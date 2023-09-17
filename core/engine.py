from typing import Optional
from time import time_ns
from core.common_imports import *
from core.ingest_markdown import Markdown, processMarkdownFile
from pypage import pypage

# pyre-ignore[21]
from colored import Fore, Back, Style  # type: ignore [import]

colored_logs = True


class FsNode(object):
    def __init__(self, dirPath: str, fileName: Optional[str]) -> None:
        self.dirPath: str = dirPath
        self.fileName: Optional[str] = fileName
        self.fullPath: str = (
            self.dirPath
            if isinstance(self, DirNode) or type(fileName) is not str
            else os.path.join(self.dirPath, fileName)
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


def isHidden(name: str) -> bool:
    return name.startswith(".")


class DirNode(FsNode):
    def __init__(self, dirPath: str) -> None:
        _, subDirNames, fileNames = next(os.walk(dirPath))
        super().__init__(dirPath, None)

        self.files: List[FileNode] = [
            FileNode(dirPath, fileName)
            for fileName in fileNames
            if not isHidden(fileName)
        ]
        self.subDirs: List[DirNode] = [
            DirNode(os.path.join(dirPath, subDirName))
            for subDirName in subDirNames
            if not isHidden(subDirName)
        ]


def displayDir(dirNode: DirNode, indent: int = 0) -> str:
    return (
        (" " * 2 * indent)
        + "%s -> %s\n" % (dirNode, dirNode.files)
        + "".join(displayDir(subDir, indent + 1) for subDir in dirNode.subDirs)
    )


class NameRegistry(object):
    def __init__(self) -> None:
        # Needs to be initialized with .build() later
        self.allFiles: Dict[str, FileNode] = {}

    def build(self, root: DirNode) -> None:
        allFilesMulti: DefaultDict[str, Set[FileNode]] = defaultdict(set)

        def record(fileNode: FileNode) -> None:
            if fileNode.isPage:
                allFilesMulti[fileNode.basename].add(fileNode)
            else:
                allFilesMulti[fileNode.fileName].add(fileNode)

        def traverse(node: DirNode) -> None:
            for f in node.files:
                record(f)
            for d in node.subDirs:
                traverse(d)

        traverse(root)

        def errorOut(name: str, fileNodes: Set[FileNode]) -> None:
            print(
                f"Error: The name '{name}' has multiple matches:\n"
                + "  \n".join(f" {fileNode.fullPath}" for fileNode in fileNodes)
            )
            sys.exit(1)

        for name, fileNodes in allFilesMulti.items():
            assert len(fileNodes) >= 1
            if len(fileNodes) > 1:
                errorOut(name, fileNodes)

            self.allFiles[name] = fileNodes.pop()

    def __repr__(self) -> str:
        return (
            f"Name Registry:\n  "
            + "\n  ".join(f"{k}: {v}" for k, v in self.allFiles.items())
            + "\n"
        )


class Content(object):
    def __init__(self, contentDir: str) -> None:
        os.chdir(contentDir)
        self.root: DirNode = DirNode(".")
        self.nameRegistry = NameRegistry()

    def printInputFileTree(self) -> None:
        print("Input File Tree:")
        print(displayDir(self.root))

    def printInputFileTreeAndNameRegistry(self) -> None:
        print(self.nameRegistry)
        self.printInputFileTree()

    def readMarkdown(self) -> None:
        def walk(node: FsNode) -> bool:
            if isinstance(node, DirNode):
                d: DirNode = node
                for aDir in node.subDirs:
                    walk(aDir)
                for aFile in node.files:
                    walk(aFile)

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
                elif f.extension == ".html":
                    with open(f.fullPath, "r") as htmlFile:
                        f.htmlPage = htmlFile.read()
                    f.isPage = True
                    # f.shouldPublish will be determined later in invokePypage

            return node.shouldPublish

        walk(self.root)

    def invokePypage(self) -> None:
        def processWithPypage(fileNode: FileNode) -> None:
            assert not (
                (fileNode.htmlPage is not None) and (fileNode.markdown is not None)
            )
            html: str
            if fileNode.htmlPage is not None:
                html = fileNode.htmlPage
            elif fileNode.markdown is not None:
                html = fileNode.markdown.html
            else:
                raise Exception(f"{fileNode} is not a page.")

            # Set PWD
            # TODO

            # Invoke pypage
            fileNode.htmlOutput = pypage(html)

        def walk(node: DirNode) -> None:
            for f in node.files:
                if f.isPage:
                    processWithPypage(f)
            for d in node.subDirs:
                walk(d)

        walk(self.root)

    def crunch(self) -> None:
        print("Processing Markdown...\n")
        self.readMarkdown()
        self.nameRegistry.build(self.root)
        print("Processing pypage...\n")
        self.invokePypage()
        self.printInputFileTreeAndNameRegistry()


def process(inputDir: str, outputDir: str) -> None:
    startTimeNs = time_ns()
    resetOutputDir(outputDir)
    content = Content(inputDir)
    content.crunch()

    elapsedMilliseconds = (time_ns() - startTimeNs) / 10**6
    print("\nTime elapsed: %.2f ms" % elapsedMilliseconds)


def resetOutputDir(outputDir: str) -> None:
    if os.path.isfile(outputDir):
        raise Exception("There is a file named %s." % outputDir)
    if os.path.isdir(outputDir):
        print("Deleting directory %s and all of its content...\n" % outputDir)
        shutil.rmtree(outputDir)
    os.mkdir(outputDir)
