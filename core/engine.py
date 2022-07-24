# formatted with black
# pyre-strict

from core.ingest_markdown import *


class FsNode(object):
    def __init__(self, dirPath: str, name: str) -> None:
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
    def __init__(self, dirPath: str, nameRegistry) -> None:
        _, subDirNames, fileNames = next(os.walk(dirPath))
        dirName: str = os.path.split(dirPath)[-1]
        super().__init__(dirPath, dirName)

        self.files: List[FileNode] = [
            FileNode(dirPath, fileName) for fileName in fileNames if not isHidden(fileName)
        ]
        nameRegistry.addFiles(self)
        self.subDirs: List[DirNode] = [
            DirNode(os.path.join(dirPath, dirName), nameRegistry) for dirName in subDirNames if not isHidden(dirName)
        ]

    def display(self, indent: int = 0) -> str:
        return (
                (' ' * 2 * indent)
                + '%s -> %s\n' % (self, self.files)
                + ''.join(subDir.display(indent + 1) for subDir in self.subDirs)
        )


class NameRegistry(object):
    def __init__(self):
        self.allFiles: DefaultDict[str, Set[FileNode]] = defaultdict(set)

    def addFiles(self, dirNode: DirNode):
        for fileNode in dirNode.files:
            self.allFiles[fileNode.name].add(fileNode)
            self.allFiles[fileNode.basename].add(fileNode)


class Content(object):
    def __init__(self, contentDir: str) -> None:
        os.chdir(contentDir)
        self.nameRegistry = NameRegistry()
        self.root: DirNode = DirNode(".", self.nameRegistry)


def process(contentDir: str, outputDir: str) -> None:
    content = Content(contentDir)

    print('Input File Tree View 1:')
    print(content.root.display())

    print('Input File Tree View 2:')

    def walk(node: DirNode) -> None:
        for f in node.files:
            print(' ', f.name)
        for d in node.subDirs:
            print('Inside %s' % d)
            walk(d)

    walk(content.root)

    print('\nAll input files:', dict(content.nameRegistry.allFiles))
