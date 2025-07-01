import functools
import os
import re
import unicodedata
from collections import deque
from datetime import date, datetime
from typing import (
	Any,
	Callable,
	Dict,
	Union,
	Iterator,
	List,
	NamedTuple,
	Optional,
	Sequence,
	Tuple,
)

import markdown
import yaml
from colored import Fore, Style  # type: ignore
from markdown.extensions.wikilinks import WikiLinkExtension

from .util import AltezaException, PublicNodeCounts


class FsNode:
	publicNodeCounts: Optional[PublicNodeCounts] = None  # Set by the Content class.

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
		assert FsNode.publicNodeCounts is not None
		publicNodeCounts: PublicNodeCounts = FsNode.publicNodeCounts
		if not self.shouldPublish:
			if isinstance(self, FileNode):
				publicNodeCounts.fileCount += 1
			else:
				publicNodeCounts.dirCount += 1
		self.shouldPublish = True

	def makePublic(self) -> None:
		self.runOnFsNodeAndAscendantNodes(self, lambda fsNode: fsNode.setNodeAsPublic())

	@staticmethod
	def runOnFsNodeAndAscendantNodes(startingNode: 'FsNode', fn: Callable[['FsNode'], None]) -> None:
		def walk(node: FsNode) -> None:
			fn(node)
			if node.parent is not None:
				walk(node.parent)

		walk(startingNode)


class FileNode(FsNode):
	# pylint: disable=too-many-instance-attributes
	current_pypage_node_being_processed: Optional['PyPageNode'] = None

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

		# Populated by Driver.analyzeGitHistory:
		self.gitFirstCommitDate: Optional[datetime] = None
		self.gitLastCommitDate: Optional[datetime] = None

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

	@staticmethod
	def relativePath(
		srcFile: 'FileNode', dstFile: 'FileNode', noMdCorrection: bool = False, useUrlName: bool = True
	) -> str:
		dstFileName = FileNode.getFileUrlName(dstFile) if useUrlName else dstFile.fileName

		srcPath = FileNode.splitPath(srcFile.fullPath)[:-1]
		dstPath = FileNode.splitPath(dstFile.fullPath)[:-1]
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
		if isinstance(srcFile, Md) and not srcFile.isIndex and not noMdCorrection:
			relativePath = ['..'] + relativePath

		relativePathStr = os.path.join('', *relativePath)
		return relativePathStr

	@staticmethod
	def getFileUrlName(dstFile: 'FileNode') -> str:
		if dstFile.isIndex:
			return ''
		if isinstance(dstFile, Md):
			return dstFile.realName
		if isinstance(dstFile, NonMd):
			return dstFile.rectifiedFileName
		return dstFile.fileName

	@staticmethod
	def splitPath(path: str) -> List[str]:
		head, tail = os.path.split(path)
		if head == '':
			return [path]
		return FileNode.splitPath(head) + [tail]

	#
	# Git & Date related methods
	#

	default_date_format: str = '%Y %b %-d'
	default_datetime_format: str = default_date_format + ' at %-H:%M %p'

	def ideaDate(self, f: str = default_date_format) -> str:
		ideaDate = self.ideaDateObj()
		return ideaDate.strftime(f) if ideaDate else ''

	def ideaDateObj(self) -> Optional[date]:
		if isinstance(self, Md):
			if self._ideaDate is not None:
				return self._ideaDate
		return self.gitFirstCommitDate

	def firstCommitDate(self, f: str = default_date_format) -> str:
		createDate = self.gitFirstCommitDate
		return createDate.strftime(f) if createDate else ''

	def firstCommitDateObj(self) -> Optional[date]:
		return self.gitFirstCommitDate

	def lastModified(self, f: str = default_datetime_format) -> str:
		# The formatting below might only work on Linux. https://stackoverflow.com/a/29980406/908430
		return self.lastModifiedObj.strftime(f)

	@functools.cached_property
	def lastModifiedObj(self) -> datetime:
		"""Get the last modified date from: (a) git history, or (b) system modified time."""
		if self.gitLastCommitDate is not None:
			return self.gitLastCommitDate
		return datetime.fromtimestamp(os.path.getmtime(self.absoluteFilePath))

	#
	# Visualization
	#

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
	def title(self) -> str:
		title: Optional[str] = None
		if self.indexPage and 'title' in self.indexPage.env:
			title = self.indexPage.title
		if self.configTitle:
			title = self.configTitle
		if not title:
			title = self.dirName
		return title

	@title.setter
	def title(self, configTitle: str) -> None:
		self.configTitle = configTitle

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
					f'<a class="crumb crumb-link" href="{PyPageNode.link(parent)}">{parent.title}</a>'
					if parent.hasIndexPage
					else f'<span class="crumb crumb-nolink">{parent.title}</span>'
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

		self._ideaDate: Optional[date] = None
		# Handle file names that start with a date:
		dateFragmentLength = len('YYYY-MM-DD-')
		if len(self.baseName) > dateFragmentLength:
			dateFragment_ = self.baseName[:dateFragmentLength]
			remainingBasename = self.baseName[dateFragmentLength:]
			if re.match('[0-9]{4}-[0-9]{2}-[0-9]{2}[- ]$', dateFragment_):
				dateFragment = dateFragment_[:-1]
				self._ideaDate = date.fromisoformat(dateFragment)
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
