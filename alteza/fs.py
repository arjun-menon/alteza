import re
import os
import yaml
import markdown
from collections import defaultdict
from datetime import date, datetime
from subprocess import check_output, CalledProcessError, STDOUT
from typing import (
    Optional,
    List,
    Dict,
    DefaultDict,
    Set,
    Tuple,
    Callable,
    Union,
    NamedTuple,
)
from colored import Style, Fore  # type: ignore

colored_logs = True
config_py_file = "__config__.py"


class FsNode:
    def __init__(
        self, parent: Optional["FsNode"], dirPath: str, fileName: Optional[str]
    ) -> None:
        self.parent = parent
        self.fileName: Optional[str] = fileName
        self.dirName: str = os.path.basename(dirPath)
        self.fullPath: str = (
            (os.curdir if dirPath == "" else dirPath)
            if isinstance(self, DirNode) or not isinstance(fileName, str)
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

    def setNodeAsPublic(self) -> None:
        self.shouldPublish = True

    def makePublic(self) -> None:
        runOnFsNodeAndAscendantNodes(self, lambda fsNode: fsNode.setNodeAsPublic())


class FileNode(FsNode):
    def __init__(self, parent: Optional[FsNode], dirPath: str, fileName: str) -> None:
        super().__init__(parent, dirPath, fileName)
        self.fileName: str = fileName  # for typing
        split_name = os.path.splitext(fileName)
        self.basename: str = split_name[0]
        self.extension: str = split_name[1]
        self.absoluteFilePath: str = os.path.join(os.getcwd(), self.fullPath)

        self.page: Optional[Union[Md, NonMd]] = None
        self.pageName: str = self.basename  # to be overwritten selectively
        self.pyPageOutput: Optional[str] = None  # to be generated (by pypage)

    def colorize(self, r: str) -> str:
        if colored_logs:
            if self.page is not None and self.shouldPublish:
                r = f"{Fore.spring_green_1}{r}{Style.reset}"
            elif isinstance(self.page, Md):
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
        parent: Optional[FsNode],
        dirPath: str,
        # shouldIgnore(name: str, isDir: bool) -> bool
        shouldIgnore: Callable[[str, bool], bool],
    ) -> None:
        _, subDirNames, fileNames = next(os.walk(dirPath))
        dirPath = "" if dirPath == os.curdir else dirPath
        super().__init__(parent, dirPath, None)

        self.files: List[FileNode] = [
            FileNode(self, dirPath, fileName)
            for fileName in fileNames
            if not shouldIgnore(fileName, False)
        ]
        self.subDirs: List[DirNode] = [
            DirNode(self, os.path.join(dirPath, subDirName), shouldIgnore)
            for subDirName in subDirNames
            if not shouldIgnore(subDirName, True)
        ]


def displayDir(dirNode: DirNode, indent: int = 0) -> str:
    return (
        (" " * 2 * indent)
        + f"{dirNode} -> {dirNode.files}\n"
        + "".join(displayDir(subDir, indent + 1) for subDir in dirNode.subDirs)
    )


class AltezaException(Exception):
    """Alteza Exceptions"""


class NameRegistry:
    def __init__(self, root: DirNode, skipForRegistry: Callable[[str], bool]) -> None:
        self.allFiles: Dict[str, FileNode] = {}
        self.skipForRegistry = skipForRegistry

        allFilesMulti: DefaultDict[str, Set[FileNode]] = defaultdict(set)

        def record(fileNode: FileNode) -> None:
            allFilesMulti[fileNode.fileName].add(fileNode)

            if fileNode.page is not None:
                allFilesMulti[fileNode.basename].add(fileNode)  # maybe delete this

                if fileNode.basename != fileNode.pageName:
                    allFilesMulti[fileNode.pageName].add(fileNode)

        def walk(node: DirNode) -> None:
            for f in node.files:
                if not self.skipForRegistry(f.fileName):
                    record(f)
            for d in node.subDirs:
                walk(d)

        walk(root)

        # TODO: Handle index pages specially here

        for name, fileNodes in allFilesMulti.items():
            assert len(fileNodes) >= 1
            if len(fileNodes) > 1:
                self.errorOut(name, fileNodes)

            self.allFiles[name] = fileNodes.pop()

    def lookup(self, name: str) -> FileNode:
        if name not in self.allFiles:
            print(
                f"Link error: `{name}` was not found in the name registry."
                # f" The {self}"
            )
            raise AltezaException(f"Link error: {name}")

        return self.allFiles[name]

    @staticmethod
    def errorOut(name: str, fileNodes: Set[FileNode]) -> None:
        raise AltezaException(
            f"Error: The name '{name}' has multiple matches:\n"
            + "  \n".join(f" {fileNode.fullPath}" for fileNode in fileNodes)
        )

    def __repr__(self) -> str:
        return (
            "Name Registry:\n  "
            + "\n  ".join(
                f"{k}: {v} {Fore.grey_39}@ {v.fullPath}{Style.reset}"
                for k, v in self.allFiles.items()
            )
            + "\n"
        )


class Page:
    def __init__(self, f: FileNode) -> None:
        self.lastUpdated: datetime = self.getLastUpdated(f.fullPath)

    @staticmethod
    def getLastUpdated(path: str) -> datetime:
        """Get last modified date from: (a) git history, or (b) system modified time."""
        if Page.isGitRepo():
            lastUpdated = Page.getGitFileLastAuthDate(path)
            if lastUpdated is not None:
                return lastUpdated
        return datetime.fromtimestamp(os.path.getmtime(path))

    @staticmethod
    def isGitRepo() -> bool:
        try:
            check_output(["git", "status"], stderr=STDOUT).decode()
            return True
        except CalledProcessError:
            return False

    @staticmethod
    def getGitFileLastAuthDate(path: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(
                check_output(
                    ["git", "log", "-n", "1", "--pretty=format:%aI", path]
                ).decode()
            )
        except Exception:
            return None


class Md(Page):
    def __init__(self, f: FileNode) -> None:
        super().__init__(f)
        self.draftDate: Optional[date] = None

        # Handle file names that start with a date
        dateFragmentLength = len("YYYY-MM-DD-")
        if len(f.basename) > dateFragmentLength:
            dateFragment_ = f.basename[:dateFragmentLength]
            remainingBasename = f.basename[dateFragmentLength:]
            if re.match("[0-9]{4}-[0-9]{2}-[0-9]{2}-$", dateFragment_):
                dateFragment = dateFragment_[:-1]
                self.draftDate = date.fromisoformat(dateFragment)
                f.pageName = remainingBasename

    class Result(NamedTuple):
        metadata: Dict[str, str]
        html: str

    @staticmethod
    def processMarkdown(text: str) -> Result:
        md = markdown.Markdown(extensions=["meta", "codehilite"])
        html: str = md.convert(text)
        yamlFrontMatter: str = ""

        for name, lines in md.Meta.items():  # type: ignore # pylint: disable=no-member
            yamlFrontMatter += f"{name} : {lines[0]} \n"
            for line in lines[1:]:
                yamlFrontMatter += " " * (len(name) + 3) + line + "\n"

        metadata = yaml.safe_load(yamlFrontMatter)
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise AltezaException("Expected yaml.safe_load to return a dict or None.")

        return Md.Result(metadata=metadata, html=html)


class NonMd(Page):
    def __init__(self, f: FileNode, pageName: str, rectifiedFileName: str) -> None:
        super().__init__(f)
        f.pageName = pageName
        self.rectifiedFileName: str = rectifiedFileName

    @staticmethod
    def isNonMdPyPageFile(fileNode: FileNode) -> Optional["NonMd"]:
        """Check if fileNode is a non-Md page (that needs to be processed with pypage).
        If is a non-Md page, we return a NonMd object.
        If it is not, we return None."""
        if ".py." in fileNode.fileName:
            pySubExtPos = fileNode.fileName.find(".py.")
            remainingExt = fileNode.fileName[pySubExtPos:]
            expectedRemainingExt = ".py" + fileNode.extension
            if remainingExt == expectedRemainingExt:
                # The condition above passing indicates this is a NonMd page file.
                realPageName = fileNode.fileName[:pySubExtPos]
                rectifiedFileName = realPageName + fileNode.extension
                return NonMd(fileNode, realPageName, rectifiedFileName)
        return None


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
            f.page = Md(f)
        else:
            f.page = NonMd.isNonMdPyPageFile(f)


def readfile(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as someFile:
        return someFile.read()


def runOnFsNodeAndAscendantNodes(
    startingNode: FsNode, fn: Callable[[FsNode], None]
) -> None:
    def walk(node: FsNode) -> None:
        fn(node)
        if node.parent is not None:
            walk(node.parent)

    walk(startingNode)


def isHidden(name: str) -> bool:
    return name.startswith(".")


def defaultShouldIgnore(name: str, isDir: bool) -> bool:
    # pylint: disable=unused-argument
    if isHidden(name):
        return True
    if name in {"__pycache__"}:
        return True
    _, fileExt = os.path.splitext(name)
    if fileExt == ".pyc":
        return True
    if name != config_py_file and fileExt == ".py":
        return True
    return False


def defaultSkipForRegistry(name: str) -> bool:
    if name == config_py_file:
        return True
    return False


def fsCrawl(
    # Signature -- shouldIgnore(name: str, isDir: bool) -> bool
    shouldIgnore: Callable[[str, bool], bool] = defaultShouldIgnore,
    skipForRegistry: Callable[[str], bool] = defaultSkipForRegistry,
) -> Tuple[DirNode, NameRegistry]:
    """
    Crawl the current directory. Construct & return an FsNode tree and NameRegistry.
    """
    dirPath: str = os.curdir
    rootDir: DirNode = DirNode(
        None, dirPath, lambda s, b: shouldIgnore(s, b) or defaultShouldIgnore(s, b)
    )

    readPages(rootDir)  # This must occur before NameRegistry creation.

    nameRegistry = NameRegistry(
        rootDir, lambda s: skipForRegistry(s) and defaultSkipForRegistry(s)
    )

    return rootDir, nameRegistry
