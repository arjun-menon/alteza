# formatted with black
# pyre-strict

from core.ingest_markdown import *

magic_py: str = 'magic.py'


class FsNode(object):
    def __init__(self, dirPath: str, name: str or None) -> None:
        self.dirPath, self.name = dirPath, name
        self.fullPath: str = self.dirPath if isinstance(self, DirNode) else os.path.join(self.dirPath, self.name)

    def __repr__(self) -> str:
        return self.fullPath


class FileNode(FsNode):
    def __init__(self, dirPath: str, name: str) -> None:
        super().__init__(dirPath, name)
        self.basename, self.extension = os.path.splitext(name)


def isHidden(name: str) -> bool:
    return name.startswith('.')


class DirNode(FsNode):
    def __init__(self, dirPath: str) -> None:
        _, subDirNames, fileNames = next(os.walk(dirPath))
        super().__init__(dirPath, None)

        self.files: List[FileNode] = [FileNode(dirPath, fileName) for fileName
                                      in fileNames if not isHidden(fileName)]
        self.subDirs: List[DirNode] = [DirNode(os.path.join(dirPath, subDirName)) for subDirName
                                       in subDirNames if not isHidden(subDirName)]


def displayDir(dirNode: DirNode, indent: int = 0) -> str:
    return (
            (' ' * 2 * indent)
            + '%s -> %s\n' % (dirNode, dirNode.files)
            + ''.join(displayDir(subDir, indent + 1) for subDir in dirNode.subDirs)
    )


class NameRegistry(object):
    def __init__(self, root: DirNode):
        self.allFiles: DefaultDict[str, Set[FileNode]] = defaultdict(set)

        def walk(node: DirNode) -> None:
            for f in node.files:
                self.record(f)
            for d in node.subDirs:
                walk(d)

        walk(root)

    def record(self, fileNode: FileNode):
        self.allFiles[fileNode.name].add(fileNode)
        self.allFiles[fileNode.basename].add(fileNode)

    def addFiles(self, dirNode: DirNode):
        for fileNode in dirNode.files:
            self.allFiles[fileNode.name].add(fileNode)
            self.allFiles[fileNode.basename].add(fileNode)


class Content(object):
    def __init__(self, contentDir: str) -> None:
        os.chdir(contentDir)
        self.root: DirNode = DirNode(".")
        self.nameRegistry = NameRegistry(self.root)


def process(contentDir: str, outputDir: str) -> None:
    content = Content(contentDir)

    print('Input File Tree:')
    print(displayDir(content.root))
    print('\nAll input files:', dict(content.nameRegistry.allFiles))
