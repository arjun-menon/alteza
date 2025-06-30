import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Callable, DefaultDict, Set, Dict, List, Any
from colored import Fore, Style  # type: ignore
from tqdm import tqdm  # type: ignore
from .fs import DirNode, FileNode, Md, AltezaException, PageNode


class ProgressBar:
	pbar: Optional[tqdm] = None

	@classmethod
	def start(cls, total: int, desc: str = '') -> None:
		assert cls.pbar is None
		if not sys.stdin.isatty():
			print(f'{desc}...')
			return
		cls.pbar = tqdm(total=total, desc=desc)

	@classmethod
	def increment(cls) -> None:
		if cls.pbar is not None:
			cls.pbar.update(1)

	@classmethod
	def finish(cls, total: int) -> None:
		if cls.pbar is not None:
			current_progress_n: int = ProgressBar.pbar.n  # type: ignore
			cls.pbar.update(total - current_progress_n)
			ProgressBar.close()

	@classmethod
	def write(cls, *args: Any, sep: str = ' ', end: str = '\n') -> None:
		if cls.pbar is None:
			print(*args, sep=sep, end=end)
			return
		message = sep.join(str(arg) for arg in args)
		assert cls.pbar is not None
		cls.pbar.write(message, end=end)

	@classmethod
	def close(cls) -> None:
		if cls.pbar is not None:
			cls.pbar.close()
			cls.pbar = None


pr: Callable[..., None] = ProgressBar.write


class NameRegistry:
	def __init__(self, root: DirNode, skipForRegistry: Callable[[str], bool]) -> None:
		self.pageCount = 0
		allFilesMulti: DefaultDict[str, Set[FileNode]] = defaultdict(set)

		def walk(node: DirNode) -> None:
			for fileNode in node.files:
				if not skipForRegistry(fileNode.fileName):
					allFilesMulti[fileNode.linkName].add(fileNode)
					if isinstance(fileNode, Md):
						if fileNode.preSlugRealName is not None:
							allFilesMulti[fileNode.preSlugRealName].add(fileNode)
				if isinstance(fileNode, PageNode):
					self.pageCount += 1
			for d in node.subDirs:
				walk(d)

		walk(root)

		self.allFiles: Dict[str, FileNode] = {}
		for name, fileNodes in allFilesMulti.items():
			assert len(fileNodes) >= 1
			if len(fileNodes) > 1:
				raise AltezaException(
					f"Error: The name '{name}' has multiple matches:\n"
					+ '  \n'.join(f' {fileNode.fullPath}' for fileNode in fileNodes)
				)
			self.allFiles[name] = fileNodes.pop()

	def lookup(self, name: str) -> FileNode:
		if name not in self.allFiles:
			pr(f'Link error: `{name}` was not found in the name registry.')
			raise AltezaException(f'Link error: {name}')

		return self.allFiles[name]

	def __repr__(self) -> str:
		return (
			'Name Registry:\n  '
			+ '\n  '.join(f'{k}: {v} {Fore.grey_39}@ {v.fullPath}{Style.reset}' for k, v in self.allFiles.items())
			+ '\n'
		)


@dataclass
class CrawlResult:
	rootDir: DirNode
	nameRegistry: NameRegistry


def isHidden(name: str) -> bool:
	return name.startswith('.')


def shouldIgnoreStandard(name: str) -> bool:
	if isHidden(name):
		return True
	if name in {'__pycache__'}:
		return True
	_, fileExt = os.path.splitext(name)
	if fileExt == '.pyc':
		return True
	if name != CrawlConfig.configFileName and fileExt == '.py':
		return True
	return False


def defaultShouldIgnore(name: str, parentPath: str, isDir: bool) -> bool:
	# pylint: disable=unused-argument
	if shouldIgnoreStandard(name):
		return True

	fullPath = os.path.abspath(os.path.join(parentPath, name))
	for ignoreAbsPath in CrawlConfig.ignoreAbsPaths:
		if ignoreAbsPath in fullPath:
			return True

	return False


def defaultSkipForRegistry(name: str) -> bool:
	if name == CrawlConfig.configFileName:
		return True
	return False


def crawl(
	# Signature -- shouldIgnore(name: str, parentPath: str, isDir: bool) -> bool
	shouldIgnore: Callable[[str, str, bool], bool] = defaultShouldIgnore,
	skipForRegistry: Callable[[str], bool] = defaultSkipForRegistry,
) -> CrawlResult:
	"""
	Crawl the current directory. Construct & return an FsNode tree and NameRegistry.
	"""
	dirPath: str = os.curdir

	rootDir: DirNode = DirNode(None, dirPath, shouldIgnore)
	nameRegistry = NameRegistry(rootDir, skipForRegistry)

	return CrawlResult(rootDir, nameRegistry)


class CrawlConfig:  # pyre-ignore[13]
	# pylint: disable=too-few-public-methods
	configFileName: str
	ignoreAbsPaths: List[str]
