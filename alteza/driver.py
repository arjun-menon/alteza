import os
import shutil
import signal
import time
import types
import traceback
from datetime import datetime
from typing import Optional, Dict, Tuple

from pypage import PypageError, PypageSyntaxError  # type: ignore
from watchdog.events import FileSystemEventHandler, FileSystemEvent, DirModifiedEvent
from watchdog.observers import Observer as WatchdogObserver
from colored import Fore, Style  # type: ignore

from .util import AltezaException, getFilesCommitDates
from .fs import FileNode, DirNode, PyPageNode, Md, NonMd
from .crawl import CrawlConfig, isHidden, crawl, ProgressBar, NameRegistry, pr
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
		CrawlConfig.configFileName = Args.config
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
			ProgressBar.increment()
			for subDir in filter(lambda node: node.shouldPublish, curDir.subDirs):
				os.mkdir(subDir.dirName)
				with enterDir(subDir.dirName):
					walk(subDir)

			for fileNode in filter(lambda node: node.shouldPublish, curDir.files):
				if isinstance(fileNode, PyPageNode):
					Driver.generatePyPageNode(fileNode)
				else:
					self.generateStaticAsset(fileNode)
				ProgressBar.increment()

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
			pr(f'Deleting directory {Fore.dark_red_2}%s{Style.reset} and all of its content...\n' % self.outputDir)
			shutil.rmtree(self.outputDir)
		os.mkdir(self.outputDir)

	def analyzeGitHistory(self, nameRegistry: NameRegistry) -> None:
		inGitRepo = os.path.exists('.git')  # Improve this to find the nearest ascendant git repo.
		if not inGitRepo:
			pr(f'Warning: {Fore.light_red}Not in a git repository{Style.reset}.\n')

		def getGitRelPath(fileNode: FileNode) -> str:
			if self.contentDir == '.':
				return fileNode.fullPath
			return os.path.join(self.contentDir, fileNode.fullPath)

		startTimeNs = time.time_ns()
		pr('Analyzing git history...', end='')
		filesPathsToFileNodes: dict[str, FileNode] = {
			getGitRelPath(fileNode): fileNode for fileNode in nameRegistry.allFiles.values()
		}
		fileCommitDates: Dict[str, Tuple[datetime, datetime]] = getFilesCommitDates(list(filesPathsToFileNodes.keys()))
		for filePath, (firstCommitDate, lastCommitDate) in fileCommitDates.items():
			fileNode = filesPathsToFileNodes[filePath]
			fileNode.gitFirstCommitDate = firstCommitDate
			fileNode.gitLastCommitDate = lastCommitDate

		elapsedMilliseconds = (time.time_ns() - startTimeNs) / 10**6
		pr(f' got the dates of {len(fileCommitDates)} files. Took {elapsedMilliseconds:.2f} ms.\n')

	def processContent(self) -> Content:
		with enterDir(self.contentDir):
			startTimeNs = time.time_ns()
			pr('Analyzing content directory...', end='')
			fsCrawlResult = crawl()
			elapsedMilliseconds = (time.time_ns() - startTimeNs) / 10**6
			pr(f' took {elapsedMilliseconds:.2f} ms.')
			pr(fsCrawlResult.nameRegistry)

		# Analyze git history
		self.analyzeGitHistory(fsCrawlResult.nameRegistry)

		# Process content
		with enterDir(self.contentDir):
			startTimeNs = time.time_ns()
			progress_total = fsCrawlResult.nameRegistry.pageCount
			ProgressBar.start(progress_total, 'Processing')
			content = Content(self.args, fsCrawlResult)
			content.process()
			ProgressBar.finish(progress_total)
			elapsedMilliseconds = (time.time_ns() - startTimeNs) / 10**6
			pr(f'\nSuccessfully completed processing. Took {elapsedMilliseconds:.2f} ms. Of which:')
			pr(
				f'  PyPage processing took {content.timePyPage.total() / 10**6:.2f} ms'
				f' in total for {content.timePyPage.count()} calls,'
				f' with each call averaging {content.timePyPage.average() / 10**6:.2f} ms.'
			)
			pr(
				f'  Markdown processing took {content.timeMarkdown.total() / 10**6:.2f} ms'
				f' in total for {content.timeMarkdown.count()} calls,'
				f' with each call averaging {content.timeMarkdown.average() / 10**6:.2f} ms.'
			)
			pr()

		pr('File Tree:')
		pr(fsCrawlResult.rootDir.displayDir())

		return content

	def makeSite(self) -> int:
		try:
			startTimeNs = time.time_ns()

			self.checkContentDir()
			content = self.processContent()

			# Generate site
			genStartTimeNs = time.time_ns()
			ProgressBar.start(content.publicNodeCounts.total(), 'Generating')
			self.resetOutputDir()
			self.generate(content)
			ProgressBar.close()
			genElapsedMilliseconds = (time.time_ns() - genStartTimeNs) / 10**6
			pr(f'Generation complete. Took {genElapsedMilliseconds:.2f} ms.')

			elapsedMilliseconds = (time.time_ns() - startTimeNs) / 10**6
			if len(content.warnings) > 0:
				pr('\nWarnings:')
				pr(
					'\n  '.join(
						f'{Fore.light_red}{fN.fullPath}{Style.reset}: {d}' for fN, d in content.warnings.items()
					)
				)
			pr(
				# pylint: disable=consider-using-f-string
				'\nSite build complete (Alteza %s). Time elapsed: %.2f ms' % (alteza_version, elapsedMilliseconds)
			)
			return 0
		except (AltezaException, PypageError, PypageSyntaxError) as e:
			pr(f'\nSite build failed due to Alteza or PyPage error: {e}')
			pr(f'\n{traceback.format_exc()}')
			return 1
		except Exception as e:
			pr(f'\nSite build failed with unexpected error: {e}')
			pr(f'\n{traceback.format_exc()}')
			return 1
		finally:
			ProgressBar.close()

	@staticmethod
	def setIgnoreAbsPaths(args: Args) -> None:
		CrawlConfig.ignoreAbsPaths = []
		for somePath in args.ignore:
			if os.path.exists(somePath):
				CrawlConfig.ignoreAbsPaths.append(os.path.abspath(somePath))
			else:
				raise AltezaException(f'Path to ignore `{somePath}` does not exist.')

	class WatchdogEventHandler(FileSystemEventHandler):
		def __init__(self, contentDir: str) -> None:
			self.contentDirAbsPath: str = os.path.abspath(contentDir)
			self.timeOfMostRecentEvent: Optional[int] = None

		def on_any_event(self, event: FileSystemEvent) -> None:
			for ignoreAbsPath in CrawlConfig.ignoreAbsPaths:
				if ignoreAbsPath in event.src_path or ignoreAbsPath in event.dest_path:
					return
			if '__pycache__' in event.src_path or '__pycache__' in event.dest_path:
				return
			if isHidden(os.path.basename(os.path.normpath(event.src_path))):
				return
			if isinstance(event, DirModifiedEvent) and event.src_path == self.contentDirAbsPath:
				return

			pr('Detected a change in:', event.src_path or event.dest_path)

			self.timeOfMostRecentEvent = max(self.timeOfMostRecentEvent or 0, time.time_ns())

	def runWatchdog(self) -> None:
		self.makeSite()

		timeIntervalNs = 2 * 10**8
		timeIntervalSecs = 0.2

		def logWatching() -> None:
			pr('\nWatching for changes... press Ctrl+C to exit.')

		eventHandler = Driver.WatchdogEventHandler(self.contentDir)
		observer = WatchdogObserver()
		observer.schedule(eventHandler, self.contentDir, recursive=True)
		observer.start()
		try:
			logWatching()

			def signalHandler(sig: int, frame: Optional[types.FrameType]) -> None:
				# pylint: disable=unused-argument
				pr('\nExiting...')
				self.shouldExit = True

			signal.signal(signal.SIGINT, signalHandler)

			while not self.shouldExit:
				time.sleep(timeIntervalSecs)
				if eventHandler.timeOfMostRecentEvent:
					timeSinceMostRecentEvent = time.time_ns() - (eventHandler.timeOfMostRecentEvent or 0)
					if timeSinceMostRecentEvent > timeIntervalNs:
						eventHandler.timeOfMostRecentEvent = None
						pr('\nRebuilding...\n')
						self.makeSite()
						logWatching()
		finally:
			observer.stop()
			observer.join()

	def run(self) -> int:
		if self.args.watch:
			self.runWatchdog()
			return 0
		return self.makeSite()
