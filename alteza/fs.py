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
    NamedTuple,
)
from colored import Style, Fore  # type: ignore

colored_logs = True


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
        Fs.runOnFsNodeAndAscendantNodes(self, lambda fsNode: fsNode.setNodeAsPublic())


class FileNode(FsNode):
    @staticmethod
    def construct(parent: Optional[FsNode], dirPath: str, fileName: str) -> "FileNode":
        """Constructs an object of type FileNode or one of its subclasses.
        Check if fileName needs to be processed with pypage.
            If is a Md page, we return a Md object.
            If is a non-Md page, we return a NonMd object.
        If it is neither, we return a FileNode object.
        """
        _, extension = FileNode.splitFileName(fileName)

        if extension == ".md":
            return Md(parent, dirPath, fileName)

        if ".py." in fileName:
            pySubExtPos = fileName.find(".py.")
            remainingExt = fileName[pySubExtPos:]
            expectedRemainingExt = ".py" + extension
            if remainingExt == expectedRemainingExt:
                # The condition above passing indicates this is a NonMd page file.
                realName = fileName[:pySubExtPos]
                rectifiedFileName = realName + extension
                return NonMd(realName, rectifiedFileName, parent, dirPath, fileName)

        return FileNode(parent, dirPath, fileName)

    @staticmethod
    def splitFileName(fileName: str) -> Tuple[str, str]:
        return os.path.splitext(fileName)

    def __init__(self, parent: Optional[FsNode], dirPath: str, fileName: str) -> None:
        """Do not use this constructor directly. Use the static method construct instead."""
        super().__init__(parent, dirPath, fileName)
        baseName, extension = FileNode.splitFileName(fileName)
        self.absoluteFilePath: str = os.path.join(os.getcwd(), self.fullPath)
        self.fileName: str = fileName
        self.extension: str = extension
        self.baseName: str = baseName
        self.realName: str = self.baseName  # to be overwritten selectively

    def getLinkName(self) -> str:
        if self.realName == "index" and (self.extension in (".md", ".html")):
            # Index pages (i.e. `index.md` or `index[.py].html` files):
            rectifiedParentDirName: str = self.getParentDir().getRectifiedName()
            return rectifiedParentDirName

        if isinstance(self, Md) or (
            isinstance(self, NonMd) and self.extension == ".html"
        ):
            return self.realName

        if isinstance(self, NonMd):
            return self.rectifiedFileName

        return self.fileName

    def colorize(self, r: str) -> str:
        if colored_logs:
            if isinstance(self, PyPageNode) is not None and self.shouldPublish:
                r = f"{Fore.spring_green_1}{r}{Style.reset}"
            elif isinstance(self, Md):
                r = f"{Fore.purple_4b}{r}{Style.reset}"
        return r

    def __repr__(self) -> str:
        r = f"{self.fileName}"
        r = self.colorize(r)
        r = super().colorize(r)
        return r

    def getParentDir(self) -> "DirNode":
        # Note: The parent of a FileNode is always a DirNode (and never None).
        assert isinstance(self.parent, DirNode)
        parentDir: DirNode = self.parent
        return parentDir


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
            FileNode.construct(self, dirPath, fileName)
            for fileName in fileNames
            if not shouldIgnore(fileName, False)
        ]
        self.subDirs: List[DirNode] = [
            DirNode(self, os.path.join(dirPath, subDirName), shouldIgnore)
            for subDirName in subDirNames
            if not shouldIgnore(subDirName, True)
        ]

    def getRectifiedName(self) -> str:
        # Note: if `dirName` is an empty string (""), that means we're at the root (/).
        return self.dirName if len(self.dirName) > 0 else "/"

    @staticmethod
    def _displayDir(dirNode: "DirNode", indent: int = 0) -> str:
        return (
            (" " * 2 * indent)
            + f"{dirNode} -> {dirNode.files}\n"
            + "".join(
                DirNode._displayDir(subDir, indent + 1) for subDir in dirNode.subDirs
            )
        )

    def displayDir(self) -> str:
        return self._displayDir(self)


class AltezaException(Exception):
    """Alteza Exceptions"""


class PageNode(FileNode):
    def __init__(self, parent: Optional[FsNode], dirPath: str, fileName: str) -> None:
        super().__init__(parent, dirPath, fileName)
        self.lastUpdated: datetime = self.getLastUpdated(self.fullPath)

    @staticmethod
    def getLastUpdated(path: str) -> datetime:
        """Get last modified date from: (a) git history, or (b) system modified time."""
        if PageNode.isGitRepo():
            lastUpdated = PageNode.getGitFileLastAuthDate(path)
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


class PyPageNode(PageNode):
    def __init__(self, parent: Optional[FsNode], dirPath: str, fileName: str) -> None:
        super().__init__(parent, dirPath, fileName)
        self._pyPageOutput: Optional[str] = None  # to be generated (by pypage)

    def setPyPageOutput(self, output: str) -> None:
        self._pyPageOutput = output

    def getPyPageOutput(self) -> str:
        if self._pyPageOutput is None:
            raise AltezaException("PyPage output has not been generated yet.")
        assert isinstance(self._pyPageOutput, str)
        return self._pyPageOutput


class Md(PyPageNode):
    def __init__(self, parent: Optional[FsNode], dirPath: str, fileName: str) -> None:
        super().__init__(parent, dirPath, fileName)

        self.ideaDate: Optional[date] = None
        # Handle file names that start with a date:
        dateFragmentLength = len("YYYY-MM-DD-")
        if len(self.baseName) > dateFragmentLength:
            dateFragment_ = self.baseName[:dateFragmentLength]
            remainingBasename = self.baseName[dateFragmentLength:]
            if re.match("[0-9]{4}-[0-9]{2}-[0-9]{2}-$", dateFragment_):
                dateFragment = dateFragment_[:-1]
                self.ideaDate = date.fromisoformat(dateFragment)
                self.realName: str = remainingBasename

    class Result(NamedTuple):
        metadata: Dict[str, str]
        html: str

    @staticmethod
    def processMarkdown(text: str) -> Result:
        md = markdown.Markdown(
            # See: https://python-markdown.github.io/extensions/
            extensions=[
                # Extra extensions:
                "abbr",
                "attr_list",
                "def_list",
                "fenced_code",
                "footnotes",
                "md_in_html",
                "tables",
                # Standard extensions:
                "admonition",
                "codehilite",
                "meta",
                "sane_lists",
                "smarty",  # not sure
                "toc",
            ]
        )
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


class NonMd(PyPageNode):
    def __init__(
        # pylint: disable=too-many-arguments
        self,
        realName: str,
        rectifiedFileName: str,
        parent: Optional[FsNode],
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
                    allFilesMulti[fileNode.getLinkName()].add(fileNode)
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


class Fs:
    configFileName: str = "__config__.py"

    @staticmethod
    def readfile(file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8") as someFile:
            return someFile.read()

    @staticmethod
    def runOnFsNodeAndAscendantNodes(
        startingNode: FsNode, fn: Callable[[FsNode], None]
    ) -> None:
        def walk(node: FsNode) -> None:
            fn(node)
            if node.parent is not None:
                walk(node.parent)

        walk(startingNode)

    @staticmethod
    def _isHidden(name: str) -> bool:
        return name.startswith(".")

    @staticmethod
    def _defaultShouldIgnore(name: str, isDir: bool) -> bool:
        # pylint: disable=unused-argument
        if Fs._isHidden(name):
            return True
        if name in {"__pycache__"}:
            return True
        _, fileExt = os.path.splitext(name)
        if fileExt == ".pyc":
            return True
        if name != Fs.configFileName and fileExt == ".py":
            return True
        return False

    @staticmethod
    def _defaultSkipForRegistry(name: str) -> bool:
        if name == Fs.configFileName:
            return True
        return False

    @staticmethod
    def _crawl(
        # Signature -- shouldIgnore(name: str, isDir: bool) -> bool
        shouldIgnore: Callable[[str, bool], bool] = _defaultShouldIgnore,
        skipForRegistry: Callable[[str], bool] = _defaultSkipForRegistry,
    ) -> Tuple[DirNode, NameRegistry]:
        """
        Crawl the current directory. Construct & return an FsNode tree and NameRegistry.
        """
        dirPath: str = os.curdir

        rootDir: DirNode = DirNode(None, dirPath, shouldIgnore)
        nameRegistry = NameRegistry(rootDir, skipForRegistry)

        return rootDir, nameRegistry

    def __init__(self) -> None:
        rootDir, nameRegistry = Fs._crawl()
        self.rootDir: DirNode = rootDir
        self.nameRegistry: NameRegistry = nameRegistry
