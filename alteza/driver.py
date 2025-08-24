import os
import shutil
import signal
import time
import types
import traceback
from datetime import datetime
from typing import Optional, Dict, Tuple, Set, Any, List

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
		# Content instance variable:
		self.content: Optional[Content] = None
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

		# Store content for potential selective rebuilds
		self.content = content
		return content

	def findDescendantMarkdownFiles(self, configFilePath: str) -> List[str]:
		"""Find all Markdown files that are descendants of a config file directory."""
		if self.content is None:
			return []

		# Get the directory containing the config file
		configDir = os.path.dirname(configFilePath) if configFilePath != CrawlConfig.configFileName else '.'

		descendant_files = []

		# Find all markdown files in the name registry
		for linkName, fileNode in self.content.nameRegistry.allFiles.items():
			if isinstance(fileNode, Md):
				# Check if this file is in the config directory or a subdirectory
				fileDir = os.path.dirname(fileNode.fullPath) if fileNode.fullPath != fileNode.fileName else '.'

				# Check if fileDir is configDir or a subdirectory of configDir
				if configDir == '.':
					# Root config affects all files
					descendant_files.append(fileNode.fullPath)
				elif fileDir == configDir or fileDir.startswith(configDir + '/'):
					descendant_files.append(fileNode.fullPath)

		return descendant_files

	def selectiveRebuildMultiple(self, rebuild_info: Dict[str, Any]) -> bool:
		"""Rebuild multiple files based on the rebuild info. Returns True if successful, False if fallback needed."""
		try:
			rebuild_type = rebuild_info['type']
			pr(f'{Fore.light_blue}Selective rebuild ({rebuild_type}):{Style.reset}')

			# Use existing content if available, otherwise process from scratch
			if self.content is None:
				with enterDir(self.contentDir):
					fsCrawlResult = crawl()
				self.analyzeGitHistory(fsCrawlResult.nameRegistry)
				self.content = Content(self.args, fsCrawlResult)

			files_to_rebuild = []

			if rebuild_type == 'markdown_only':
				files_to_rebuild = rebuild_info['files']
			elif rebuild_type == 'config_and_descendants':
				# Add explicitly changed markdown files
				files_to_rebuild.extend(rebuild_info.get('markdown_files', []))

				# Add descendants of each changed config file
				for config_file in rebuild_info['config_files']:
					descendants = self.findDescendantMarkdownFiles(config_file)
					files_to_rebuild.extend(descendants)

				# Remove duplicates
				files_to_rebuild = list(set(files_to_rebuild))

			if not files_to_rebuild:
				pr('No markdown files to rebuild')
				return True

			pr(f'  Rebuilding {len(files_to_rebuild)} files: {files_to_rebuild}')

			# Process each file
			successful_rebuilds = 0
			for file_path in files_to_rebuild:
				try:
					success = self._rebuildSingleMarkdownFile(file_path)
					if success:
						successful_rebuilds += 1
					else:
						pr(f'  Failed to rebuild {file_path}')
						return False
				except Exception as e:
					pr(f'  Error rebuilding {file_path}: {e}')
					return False

			pr(
				f'{Fore.light_green}Selective rebuild complete: {successful_rebuilds}/{len(files_to_rebuild)} files{Style.reset}'
			)
			return True

		except Exception as e:
			pr(f'{Fore.light_red}Selective rebuild failed:{Style.reset} {e}')
			pr('Falling back to full rebuild')
			return False

	def _rebuildSingleMarkdownFile(self, file_path: str) -> bool:
		"""Internal method to rebuild a single markdown file. Returns True if successful."""
		# Find the file in the name registry
		fileBaseName = os.path.splitext(os.path.basename(file_path))[0]
		try:
			fileNode = self.content.nameRegistry.lookup(fileBaseName)
		except AltezaException:
			pr(f'  Could not find {fileBaseName} in name registry')
			return False

		if not isinstance(fileNode, Md):
			pr(f'  {fileBaseName} is not a Markdown file')
			return False

		# Build environment by walking up the directory hierarchy
		env = self.content.seed | Content.getBasicHelpers()

		# Walk through all ancestor directories to build up environment
		dirNode = fileNode.parentDir
		ancestorDirs = []

		# Collect all ancestor directories
		currentDir = dirNode
		while currentDir is not None:
			ancestorDirs.append(currentDir)
			currentDir = currentDir.parent

		# Reverse to process from root to leaf
		ancestorDirs.reverse()

		# Process config files from root down to the file's directory
		with enterDir(self.contentDir):
			for ancestorDir in ancestorDirs:
				if ancestorDir.fullPath != '.':
					with enterDir(ancestorDir.fullPath):
						env = env.copy()
						env |= {'dir': ancestorDir}
						env |= Content.getModuleVars(self.content.runConfigIfAny(ancestorDir, env))
				else:
					env = env.copy()
					env |= {'dir': ancestorDir}
					env |= Content.getModuleVars(self.content.runConfigIfAny(ancestorDir, env))

		# Process the markdown file
		with enterDir(self.contentDir):
			self.content.invokePyPage(fileNode, env)

		# Generate output for this specific file
		with enterDir(self.outputDir):
			# Navigate to the correct output subdirectory if needed
			outputPath = os.path.dirname(fileNode.fullPath)
			if outputPath and outputPath != '.':
				# Ensure the output directory structure exists
				os.makedirs(outputPath, exist_ok=True)
				with enterDir(outputPath):
					Driver.generateMd(fileNode)
			else:
				Driver.generateMd(fileNode)

		return True

	def selectiveRebuildSingleMd(self, changedFile: str) -> bool:
		"""Rebuild just a single Markdown file. Returns True if successful, False if fallback to full rebuild needed."""
		try:
			pr(f'{Fore.light_blue}Selective rebuild:{Style.reset} {changedFile}')

			# Use existing content if available, otherwise process from scratch
			if self.content is None:
				with enterDir(self.contentDir):
					fsCrawlResult = crawl()
				self.analyzeGitHistory(fsCrawlResult.nameRegistry)
				self.content = Content(self.args, fsCrawlResult)
				# Note: We don't call content.process() here since we only want to process one file

			success = self._rebuildSingleMarkdownFile(changedFile)
			if success:
				pr(f'{Fore.light_green}Selective rebuild complete{Style.reset}')
				return True
			else:
				return False

		except Exception as e:
			pr(f'{Fore.light_red}Selective rebuild failed:{Style.reset} {e}')
			pr('Falling back to full rebuild')
			return False

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
			self.pathsOfChangedFiles: Set[str] = set()

		def isOnlyOneMarkdownFileChanged(self) -> Optional[str]:
			"""Check if only one file changed and it's a Markdown file. Returns the file path if so, None otherwise."""
			if len(self.pathsOfChangedFiles) != 1:
				return None

			changed_file = next(iter(self.pathsOfChangedFiles))
			# Remove leading slash if present
			if changed_file.startswith('/'):
				changed_file = changed_file[1:]

			if changed_file.endswith('.md'):
				return changed_file
			return None

		def getSelectiveRebuildInfo(self) -> Optional[Dict[str, Any]]:
			"""
			Analyze changed files and determine if selective rebuild is possible.
			Returns None if full rebuild needed, otherwise returns rebuild info dict.
			"""
			if len(self.pathsOfChangedFiles) == 0:
				return None

			# Clean up file paths
			changed_files = []
			for file_path in self.pathsOfChangedFiles:
				if file_path.startswith('/'):
					file_path = file_path[1:]
				changed_files.append(file_path)

			# Check for config file changes
			config_changes = []
			markdown_changes = []
			other_changes = []

			for file_path in changed_files:
				file_name = os.path.basename(file_path)
				if file_name == CrawlConfig.configFileName:
					config_changes.append(file_path)
				elif file_path.endswith('.md'):
					markdown_changes.append(file_path)
				else:
					other_changes.append(file_path)

			# If there are non-markdown, non-config changes, do full rebuild
			if other_changes:
				return None

			# If only markdown files changed, we can do selective rebuild
			if config_changes == [] and markdown_changes:
				return {'type': 'markdown_only', 'files': markdown_changes}

			# If config files changed, we need to rebuild affected descendants
			if config_changes:
				return {
					'type': 'config_and_descendants',
					'config_files': config_changes,
					'markdown_files': markdown_changes,
				}

			return None

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

			changedPath = event.src_path or event.dest_path
			if not os.path.isdir(changedPath):
				changedPath = changedPath.removeprefix(self.contentDirAbsPath)
				self.pathsOfChangedFiles.add(changedPath)
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
						pr(f'Detected a change in the following files: {eventHandler.pathsOfChangedFiles}')

						# Check if we can do a selective rebuild
						rebuild_info = eventHandler.getSelectiveRebuildInfo()
						if rebuild_info:
							pr('\nAttempting selective rebuild...\n')
							success = self.selectiveRebuildMultiple(rebuild_info)
							if success:
								eventHandler.pathsOfChangedFiles = set()
								logWatching()
								continue

						# Fall back to full rebuild
						eventHandler.pathsOfChangedFiles = set()
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
