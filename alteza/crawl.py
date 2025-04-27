import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, DefaultDict, Set, Dict, List
from colored import Fore, Style  # type: ignore
from alteza.fs import DirNode, FileNode, Md, AltezaException


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
