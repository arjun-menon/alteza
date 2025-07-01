import contextlib
import itertools
import json
import os
import sys
import types
from typing import List, Dict, Set, Any, Union, Optional, Generator, Callable

from tap import Tap
import sh  # type: ignore
from pypage import pypage  # type: ignore
from colored import Fore, Style  # type: ignore

from .fs import AltezaException, PublicNodeCounts, FsNode, FileNode, DirNode, PageNode, PyPageNode, Md, NonMd
from .crawl import NameRegistry, CrawlResult, CrawlConfig, ProgressBar, pr
from .util import StopWatch, MultiRunTimes


class Args(Tap):  # pyre-ignore[13]
	content: str  # Directory to read the input content from.
	output: str  # Directory to write the generated site to.
	clear_output_dir: bool = False  # Delete the output directory, if it already exists.
	copy_assets: bool = False  # Copy static assets instead of symlinking to them.
	seed: str = '{}'  # Seed JSON data to add to the initial root env.
	watch: bool = False  # Watch for content changes, and rebuild.
	ignore: List[str] = []  # Paths to completely ignore.
	config: str = '__config__.py'


class Content:  # pylint: disable=too-many-instance-attributes
	def __init__(self, args: Args, fs: CrawlResult) -> None:
		self.publicNodeCounts: PublicNodeCounts = PublicNodeCounts()
		FsNode.publicNodeCounts = self.publicNodeCounts
		self.inTemplate: bool = False
		self.templateCache: Dict[str, str] = {}
		self.seenTemplateLinks: Set[FileNode] = set()
		self.rootDir: DirNode = fs.rootDir
		self.nameRegistry: NameRegistry = fs.nameRegistry
		self.seed: Dict[str, Any] = json.loads(args.seed)
		self.timePyPage: MultiRunTimes = MultiRunTimes()
		self.timeMarkdown: MultiRunTimes = MultiRunTimes()
		self.warnings: Dict[FileNode, str] = {}
		self.fixSysPath()

	def link(self, srcFile: FileNode, dstFile: FileNode, pathOnly: bool = False) -> str:
		if not pathOnly:
			srcFile.linksTo.append(dstFile)  # This is used to determine reachability.
			if dstFile not in self.seenTemplateLinks:
				pr(
					' ' * (4 if self.inTemplate else 2) + f'{Fore.grey_42}Linking to:{Style.reset} {dstFile.linkName}',
				)
				if self.inTemplate:
					self.seenTemplateLinks.add(dstFile)

		return FileNode.relativePath(srcFile, dstFile, pathOnly)

	def linkFlex(
		self,
		fromPyPage: PyPageNode,
		destination: Union[str, FsNode],
		pathOnly: bool = False,
	) -> str:
		if isinstance(destination, str):
			dstFile: FileNode = self.nameRegistry.lookup(destination)
			return self.link(fromPyPage, dstFile, pathOnly)
		if isinstance(destination, FileNode):
			return self.link(fromPyPage, destination, pathOnly)
		if isinstance(destination, DirNode):
			if not destination.indexPage:
				raise AltezaException(f'Directory `{destination}` has no index page.')
			return self.link(fromPyPage, destination.indexPage, pathOnly)
		raise AltezaException(f'Unknown link destination type: `{type(destination)}`.')

	def warn(self, fileNode: FileNode, desc: str) -> None:
		self.warnings[fileNode] = desc

	def invokePyPage(self, pyPageNode: PyPageNode, env: dict[str, Any]) -> None:
		pr(f'{Fore.gold_1}Processing:{Style.reset}', pyPageNode.fullPath)
		FileNode.current_pypage_node_being_processed = pyPageNode
		env = env.copy()

		# Enrich with the current file:
		env |= {'page': pyPageNode}
		env |= {'warn': lambda desc: self.warn(pyPageNode, desc)}
		env |= pyPageNode.env

		rawPyPageFileText: str
		if isinstance(pyPageNode, (Md, NonMd)):
			rawPyPageFileText = readfile(pyPageNode.absoluteFilePath)
		else:
			raise AltezaException(f'{pyPageNode} Unsupported type of PyPageNode.')

		def link(destination: Union[str, FsNode], pathOnly: bool = False) -> str:
			return self.linkFlex(pyPageNode, destination, pathOnly)

		PyPageNode.temporal_link = link

		def path(name: str) -> str:
			return self.linkFlex(pyPageNode, name, True)

		env |= {'file': self.nameRegistry.lookup}
		env |= {'link': link}
		env |= {'path': path}

		env |= {'lastModified': pyPageNode.lastModified}
		env |= {'lastModifiedObj': lambda: pyPageNode.lastModifiedObj}
		env |= {'ideaDate': pyPageNode.ideaDate}
		env |= {'ideaDateObj': pyPageNode.ideaDateObj}
		env |= {'firstCommitDate': pyPageNode.firstCommitDate}
		env |= {'firstCommitDateObj': pyPageNode.firstCommitDateObj}

		# Invoke pypage on the raw page file text:
		with StopWatch() as sw:
			pyPageOutput = pypage(rawPyPageFileText, env)
		self.timePyPage.add(sw)

		# Perform Markdown processing:
		if isinstance(pyPageNode, Md):
			with StopWatch() as sw:
				mdResult = Md.processMarkdown(pyPageOutput)
			self.timeMarkdown.add(sw)
			env.update(mdResult.metadata)
			pyPageOutput = mdResult.html

		# Enrich with `env`:
		pyPageNode.env |= env
		for k, v in self.getModuleVars(env).items():
			if k not in dir(pyPageNode):
				setattr(pyPageNode, k, v)

		# Perform template application (invoke PyPage on the layout template):
		if isinstance(pyPageNode, Md):
			templateHtml = self.getTemplateHtml(env)
			self.inTemplate = True
			# Re-process against `templateHtml` with PyPage:
			with StopWatch() as sw:
				pyPageOutput = pypage(templateHtml, env | {'content': pyPageOutput})
			self.timePyPage.add(sw)
			self.inTemplate = False

		# Set the PyPageNode's output:
		pyPageNode.output = pyPageOutput

		# Handle `public` var:
		if 'public' in env:
			if env['public'] is True:
				pyPageNode.makePublic()

		FileNode.current_pypage_node_being_processed = None
		PyPageNode.temporal_link = None

	def runConfigIfAny(self, dirNode: DirNode, env: dict[str, Any]) -> Dict[str, Any]:
		# Run the config Python file (usually `__config__.py`) if one exists.
		configEnv = env.copy()
		configFileL = [f for f in dirNode.files if f.fileName == CrawlConfig.configFileName]
		if configFileL:
			configFile: FileNode = configFileL[0]

			def path(name: str) -> str:
				return self.link(configFile, self.nameRegistry.lookup(name), True)

			configEnv |= {'file': self.nameRegistry.lookup}
			configEnv |= {'warn': lambda desc: self.warn(configFile, desc)}
			configEnv |= {'path': path}

			pr(
				f'{Fore.dark_orange}Running:{Style.reset}',
				os.path.join(dirNode.fullPath, CrawlConfig.configFileName),
			)
			exec(readfile(CrawlConfig.configFileName), configEnv)

			if 'title' in configEnv:
				if dirNode.configTitle is not None:
					raise AltezaException(f'Do not set both `title` and `dir.title` in `{CrawlConfig.configFileName}`.')
				dirNode.title = configEnv['title']
				del configEnv['title']
		return configEnv

	@staticmethod
	def getSkipNames(env: dict[str, Any]) -> List[str]:
		skipNames = []
		if 'skip' in env:
			skipVar = env['skip']
			if isinstance(skipVar, list):
				for skipName in skipVar:
					if isinstance(skipName, str):
						skipNames.append(skipName)
					else:
						raise AltezaException(
							'`skip` must be a list of strings representing names to be skipped.\n'
							+ f'`{skipName}` is not a string.'
						)
			else:
				raise AltezaException('`skip` must be a list of names.')
		return skipNames

	def process(self) -> None:
		def walk(dirNode: DirNode, env: dict[str, Any]) -> None:
			env = env.copy()  # Duplicate env.
			env |= {'dir': dirNode}  # Enrich with current dir.
			env |= self.getModuleVars(self.runConfigIfAny(dirNode, env))  # Run config.
			skipNames = self.getSkipNames(env)  # Type check `skip`.

			# Ordering Note: We must recurse into the subdirectories first.
			for d in dirNode.subDirs:
				if d.dirName not in skipNames:
					with enterDir(d.dirName):
						walk(d, env)

			# Ordering Note: Files in the current directory must be processed after
			# all subdirectories have been processed so that they have access to
			# information about the subdirectories.
			for pyPageNode in dirNode.getPyPagesOtherThanIndex():
				if pyPageNode.linkName not in skipNames:
					self.invokePyPage(pyPageNode, env)
				ProgressBar.increment()

			self.sortDirNode(dirNode, env)

			# We must process the index file last.
			indexPage: Optional[PageNode] = dirNode.indexPage
			if indexPage is not None and isinstance(indexPage, PyPageNode):
				self.invokePyPage(indexPage, env)
				ProgressBar.increment()

			# TODO: Enrich dirNode with additional `env`/info from index?

		initial_env = self.seed | self.getBasicHelpers()

		walk(self.rootDir, initial_env)

		self.tracePublic()

	@staticmethod
	def sortDirNode(dirNode: DirNode, env: dict[str, Any]) -> None:
		# Sorting:
		# =========
		def getField(fieldName: str) -> Optional[Union[str, Callable[[Any], Any]]]:
			return env.get(fieldName) or getattr(dirNode, fieldName, None)

		# Sort all
		sortKey: Optional[Union[str, Callable[[Any], Any]]] = getField('sortKey')

		# Sort dirs
		fieldName = 'sortDirsKey'
		sortDirsKey: Optional[Union[str, Callable[[Any], Any]]] = getField(fieldName)
		if sortDirsKey is None:
			sortDirsKey = sortKey
			fieldName = 'sortKey'
		if sortDirsKey is not None:
			if callable(sortDirsKey):
				# Sort all by specified key function
				dirNode.subDirs.sort(key=sortDirsKey)
			elif isinstance(sortDirsKey, str):
				# Sort all by specified key string
				dirNode.subDirs.sort(key=lambda d: getattr(d, sortDirsKey))
			else:
				raise AltezaException(
					f'`{fieldName}` must be a string or a function, but got `{sortDirsKey}` of type `{type(sortDirsKey)}`.'
				)

		# Sort files
		fieldName = 'sortFilesKey'
		sortFilesKey: Optional[Union[str, Callable[[Any], Any]]] = getField(fieldName)
		if sortFilesKey is None:
			fieldName = 'sortKey'
			sortFilesKey = sortKey
		if sortFilesKey is not None:
			if callable(sortFilesKey):
				# Sort files by specified key function
				dirNode.files.sort(key=sortFilesKey)
			elif isinstance(sortFilesKey, str):
				# Sort files by specified key string
				dirNode.files.sort(key=lambda f: getattr(f, sortFilesKey))
			else:
				raise AltezaException(
					f'`{fieldName}` must be a string or a function, but got `{sortFilesKey}` of type `{type(sortFilesKey)}`.'
				)

	def tracePublic(self) -> None:
		"""Make all nodes reachable from public nodes public. (Called after processing.)"""
		if '/' in self.nameRegistry.allFiles:
			# Always make the root (/) level index page public, if it exists.
			rootIndex = self.nameRegistry.allFiles['/']
			rootIndex.makePublic()

		publicNodes: List['FsNode'] = []

		def gatherPublicNodes(fsNode: FsNode) -> None:
			if isinstance(fsNode, DirNode):
				for dirNode in itertools.chain(fsNode.subDirs, fsNode.files):
					gatherPublicNodes(dirNode)
			if fsNode.shouldPublish:
				publicNodes.append(fsNode)

		gatherPublicNodes(self.rootDir)

		pr('\nInitial pre-reachability public files:')
		for node in filter(lambda pNode: isinstance(pNode, FileNode), publicNodes):
			pr('/' + node.fullPath)
		pr()

		pr('Marking all reachable nodes as public...')
		seen: Set['FsNode'] = set()

		def makeReachableNodesPublic(fsNode: FsNode) -> None:
			if fsNode in seen:
				return
			seen.add(fsNode)

			if not fsNode.shouldPublish:
				fsNode.makePublic()

			for linkedToNode in fsNode.linksTo:
				makeReachableNodesPublic(linkedToNode)

		for node in publicNodes:
			makeReachableNodesPublic(node)

		pr(f'{self.publicNodeCounts.total()} reachable public nodes.\n')

	@staticmethod
	def fixSysPath() -> None:
		"""
		This is necessary for import statements inside executed .py to consider the current directory.
		Without this, for example, an import statement inside a `__config__.py` file will error out.
		See: https://stackoverflow.com/questions/57870498/cannot-find-module-after-change-directory
		"""
		sys.path.insert(0, '')

	@staticmethod
	def getModuleVars(env: Dict[str, Any]) -> Dict[str, Any]:
		return {k: v for k, v in env.items() if (not k.startswith('_') and not isinstance(v, types.ModuleType))}

	@staticmethod
	def getBasicHelpers() -> Dict[str, Any]:
		return {'readfile': readfile, 'sh': sh, 'markdown': lambda text: Md.processMarkdown(text).html}

	def getTemplateHtml(self, env: dict[str, Any]) -> str:
		if 'layoutRaw' in env:
			templateRaw = env['layoutRaw']
			if not isinstance(templateRaw, str):
				raise AltezaException('The `layoutRaw` must be a string.')
			pr(f'  {Fore.purple_3}Applying raw template...{Style.reset}')
			return templateRaw
		if 'layout' in env:
			templateName = env['layout']
			pr(f'  {Fore.purple_3}Applying template: {Fore.blue_violet}{templateName}{Fore.purple_3}...{Style.reset}')
			if templateName in self.templateCache:
				return self.templateCache[templateName]
			templateFile = self.nameRegistry.lookup(templateName)
			templateRaw = readfile(templateFile.absoluteFilePath)
			self.templateCache[templateName] = templateRaw
			return templateRaw
		raise AltezaException(
			f'You must define a `layout` or `layoutRaw` in some ancestral `{CrawlConfig.configFileName}` file.'
		)


def readfile(file_path: str) -> str:
	with open(file_path, 'r', encoding='utf-8') as someFile:
		return someFile.read()


@contextlib.contextmanager
def enterDir(newDir: str) -> Generator[None, None, None]:
	# https://stackoverflow.com/a/13847807/908430
	oldDir = os.getcwd()
	os.chdir(newDir)
	try:
		yield
	finally:
		os.chdir(oldDir)
