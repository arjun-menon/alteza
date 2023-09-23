import os
import sys
from collections import defaultdict
from typing import Optional, List, Dict, DefaultDict, Set, Tuple, Callable

# pyre-ignore[21]
from colored import Style, Fore  # type: ignore [import]

from core.ingest_markdown import Markdown, processMarkdownFile

colored_logs = True

config_py_name = "__config__"
config_py_file = "__config__.py"


class FsNode(object):
    def __init__(self, dirPath: str, fileName: Optional[str]) -> None:
        self.fileName: Optional[str] = fileName
        self.dirName: str = os.path.basename(dirPath)
        self.fullPath: str = (
            (os.curdir if dirPath == "" else dirPath)
            if isinstance(self, DirNode) or type(fileName) is not str
            else os.path.join(dirPath, fileName)
        )
        self.shouldPublish: bool = False

    def __repr__(self) -> str:
        return self.colorize(self.fullPath)

    def colorize(self, r: str) -> str:
        if colored_logs:
            if self.shouldPublish:
                r = f"{Style.bold}{Fore.spring_green_2b}{r}{Style.reset}"
        return r


class FileNode(FsNode):  # pyre-ignore[13]
    def __init__(self, dirPath: str, fileName: str) -> None:
        super().__init__(dirPath, fileName)
        self.fileName: str = fileName  # for typing
        split_name = os.path.splitext(fileName)
        self.basename: str = split_name[0]
        self.extension: str = split_name[1]
        self.absoluteFilePath: str = os.path.join(os.getcwd(), self.fullPath)

        self.isPage: bool = False
        self.htmlPage: Optional[str] = None
        self.markdown: Optional[Markdown] = None
        self.htmlOutput: Optional[str] = None

        self.hmm: str

    def colorize(self, r: str) -> str:
        if colored_logs:
            if self.isPage and self.shouldPublish:
                r = f"{Fore.spring_green_1}{r}{Style.reset}"
            elif self.markdown:
                r = f"{Fore.purple_4b}{r}{Style.reset}"
        return r

    def __repr__(self) -> str:
        r = f"{self.fileName}"
        r = self.colorize(r)
        r = super().colorize(r)
        return r


class DirNode(FsNode):
    def __init__(
        self,
        dirPath: str,
        # shouldIgnore(name: str, isDir: bool) -> bool
        shouldIgnore: Callable[[str, bool], bool],
    ) -> None:
        _, subDirNames, fileNames = next(os.walk(dirPath))
        dirPath = "" if dirPath == os.curdir else dirPath
        super().__init__(dirPath, None)

        self.files: List[FileNode] = [
            FileNode(dirPath, fileName)
            for fileName in fileNames
            if not shouldIgnore(fileName, False)
        ]
        self.subDirs: List[DirNode] = [
            DirNode(os.path.join(dirPath, subDirName), shouldIgnore)
            for subDirName in subDirNames
            if not shouldIgnore(subDirName, True)
        ]


def displayDir(dirNode: DirNode, indent: int = 0) -> str:
    return (
        (" " * 2 * indent)
        + "%s -> %s\n" % (dirNode, dirNode.files)
        + "".join(displayDir(subDir, indent + 1) for subDir in dirNode.subDirs)
    )


class NameRegistry(object):
    def __init__(self, root: DirNode, skipForRegistry: Callable[[str], bool]) -> None:
        self.allFiles: Dict[str, FileNode] = {}

        allFilesMulti: DefaultDict[str, Set[FileNode]] = defaultdict(set)

        def record(fileNode: FileNode) -> None:
            if fileNode.isPage:
                allFilesMulti[fileNode.basename].add(fileNode)
            else:
                allFilesMulti[fileNode.fileName].add(fileNode)

        def walk(node: DirNode) -> None:
            for f in node.files:
                if not defaultSkipForRegistry(f.fileName):
                    record(f)
            for d in node.subDirs:
                walk(d)

        walk(root)

        for name, fileNodes in allFilesMulti.items():
            assert len(fileNodes) >= 1
            if len(fileNodes) > 1:
                self.errorOut(name, fileNodes)

            self.allFiles[name] = fileNodes.pop()

    @staticmethod
    def errorOut(name: str, fileNodes: Set[FileNode]) -> None:
        print(
            f"Error: The name '{name}' has multiple matches:\n"
            + "  \n".join(f" {fileNode.fullPath}" for fileNode in fileNodes)
        )
        sys.exit(1)

    def __repr__(self) -> str:
        return (
            f"Name Registry:\n  "
            + "\n  ".join(
                f"{k}: {v} {Fore.grey_39}@ {v.fullPath}{Style.reset}"
                for k, v in self.allFiles.items()
            )
            + "\n"
        )


def readPages(node: FsNode) -> None:
    if isinstance(node, DirNode):
        d: DirNode = node
        for aDir in node.subDirs:
            readPages(aDir)
        for aFile in node.files:
            readPages(aFile)

        if any(aDir.shouldPublish for aDir in node.subDirs) or any(
            aFile.shouldPublish for aFile in node.files
        ):
            d.shouldPublish = True

    elif isinstance(node, FileNode):
        f: FileNode = node
        if f.extension == ".md":
            f.markdown = processMarkdownFile(f.fullPath)
            f.isPage = True
            f.shouldPublish = bool(f.markdown.metadata.get("public", False))
            # f.shouldPublish could be overriden during pypage invocation
        elif f.extension == ".html":
            with open(f.fullPath, "r") as htmlFile:
                f.htmlPage = htmlFile.read()
            f.isPage = True
            # f.shouldPublish will be determined later after pypage invocation


def isHidden(name: str) -> bool:
    return name.startswith(".")


def defaultShouldIgnore(name: str, isDir: bool) -> bool:
    if isHidden(name):
        return True
    if name in {"__pycache__"}:
        return True
    basename, fileExt = os.path.splitext(name)
    if fileExt == ".pyc":
        return True
    return False


def defaultSkipForRegistry(name: str) -> bool:
    if name == config_py_file:
        return True
    return False


def fs_crawl(
    # Signature -- shouldIgnore(name: str, isDir: bool) -> bool
    shouldIgnore: Callable[[str, bool], bool] = defaultShouldIgnore,
    skipForRegistry: Callable[[str], bool] = defaultSkipForRegistry,
) -> Tuple[DirNode, NameRegistry]:
    """
    Crawl the current directory. Construct & return an FsNode tree and NameRegistry.
    """
    dirPath: str = os.curdir
    rootDir: DirNode = DirNode(
        dirPath, lambda s, b: shouldIgnore(s, b) or defaultShouldIgnore(s, b)
    )

    readPages(rootDir)  # This must occur before NameRegistry creation.

    nameRegistry = NameRegistry(
        rootDir, lambda s: skipForRegistry(s) and defaultSkipForRegistry(s)
    )

    return rootDir, nameRegistry
