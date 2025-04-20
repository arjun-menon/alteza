import contextlib
import itertools
import json
import logging
import os
import shutil
import signal
import sys
import time
import types
from typing import Optional, Generator, List, Union, Dict, Set, Any

import sh  # type: ignore
from pypage import pypage, PypageError  # type: ignore
from tap import Tap
from watchdog.events import FileSystemEventHandler, FileSystemEvent, DirModifiedEvent
from watchdog.observers import Observer as WatchdogObserver

from .fs import (
	FsNode,
	FileNode,
	DirNode,
	NameRegistry,
	AltezaException,
	Md,
	NonMd,
	FsCrawlResult,
	Fs,
	Fore,
	Style,
	PageNode,
	PyPageNode,
)
from .version import version as alteza_version


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
					' ' * (4 if self.inTemplate else 2)
					+ f'{Fore.grey_42}Linking to:{Style.reset} {dstFile.getLinkName()}',
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
		if isinstance(srcFile, Md) and not srcFile.isIndex() and not pathOnly:
			relativePath = ['..'] + relativePath

		relativePathStr = os.path.join('', *relativePath)
		return relativePathStr

	@staticmethod
	def getFileUrlName(dstFile: FileNode) -> str:
		if dstFile.isIndex():
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

		rawPyPageFileText: str
		if isinstance(pyPageNode, (Md, NonMd)):
			rawPyPageFileText = Fs.readfile(pyPageNode.absoluteFilePath)
		else:
			raise AltezaException(f'{pyPageNode} Unsupported type of PyPageNode.')

		def link(destination: Union[str, FsNode]) -> str:
			return self.linkFlex(pyPageNode, destination)

		def path(name: str) -> str:
			return self.linkFlex(pyPageNode, name, True)

		env |= {'link': link}
		env |= {'path': path}

		env |= {'getLastModifiedObj': lambda: pyPageNode.lastModifiedObj}
		env |= {'getLastModified': pyPageNode.getLastModified}
		env |= {'getIdeaDateObj': pyPageNode.getIdeaDateObj}
		env |= {'getIdeaDate': pyPageNode.getIdeaDate}
		env |= {'getCreateDateObj': pyPageNode.gitFirstAuthDate}
		env |= {'getCreateDate': pyPageNode.getCreateDate}

		# Invoke pypage
		pyPageOutput = pypage(rawPyPageFileText, env)

		# Perform initial Markdown processing:
		if isinstance(pyPageNode, Md):
			PyPageNode.temporal_link = link
			mdResult = Md.processMarkdown(pyPageOutput)
			PyPageNode.temporal_link = None
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
		pyPageNode.env = env
		for k, v in self.getModuleVars(env).items():
			if not hasattr(pyPageNode, k):
				setattr(pyPageNode, k, v)

	def runConfigIfAny(self, dirNode: DirNode, env: dict[str, Any]) -> Dict[str, Any]:
		# Run a __config__.py file, if one exists.
		configEnv = env.copy()
		configFileL = [f for f in dirNode.files if f.fileName == Fs.configFileName]
		if configFileL:
			configFile: FileNode = configFileL[0]

			def path(name: str) -> str:
				return self.link(configFile, self.nameRegistry.lookup(name), True)

			configEnv |= {'path': path}

			print(
				f'{Fore.dark_orange}Running:{Style.reset}',
				os.path.join(dirNode.fullPath, Fs.configFileName),
			)
			exec(Fs.readfile(Fs.configFileName), configEnv)
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
				if pyPageNode.getLinkName() not in skipNames:
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
		return {'readfile': Fs.readfile, 'sh': sh}

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


class Engine:
	# Engine.generate(...) is called to write the output of a processed Content object.
	# Engine.makeSite() is called to perform a full site generation.
	# Engine.run() is used to invoke Alteza overall.
	def __init__(self, args: Args) -> None:
		self.args: Args = args
		# Just copying & renaming a few args:
		self.shouldCopyAssets: bool = args.copy_assets
		self.contentDir: str = args.content
		self.outputDir: str = args.output
		# Other instance variables:
		self.shouldExit: bool = False
		self.setIgnoreAbsPaths(args)

	@staticmethod
	def generateMdContents(md: Md) -> None:
		if os.path.exists('index.html'):
			raise AltezaException(f'An index.html already exists, and conflicts with {md}, at {os.getcwd()}.')
		with open('index.html', 'w', encoding='utf-8') as pageHtml:
			pageHtml.write(md.output)

	@staticmethod
	def generateMd(md: Md) -> None:
		if not md.isIndex():
			os.mkdir(md.realName)
			with enterDir(md.realName):
				Engine.generateMdContents(md)
		else:
			Engine.generateMdContents(md)

	@staticmethod
	def generateNonMd(nonMd: NonMd) -> None:
		fileName = nonMd.rectifiedFileName
		if os.path.exists(fileName):
			raise AltezaException(f'File {fileName} already exists, and conflicts with {nonMd}.')
		with open(fileName, 'w', encoding='utf-8') as nonMdPageFile:
			nonMdPageFile.write(nonMd.output)

	@staticmethod
	def generatePyPageNode(pyPageNode: PyPageNode) -> None:
		if isinstance(pyPageNode, Md):
			Engine.generateMd(pyPageNode)

		elif isinstance(pyPageNode, NonMd):
			Engine.generateNonMd(pyPageNode)

		else:
			raise AltezaException(f'{pyPageNode} pyPage attribute is invalid.')

	def generateStaticAsset(self, fileNode: FileNode) -> None:
		if self.shouldCopyAssets:
			shutil.copyfile(fileNode.absoluteFilePath, fileNode.fileName)
		else:
			os.symlink(fileNode.absoluteFilePath, fileNode.fileName)

	def generate(self, content: Content) -> None:
		def walk(curDir: DirNode) -> None:
			for subDir in filter(lambda node: node.shouldPublish, curDir.subDirs):
				os.mkdir(subDir.dirName)
				with enterDir(subDir.dirName):
					walk(subDir)

			for fileNode in filter(lambda node: node.shouldPublish, curDir.files):
				if isinstance(fileNode, PyPageNode):
					Engine.generatePyPageNode(fileNode)
				else:
					self.generateStaticAsset(fileNode)

		with enterDir(self.outputDir):
			walk(content.rootDir)

	def checkContentDir(self) -> None:
		if not os.path.isdir(self.contentDir):
			raise AltezaException(f"The provided path '{self.contentDir}' does not exist or is not a directory.")

	def resetOutputDir(self) -> None:
		if os.path.isfile(self.outputDir):
			raise AltezaException(
				f'A file named {self.outputDir} already exists. Please move it or delete it. '
				'Note that if this had been a directory, we would have erased it.'
			)
		if os.path.isdir(self.outputDir):
			if not self.args.clear_output_dir:
				raise AltezaException(
					f'Specified output directory {self.outputDir} already exists.\n'
					'Please use --clear_output_dir to delete it prior to site generation.'
				)
			print(f'Deleting directory {Fore.dark_red_2}%s{Style.reset} and all of its content...\n' % self.outputDir)
			shutil.rmtree(self.outputDir)
		os.mkdir(self.outputDir)

	def processContent(self) -> Content:
		with enterDir(self.contentDir):
			print('Analyzing content directory...')
			fsCrawlResult = Fs.crawl()
			print(fsCrawlResult.nameRegistry)
			content = Content(self.args, fsCrawlResult)
			print('Processing...\n')
			content.process()
			print('\nSuccessfully completed processing.\n')

		print('File Tree:')
		print(fsCrawlResult.rootDir.displayDir())

		return content

	def makeSite(self) -> None:
		startTimeNs = time.time_ns()

		self.checkContentDir()
		self.resetOutputDir()

		content = self.processContent()
		print('Generating...')
		self.generate(content)

		elapsedMilliseconds = (time.time_ns() - startTimeNs) / 10**6
		print(
			# pylint: disable=consider-using-f-string
			'\nSite generation complete (Alteza %s). Time elapsed: %.2f ms' % (alteza_version, elapsedMilliseconds)
		)

	def makeSiteWithExceptionHandling(self) -> None:
		try:
			self.makeSite()
		except (AltezaException, PypageError) as e:
			logging.exception(e)
			print('\nSite build failed due to Alteza or PyPage error.')
		except Exception as e:
			logging.exception(e)
			print('\nSite build failed.')

	@staticmethod
	def setIgnoreAbsPaths(args: Args) -> None:
		Fs.ignoreAbsPaths = []
		for somePath in args.ignore:
			if os.path.exists(somePath):
				Fs.ignoreAbsPaths.append(os.path.abspath(somePath))
			else:
				raise AltezaException(f'Path to ignore `{somePath}` does not exist.')

	class WatchdogEventHandler(FileSystemEventHandler):
		def __init__(self, contentDir: str) -> None:
			self.contentDirAbsPath: str = os.path.abspath(contentDir)
			self.timeOfMostRecentEvent: Optional[int] = None

		def on_any_event(self, event: FileSystemEvent) -> None:
			for ignoreAbsPath in Fs.ignoreAbsPaths:
				if ignoreAbsPath in event.src_path or ignoreAbsPath in event.dest_path:
					return
			if '__pycache__' in event.src_path or '__pycache__' in event.dest_path:
				return
			if Fs.isHidden(os.path.basename(os.path.normpath(event.src_path))):
				return
			if isinstance(event, DirModifiedEvent) and event.src_path == self.contentDirAbsPath:
				return

			print('Detected a change in:', event.src_path or event.dest_path)

			self.timeOfMostRecentEvent = max(self.timeOfMostRecentEvent or 0, time.time_ns())

	def runWatchdog(self) -> None:
		self.makeSiteWithExceptionHandling()

		timeIntervalNs = 2 * 10**8
		timeIntervalSecs = 0.2

		def watching() -> None:
			print('\nWatching for changes... press Ctrl+C to exit.')

		eventHandler = Engine.WatchdogEventHandler(self.contentDir)
		observer = WatchdogObserver()
		observer.schedule(eventHandler, self.contentDir, recursive=True)
		observer.start()
		try:
			watching()

			def signalHandler(sig: int, frame: Optional[types.FrameType]) -> None:
				# pylint: disable=unused-argument
				print('\nExiting...')
				self.shouldExit = True

			signal.signal(signal.SIGINT, signalHandler)

			while not self.shouldExit:
				time.sleep(timeIntervalSecs)
				if eventHandler.timeOfMostRecentEvent:
					timeSinceMostRecentEvent = time.time_ns() - (eventHandler.timeOfMostRecentEvent or 0)
					if timeSinceMostRecentEvent > timeIntervalNs:
						eventHandler.timeOfMostRecentEvent = None
						print('\nRebuilding...\n')
						try:
							self.makeSiteWithExceptionHandling()
						except AltezaException as e:
							logging.exception(e)
							print('\nSite build failed.')
						watching()
		finally:
			observer.stop()
			observer.join()

	def run(self) -> None:
		if self.args.watch:
			self.runWatchdog()
		else:
			self.makeSite()
