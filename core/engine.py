from typing import Optional
from core.common_imports import *


class FsNode(object):
    def __init__(self, dirPath: str, name: Optional[str]) -> None:
        self.dirPath: str = dirPath
        self.name: Optional[str] = name
        self.fullPath: str = (
            self.dirPath
            if isinstance(self, DirNode) or type(name) is not str
            else os.path.join(self.dirPath, name)
        )

    def __repr__(self) -> str:
        return self.fullPath


class FileNode(FsNode):  # pyre-ignore[13]
    def __init__(self, dirPath: str, name: str) -> None:
        super().__init__(dirPath, name)
        self.name: str = name  # for typing
        split_name = os.path.splitext(name)
        self.basename: str = split_name[0]
        self.extension: str = split_name[1]
        self.shouldPublish: bool


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
        self.allFiles[fileNode.name].add(fileNode)
        self.allFiles[fileNode.basename].add(fileNode)

    def addFiles(self, dirNode: DirNode) -> None:
        for fileNode in dirNode.files:
            self.allFiles[fileNode.name].add(fileNode)
            self.allFiles[fileNode.basename].add(fileNode)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}:\n" + "\n  ".join(
            f"{k}: {v}" for k, v in self.allFiles.items()
        )


class Content(object):
    def __init__(self, contentDir: str) -> None:
        os.chdir(contentDir)
        self.root: DirNode = DirNode(".")
        self.nameRegistry = NameRegistry(self.root)

    def processMarkdown(self) -> None:
        def walk(node: DirNode) -> None:
            for f in node.files:
                pass
            for d in node.subDirs:
                walk(d)

        walk(self.root)


def process(inputDir: str, outputDir: str) -> None:
    content = Content(inputDir)
    print("Input File Tree:")
    print(displayDir(content.root))
    print(content.nameRegistry)
    print()
    print("Processing Markdown...")
    content.processMarkdown()
