import functools
import os
import re
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime
from subprocess import STDOUT, CalledProcessError, check_output
from typing import (
	Any,
	Callable,
	DefaultDict,
	Dict,
	Union,
	Iterator,
	List,
	NamedTuple,
	Optional,
	Sequence,
	Set,
	Tuple,
)

import markdown
import yaml
from colored import Fore, Style  # type: ignore
from markdown.extensions.wikilinks import WikiLinkExtension


class AltezaException(Exception):
	"""Alteza Exception"""


class FsNode:
	def __init__(self, parent: Optional['DirNode'], dirPath: str, fileName: Optional[str]) -> None:
		self.parent = parent
		self.fileName: Optional[str] = fileName
		self.dirName: str = os.path.basename(dirPath)
		self.fullPath: str = (
			(os.curdir if dirPath == '' else dirPath)
			if isinstance(self, DirNode) or not isinstance(fileName, str)
			else os.path.join(dirPath, fileName)
		)
		self.shouldPublish: bool = False
		# These fields are populated later during processing:
		self.linksTo: List['FsNode'] = []
		self.env: dict[str, Any] = {}

	def __repr__(self) -> str:
		return self.colorize(self.fullPath)

	def colorize(self, r: str) -> str:
		if self.shouldPublish:
			r = f'{Style.bold}{Fore.spring_green_2b}{r}{Style.reset}'
		return r

	def setNodeAsPublic(self) -> None:
		self.shouldPublish = True

	def makePublic(self) -> None:
		self.runOnFsNodeAndAscendantNodes(self, lambda fsNode: fsNode.setNodeAsPublic())

	def isParentGitRepo(self) -> bool:
		if self.parent is None:
			return DirNode.isPwdGitRepo()
		return self.parent.isInGitRepo

	@staticmethod
	def runOnFsNodeAndAscendantNodes(startingNode: 'FsNode', fn: Callable[['FsNode'], None]) -> None:
		def walk(node: FsNode) -> None:
			fn(node)
			if node.parent is not None:
				walk(node.parent)

		walk(startingNode)


class FileNode(FsNode):
	# pylint: disable=too-many-instance-attributes
	@staticmethod
	def construct(parent: Optional['DirNode'], dirPath: str, fileName: str) -> 'FileNode':
		"""Constructs an object of type FileNode or one of its subclasses.
		Check if fileName needs to be processed with pypage.
		    If is a Md page, we return a Md object.
		    If is a non-Md page, we return a NonMd object.
		If it is neither, we return a FileNode object.
		"""
		_, extension = FileNode.splitFileName(fileName)

		if extension == '.md':
			return Md(parent, dirPath, fileName)

		if '.py.' in fileName:
			pySubExtPos = fileName.find('.py.')
			remainingExt = fileName[pySubExtPos:]
			expectedRemainingExt = '.py' + extension
			if remainingExt == expectedRemainingExt:
				# The condition above passing indicates this is a NonMd page file.
				realName = fileName[:pySubExtPos]
				rectifiedFileName = realName + extension
				return NonMd(realName, rectifiedFileName, parent, dirPath, fileName)

		if extension == '.html':
			return PageNode(parent, dirPath, fileName)

		return FileNode(parent, dirPath, fileName)

	@staticmethod
	def splitFileName(fileName: str) -> Tuple[str, str]:
		return os.path.splitext(fileName)

	def __init__(self, parent: Optional['DirNode'], dirPath: str, fileName: str) -> None:
		"""Do not use this constructor directly. Use the static method construct instead."""
		super().__init__(parent, dirPath, fileName)
		baseName, extension = FileNode.splitFileName(fileName)
		self.absoluteFilePath: str = os.path.join(os.getcwd(), self.fullPath)
		self.fileName: str = fileName  # pyright: ignore
		self.extension: str = extension
		self.baseName: str = baseName
		self.realName: str = self.baseName  # to be overwritten selectively
		self.preSlugRealName: Optional[str] = None

		# Note: The parent of a FileNode is always a DirNode (and never None).
		assert isinstance(self.parent, DirNode)
		self.parentDir: DirNode = self.parent
		self.parentName: str = self.parentDir.dirName

	@functools.cached_property
	def isIndex(self) -> bool:
		# Index pages are `index.md` or `index[.py].html` files.
		return self.realName == 'index' and (self.extension in ('.md', '.html'))

	@functools.cached_property
	def linkName(self) -> str:
		if self.isIndex:
			return self.parentDir.dirName
		return self.realName

	@property
	def title(self) -> str:
		if 'title' in self.env:
			return self.env['title']
		return self.realName

	def isPyPage(self) -> bool:
		return isinstance(self, PyPageNode)

	def colorize(self, r: str) -> str:
		if self.isPyPage() is not None and self.shouldPublish:
			r = f'{Fore.spring_green_1}{r}{Style.reset}'
		elif isinstance(self, Md):
			r = f'{Fore.purple_4b}{r}{Style.reset}'
		return r

	def __repr__(self) -> str:
		r = f'{self.fileName}'
		r = self.colorize(r)
		r = super().colorize(r)
		return r


class DirNode(FsNode):
	def __init__(
		self,
		parent: Optional['DirNode'],
		dirPath: str,
		# shouldIgnore(name: str, parentPath: str, isDir: bool) -> bool
		shouldIgnore: Callable[[str, str, bool], bool],
	) -> None:
		_, subDirNames, fileNames = next(os.walk(dirPath))
		dirPath = '' if dirPath == os.curdir else dirPath
		super().__init__(parent, dirPath, None)
		self.configTitle: Optional[str] = None

		self.files: List[FileNode] = [
			FileNode.construct(self, dirPath, fileName)
			for fileName in fileNames
			if not shouldIgnore(fileName, self.fullPath, False)
		]
		self.subDirs: List[DirNode] = [
			DirNode(self, os.path.join(dirPath, subDirName), shouldIgnore)
			for subDirName in subDirNames
			if not shouldIgnore(subDirName, self.fullPath, True)
		]

		# Note: if `dirName` is an empty string (""), that means we're at the root (/).
		self.dirName: str = self.dirName if len(self.dirName) > 0 else '/'

	@functools.cached_property
	def isInGitRepo(self) -> bool:
		# We recheck if it's a git repo for each directory, in case
		# there's a symlink to a directory outside a git repo.
		return DirNode.isPwdGitRepo()

	@staticmethod
	def isPwdGitRepo() -> bool:
		try:
			check_output(['git', 'status'], stderr=STDOUT).decode()
			return True
		except CalledProcessError:
			return False

	@property
	def pages(self) -> Sequence['PageNode']:
		return [f for f in self.files if (isinstance(f, PageNode) and not f.isIndex)]

	def getPyPagesOtherThanIndex(self) -> Iterator['PyPageNode']:
		return (f for f in self.files if (isinstance(f, PyPageNode) and not f.isIndex))

	@functools.cached_property
	def indexPage(self) -> Optional['PageNode']:
		indexFilter = filter(lambda f: f.isIndex, self.files)
		indexFile: Optional[FileNode] = next(indexFilter, None)
		if indexFile:
			assert isinstance(indexFile, PageNode)
			return indexFile
		return None

	@functools.cached_property
	def hasIndexPage(self) -> bool:
		return self.indexPage is not None

	@property
	def title(self) -> Optional[str]:
		if self.indexPage and 'title' in self.indexPage.env:
			return self.indexPage.title
		return self.configTitle

	@title.setter
	def title(self, configTitle: str) -> None:
		self.configTitle = configTitle

	@property
	def titleOrName(self) -> str:
		return self.title if self.title else self.dirName

	@staticmethod
	def _displayDir(dirNode: 'DirNode', indent: int = 0) -> str:
		return (
			(' ' * 2 * indent)
			+ f'{dirNode} -> {dirNode.files}\n'
			+ ''.join(DirNode._displayDir(subDir, indent + 1) for subDir in dirNode.subDirs)
		)

	def displayDir(self) -> str:
		return self._displayDir(self)


class PageNode(FileNode):
	default_date_format: str = '%Y %b %-d'
	default_datetime_format: str = default_date_format + ' at %-H:%M %p'

	def getLastModified(self, f: str = default_datetime_format) -> str:
		# The formatting below might only work on Linux. https://stackoverflow.com/a/29980406/908430
		return self.lastModifiedObj.strftime(f)

	def getIdeaDate(self, f: str = default_date_format) -> str:
		ideaDate = self.getIdeaDateObj()
		return ideaDate.strftime(f) if ideaDate else ''

	def getIdeaDateObj(self) -> Optional[date]:
		if isinstance(self, Md):
			if self.ideaDate is not None:
				return self.ideaDate
		return self.gitFirstAuthDate

	def getCreateDate(self, f: str = default_date_format) -> str:
		createDate = self.gitFirstAuthDate
		return createDate.strftime(f) if createDate else ''

	def getCreateDateObj(self) -> Optional[date]:
		return self.gitFirstAuthDate

	@functools.cached_property
	def lastModifiedObj(self) -> datetime:
		"""Get last modified date from: (a) git history, or (b) system modified time."""
		path = self.fileName
		if self.isParentGitRepo():
			lastUpdated = PageNode.getGitFileLastAuthDate(path)
			if lastUpdated is not None:
				return lastUpdated
		return datetime.fromtimestamp(os.path.getmtime(path))

	@staticmethod
	def getGitFileLastAuthDate(path: str) -> Optional[datetime]:
		try:
			git_output = check_output(['git', 'log', '-n', '1', '--pretty=format:%aI', path]).decode()
			return datetime.fromisoformat(git_output)
		except Exception:
			return None

	@functools.cached_property
	def gitFirstAuthDate(self) -> Optional[date]:
		path = self.fileName
		if self.isParentGitRepo():
			try:
				git_output = check_output(['git', 'log', '--reverse', '--pretty=format:%aI', path]).decode()
				first_commit_date = git_output.splitlines()[0]
				return datetime.fromisoformat(first_commit_date).date()
			except Exception:
				return None
		return None

	def __getattr__(self, attr: str) -> None:
		"""Allows for checking whether page.some_property exists more easily (without `hasattr`)."""
		return None


class PyPageNode(PageNode):
	temporal_link: Optional[Callable[[Union[str, FsNode], bool], str]] = None

	@staticmethod
	def link(destination: Union[str, FsNode], pathOnly: bool = False) -> str:
		if PyPageNode.temporal_link is None:
			raise AltezaException('PyPageNode.temporal_link has not been set.')
		# pylint: disable=not-callable
		return PyPageNode.temporal_link(destination, pathOnly)

	def __init__(self, parent: Optional[DirNode], dirPath: str, fileName: str) -> None:
		super().__init__(parent, dirPath, fileName)
		self._pyPageOutput: Optional[str] = None  # to be generated (by pypage)

	@functools.cached_property
	def parents(self) -> deque[DirNode]:
		parents: deque[DirNode] = deque()
		parent: Optional[DirNode] = self.parentDir
		while parent is not None:
			parents.appendleft(parent)
			parent = parent.parent
		if self.isIndex:
			parents.pop()
		return parents

	def crumbs(self, sep: str = '&#9656;', end_with: bool = False, nav: bool = True) -> str:
		parents = self.parents
		if len(parents) == 0:
			return ''

		crumbs_html = ''
		if nav:
			crumbs_html = '<nav class="crumbs">'
		crumb_sep = f'<span class="crumb-sep"> {sep} </span>'
		crumbs_html += crumb_sep.join(
			(
				'<span class="crumb">'
				+ (
					f'<a class="crumb crumb-link" href="{PyPageNode.link(parent)}">{parent.titleOrName}</a>'
					if parent.hasIndexPage
					else f'<span class="crumb crumb-nolink">{parent.titleOrName}</span>'
				)
				+ '</span>'
			)
			for parent in parents
		)
		if end_with:
			crumbs_html += crumb_sep
		if nav:
			crumbs_html += '</nav>'
		return crumbs_html

	@property
	def output(self) -> str:
		if self._pyPageOutput is None:
			raise AltezaException('PyPage output has not been generated yet.')
		assert isinstance(self._pyPageOutput, str)
		return self._pyPageOutput

	@output.setter
	def output(self, htmlOutput: str) -> None:
		self._pyPageOutput = htmlOutput


def buildWikiUrl(label: str, base: str, end: str) -> str:
	# pylint: disable=unused-argument
	return PyPageNode.link(label)


class Md(PyPageNode):
	md = markdown.Markdown(
		# See: https://python-markdown.github.io/extensions/
		extensions=[
			# Extra extensions:
			'abbr',
			'attr_list',
			'def_list',
			'fenced_code',
			'footnotes',
			'md_in_html',
			'tables',
			# Standard extensions:
			'admonition',
			'codehilite',
			'meta',
			'mdx_breakless_lists',
			# "sane_lists",
			'mdx_truly_sane_lists',
			'smarty',  # not sure
			'toc',
			WikiLinkExtension(html_class='', build_url=buildWikiUrl),
		],
		extension_configs={'mdx_truly_sane_lists': {'nested_indent': 4}},
	)

	def __init__(self, parent: Optional[DirNode], dirPath: str, fileName: str) -> None:
		super().__init__(parent, dirPath, fileName)

		self.ideaDate: Optional[date] = None
		# Handle file names that start with a date:
		dateFragmentLength = len('YYYY-MM-DD-')
		if len(self.baseName) > dateFragmentLength:
			dateFragment_ = self.baseName[:dateFragmentLength]
			remainingBasename = self.baseName[dateFragmentLength:]
			if re.match('[0-9]{4}-[0-9]{2}-[0-9]{2}[- ]$', dateFragment_):
				dateFragment = dateFragment_[:-1]
				self.ideaDate = date.fromisoformat(dateFragment)
				self.realName: str = remainingBasename

		slugName = Md.slugify(self.realName)
		if slugName != self.realName:
			self.preSlugRealName: Optional[str] = self.realName
			self.env['title'] = self.realName
			self.realName = slugName

	class Result(NamedTuple):
		metadata: Dict[str, str]
		html: str

	@staticmethod
	def processMarkdown(text: str) -> Result:
		html: str = Md.md.convert(text)
		yamlFrontMatter: str = ''

		for name, lines in Md.md.Meta.items():  # type: ignore # pylint: disable=no-member
			yamlFrontMatter += f'{name} : {lines[0]} \n'
			for line in lines[1:]:
				yamlFrontMatter += ' ' * (len(name) + 3) + line + '\n'

		metadata = yaml.safe_load(yamlFrontMatter)
		if metadata is None:
			metadata = {}
		if not isinstance(metadata, dict):
			raise AltezaException('Expected yaml.safe_load to return a dict or None.')

		return Md.Result(metadata=metadata, html=html)

	@staticmethod
	def slugify(name: str) -> str:
		name = (
			unicodedata.normalize('NFKD', name)  # Normalize unicode characters
			.encode('ascii', 'ignore')
			.decode('ascii')
		)
		name = name.lower()
		name = re.sub(r'[^\w\s-]', '', name)  # Replace any non-word characters with a dash
		name = re.sub(r'[-\s]+', '-', name)  # Replace whitespace and repeated dashes with a single dash
		name = name.strip('-')  # Strip leading and trailing dashes
		return name


class NonMd(PyPageNode):
	def __init__(
		# pylint: disable=too-many-arguments, too-many-positional-arguments
		self,
		realName: str,
		rectifiedFileName: str,
		parent: Optional[DirNode],
		dirPath: str,
		fileName: str,
	) -> None:
		super().__init__(parent, dirPath, fileName)
		self.realName = realName
		self.rectifiedFileName: str = rectifiedFileName


class NameRegistry:
	def __init__(self, root: DirNode, skipForRegistry: Callable[[str], bool]) -> None:
		allFilesMulti: DefaultDict[str, Set[FileNode]] = defaultdict(set)

		def walk(node: DirNode) -> None:
			for fileNode in node.files:
				if not skipForRegistry(fileNode.fileName):
					allFilesMulti[fileNode.linkName].add(fileNode)
					if isinstance(fileNode, Md):
						if fileNode.preSlugRealName is not None:
							allFilesMulti[fileNode.preSlugRealName].add(fileNode)
			for d in node.subDirs:
				walk(d)

		walk(root)

		self.allFiles: Dict[str, FileNode] = {}
		for name, fileNodes in allFilesMulti.items():
			assert len(fileNodes) >= 1
			if len(fileNodes) > 1:
				self.errorOut(name, fileNodes)
			self.allFiles[name] = fileNodes.pop()

	def lookup(self, name: str) -> FileNode:
		if name not in self.allFiles:
			print(f'Link error: `{name}` was not found in the name registry.')
			raise AltezaException(f'Link error: {name}')

		return self.allFiles[name]

	@staticmethod
	def errorOut(name: str, fileNodes: Set[FileNode]) -> None:
		raise AltezaException(
			f"Error: The name '{name}' has multiple matches:\n"
			+ '  \n'.join(f' {fileNode.fullPath}' for fileNode in fileNodes)
		)

	def __repr__(self) -> str:
		return (
			'Name Registry:\n  '
			+ '\n  '.join(f'{k}: {v} {Fore.grey_39}@ {v.fullPath}{Style.reset}' for k, v in self.allFiles.items())
			+ '\n'
		)


@dataclass
class FsCrawlResult:
	rootDir: DirNode
	nameRegistry: NameRegistry


class Fs:
	configFileName: str = '__config__.py'
	ignoreAbsPaths: List[str] = []

	@staticmethod
	def readfile(file_path: str) -> str:
		with open(file_path, 'r', encoding='utf-8') as someFile:
			return someFile.read()

	@staticmethod
	def isHidden(name: str) -> bool:
		return name.startswith('.')

	@staticmethod
	def shouldIgnoreStandard(name: str) -> bool:
		if Fs.isHidden(name):
			return True
		if name in {'__pycache__'}:
			return True
		_, fileExt = os.path.splitext(name)
		if fileExt == '.pyc':
			return True
		if name != Fs.configFileName and fileExt == '.py':
			return True
		return False

	@staticmethod
	def defaultShouldIgnore(name: str, parentPath: str, isDir: bool) -> bool:
		# pylint: disable=unused-argument
		if Fs.shouldIgnoreStandard(name):
			return True

		fullPath = os.path.abspath(os.path.join(parentPath, name))
		for ignoreAbsPath in Fs.ignoreAbsPaths:
			if ignoreAbsPath in fullPath:
				return True

		return False

	@staticmethod
	def defaultSkipForRegistry(name: str) -> bool:
		if name == Fs.configFileName:
			return True
		return False

	@staticmethod
	def crawl(
		# Signature -- shouldIgnore(name: str, parentPath: str, isDir: bool) -> bool
		shouldIgnore: Callable[[str, str, bool], bool] = defaultShouldIgnore,
		skipForRegistry: Callable[[str], bool] = defaultSkipForRegistry,
	) -> FsCrawlResult:
		"""
		Crawl the current directory. Construct & return an FsNode tree and NameRegistry.
		"""
		dirPath: str = os.curdir

		rootDir: DirNode = DirNode(None, dirPath, shouldIgnore)
		nameRegistry = NameRegistry(rootDir, skipForRegistry)

		return FsCrawlResult(rootDir, nameRegistry)
