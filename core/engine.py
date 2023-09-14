from typing import Optional
from time import time_ns
from core.common_imports import *
from core.ingest_markdown import Markdown, processMarkdownFile


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
        return self.fullPath


class FileNode(FsNode):  # pyre-ignore[13]
    def __init__(self, dirPath: str, fileName: str) -> None:
        super().__init__(dirPath, fileName)
        self.fileName: str = fileName  # for typing
        split_name = os.path.splitext(fileName)
        self.basename: str = split_name[0]
        self.extension: str = split_name[1]
        self.markdown: Markdown


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
    def __init__(self, root: DirNode) -> None:
        self.allFiles: DefaultDict[str, Set[FileNode]] = defaultdict(set)

        def walk(node: DirNode) -> None:
            for f in node.files:
                self.record(f)
            for d in node.subDirs:
                walk(d)

        walk(root)

    def record(self, fileNode: FileNode) -> None:
        self.allFiles[fileNode.fileName].add(fileNode)
        self.allFiles[fileNode.basename].add(fileNode)

    def addFiles(self, dirNode: DirNode) -> None:
        for fileNode in dirNode.files:
            self.allFiles[fileNode.fileName].add(fileNode)
            self.allFiles[fileNode.basename].add(fileNode)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}:\n  " + "\n  ".join(
            f"{k}: {v}" for k, v in self.allFiles.items()
        )


class Content(object):
    def __init__(self, contentDir: str) -> None:
        os.chdir(contentDir)
        self.root: DirNode = DirNode(".")
        self.nameRegistry = NameRegistry(self.root)

    def printInputFileTree(self) -> None:
        print("Input File Tree:")
        print(displayDir(self.root))

    def printInputFileTreeAndNameRegistry(self) -> None:
        self.printInputFileTree()
        print(self.nameRegistry)
        print()

    def processMarkdown(self) -> None:
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
                    isPublic = f.markdown.metadata.get("public", False)
                    print(f.fileName, isPublic, f.markdown.metadata)
                    if isPublic:
                        f.shouldPublish = True

            return node.shouldPublish

        walk(self.root)

    def crunch(self) -> None:
        print("Processing Markdown...")
        self.processMarkdown()


def resetOutputDir(outputDir: str) -> None:
    if os.path.isfile(outputDir):
        raise Exception("There is a file named %s." % outputDir)
    if os.path.isdir(outputDir):
        print("Deleting directory %s and all of its content...\n" % outputDir)
        shutil.rmtree(outputDir)
    os.mkdir(outputDir)


def process(inputDir: str, outputDir: str) -> None:
    startTime = time_ns()
    resetOutputDir(outputDir)
    content = Content(inputDir)
    content.printInputFileTreeAndNameRegistry()
    # content.printInputFileTree()

    content.crunch()

    endTime = time_ns()
    elapsedNanoseconds = endTime - startTime
    elapsedMilliseconds = elapsedNanoseconds / 10**6
    print("\nTime elapsed: %.2f ms" % elapsedMilliseconds)
