import logging
import os
import shutil
import signal
import time
import types
from typing import Optional

from pypage import PypageError, PypageSyntaxError  # type: ignore
from watchdog.events import FileSystemEventHandler, FileSystemEvent, DirModifiedEvent
from watchdog.observers import Observer as WatchdogObserver

from .fs import (
	FileNode,
	DirNode,
	AltezaException,
	Md,
	NonMd,
	Fs,
	Fore,
	Style,
	PyPageNode,
)
from .content import Args, Content, enterDir
from .version import version as alteza_version


class Driver:
	# Driver.generate(...) is called to write the output of a processed Content object.
	# Driver.makeSite() is called to perform a full site generation.
	# Driver.run() is used to invoke Alteza overall.
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
		if not md.isIndex:
			os.mkdir(md.realName)
			with enterDir(md.realName):
				Driver.generateMdContents(md)
		else:
			Driver.generateMdContents(md)

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
			Driver.generateMd(pyPageNode)

		elif isinstance(pyPageNode, NonMd):
			Driver.generateNonMd(pyPageNode)

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
					Driver.generatePyPageNode(fileNode)
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
		if len(content.warnings) > 0:
			print('\nWarnings:')
			print('\n  '.join(f'{Fore.light_red}{fN.fullPath}{Style.reset}: {d}' for fN, d in content.warnings.items()))
		print(
			# pylint: disable=consider-using-f-string
			'\nSite generation complete (Alteza %s). Time elapsed: %.2f ms' % (alteza_version, elapsedMilliseconds)
		)

	def makeSiteWithExceptionHandling(self) -> None:
		try:
			self.makeSite()
		except (AltezaException, PypageError, PypageSyntaxError) as e:
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

		eventHandler = Driver.WatchdogEventHandler(self.contentDir)
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
