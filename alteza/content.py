import contextlib
import itertools
import json
import os
import sys
import types
from typing import List, Dict, Set, Any, Union, Optional, Generator

from tap import Tap
import sh  # type: ignore
from pypage import pypage  # type: ignore

from .fs import (
	FsNode,
	FileNode,
	DirNode,
	PageNode,
	PyPageNode,
	Md,
	NonMd,
	NameRegistry,
	FsCrawlResult,
	Fs,
	AltezaException,
	Fore,
	Style,
)


class Args(Tap):  # pyre-ignore[13]
	content: str  # Directory to read the input content from.
	output: str  # Directory to write the generated site to.
	clear_output_dir: bool = False  # Delete the output directory, if it already exists.
	copy_assets: bool = False  # Copy static assets instead of symlinking to them.
	seed: str = '{}'  # Seed JSON data to add to the initial root env.
	watch: bool = False  # Watch for content changes, and rebuild.
	ignore: List[str] = []  # Paths to completely ignore.


class Content:
	def __init__(self, args: Args, fs: FsCrawlResult) -> None:
		self.inTemplate: bool = False
		self.templateCache: Dict[str, str] = {}
		self.seenTemplateLinks: Set[FileNode] = set()
		self.rootDir: DirNode = fs.rootDir
		self.nameRegistry: NameRegistry = fs.nameRegistry
		self.seed: Dict[str, Any] = json.loads(args.seed)
		self.fixSysPath()

	def link(self, srcFile: FileNode, dstFile: FileNode, pathOnly: bool = False) -> str:
		if not pathOnly:
			srcFile.linksTo.append(dstFile)  # This is used to determine reachability.
			if dstFile not in self.seenTemplateLinks:
				print(
					' ' * (4 if self.inTemplate else 2) + f'{Fore.grey_42}Linking to:{Style.reset} {dstFile.linkName}',
				)
				if self.inTemplate:
					self.seenTemplateLinks.add(dstFile)

		dstFileName = self.getFileUrlName(dstFile)

		srcPath = self.splitPath(srcFile.fullPath)[:-1]
		dstPath = self.splitPath(dstFile.fullPath)[:-1]
		commonLevel = 0
		for i in range(min(len(srcPath), len(dstPath))):
			if srcPath[i] == dstPath[i]:
				commonLevel += 1
		remainingPath = dstPath[commonLevel:] + [dstFileName]

		relativePath: List[str] = []
		if commonLevel < len(srcPath):
			stepsDown = len(srcPath) - commonLevel
			for _ in range(stepsDown):
				relativePath.append('..')
		for p in remainingPath:
			relativePath.append(p)
		if isinstance(srcFile, Md) and not srcFile.isIndex and not pathOnly:
			relativePath = ['..'] + relativePath

		relativePathStr = os.path.join('', *relativePath)
		return relativePathStr

	@staticmethod
	def getFileUrlName(dstFile: FileNode) -> str:
		if dstFile.isIndex:
			return ''
		if isinstance(dstFile, Md):
			return dstFile.realName
		if isinstance(dstFile, NonMd):
			return dstFile.rectifiedFileName
		return dstFile.fileName

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

	def invokePyPage(self, pyPageNode: PyPageNode, env: dict[str, Any]) -> None:
		print(f'{Fore.gold_1}Processing:{Style.reset}', pyPageNode.fullPath)
		env = env.copy()

		# Enrich with the current file:
		env |= {'page': pyPageNode}
		env |= pyPageNode.env

		rawPyPageFileText: str
		if isinstance(pyPageNode, (Md, NonMd)):
			rawPyPageFileText = Fs.readfile(pyPageNode.absoluteFilePath)
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

		env |= {'getLastModifiedObj': lambda: pyPageNode.lastModifiedObj}
		env |= {'getLastModified': pyPageNode.getLastModified}
		env |= {'getIdeaDateObj': pyPageNode.getIdeaDateObj}
		env |= {'getIdeaDate': pyPageNode.getIdeaDate}
		env |= {'getCreateDateObj': pyPageNode.getCreateDateObj}
		env |= {'getCreateDate': pyPageNode.getCreateDate}

		# Invoke pypage
		pyPageOutput = pypage(rawPyPageFileText, env)

		# Perform initial Markdown processing:
		if isinstance(pyPageNode, Md):
			mdResult = Md.processMarkdown(pyPageOutput)
			env.update(mdResult.metadata)
			pyPageOutput = mdResult.html

		# Handle `public` var:
		if 'public' in env:
			if env['public'] is True:
				pyPageNode.makePublic()
			elif env['public'] is False:
				pyPageNode.shouldPublish = False

		# Perform Markdown template application:
		if isinstance(pyPageNode, Md):
			templateHtml = self.getTemplateHtml(env)
			self.inTemplate = True
			# Re-process against `templateHtml` with PyPage:
			pyPageOutput = pypage(templateHtml, env | {'content': pyPageOutput})
			self.inTemplate = False

		# Set the PyPageNode's output:
		pyPageNode.output = pyPageOutput

		# Enrich with `env`.
		pyPageNode.env |= env
		for k, v in self.getModuleVars(env).items():
			if not hasattr(pyPageNode, k):
				setattr(pyPageNode, k, v)

		PyPageNode.temporal_link = None

	def runConfigIfAny(self, dirNode: DirNode, env: dict[str, Any]) -> Dict[str, Any]:
		# Run a __config__.py file, if one exists.
		configEnv = env.copy()
		configFileL = [f for f in dirNode.files if f.fileName == Fs.configFileName]
		if configFileL:
			configFile: FileNode = configFileL[0]

			def path(name: str) -> str:
				return self.link(configFile, self.nameRegistry.lookup(name), True)

			configEnv |= {'file': self.nameRegistry.lookup}
			configEnv |= {'path': path}

			print(
				f'{Fore.dark_orange}Running:{Style.reset}',
				os.path.join(dirNode.fullPath, Fs.configFileName),
			)
			exec(Fs.readfile(Fs.configFileName), configEnv)

			if 'title' in configEnv:
				if dirNode.configTitle is not None:
					raise AltezaException('Do not set both `title` and `dir.title` in `__config__.py`.')
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
			skipNames = self.getSkipNames(env)  # Process `skip`.

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

			# We must process the index file last.
			indexPage: Optional[PageNode] = dirNode.indexPage
			if indexPage is not None and isinstance(indexPage, PyPageNode):
				self.invokePyPage(indexPage, env)

			# TODO: Enrich dirNode with additional `env`/info from index?

		initial_env = self.seed | self.getBasicHelpers()

		walk(self.rootDir, initial_env)

		self.tracePublic()

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

		print('\nInitial pre-reachability public files:')
		for node in filter(lambda pNode: isinstance(pNode, FileNode), publicNodes):
			print('/' + node.fullPath)

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
		return {'readfile': Fs.readfile, 'sh': sh, 'markdown': lambda text: Md.processMarkdown(text).html}

	@staticmethod
	def splitPath(path: str) -> List[str]:
		head, tail = os.path.split(path)
		if head == '':
			return [path]
		return Content.splitPath(head) + [tail]

	def getTemplateHtml(self, env: dict[str, Any]) -> str:
		if 'layoutRaw' in env:
			templateRaw = env['layoutRaw']
			if not isinstance(templateRaw, str):
				raise AltezaException('The `layoutRaw` must be a string.')
			print(f'  {Fore.purple_3}Applying raw template...{Style.reset}')
			return templateRaw
		if 'layout' in env:
			templateName = env['layout']
			print(
				f'  {Fore.purple_3}Applying template: {Fore.blue_violet}{templateName}{Fore.purple_3}...{Style.reset}'
			)
			if templateName in self.templateCache:
				return self.templateCache[templateName]
			templateFile = self.nameRegistry.lookup(templateName)
			templateRaw = Fs.readfile(templateFile.absoluteFilePath)
			self.templateCache[templateName] = templateRaw
			return templateRaw
		raise AltezaException('You must define a `layout` or `layoutRaw` in some ancestral `__config__.py` file.')


@contextlib.contextmanager
def enterDir(newDir: str) -> Generator[None, None, None]:
	# https://stackoverflow.com/a/13847807/908430
	oldDir = os.getcwd()
	os.chdir(newDir)
	try:
		yield
	finally:
		os.chdir(oldDir)
