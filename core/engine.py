# formatted with black
# pyre-strict

from core.ingest_markdown import *


class FsNode(object):
    def __init__(self, dirPath: str, name: str, isDir: bool) -> None:
        self.dirPath: str = dirPath
        self.name: str = name
        self.fullPath: str = self.dirPath if isDir else os.path.join(self.dirPath, self.name)

    def __repr__(self) -> str:
        return self.fullPath


class FileNode(FsNode):
    def __init__(self, dirPath: str, name: str) -> None:
        super().__init__(dirPath, name, False)
        self.basename: str = ''
        self.extension: str = ''
        self.basename, self.extension = os.path.splitext(name)


def isHidden(name: str) -> bool:
    return name.startswith('.')


class DirNode(FsNode):
    def __init__(self, dirPath: str, allFiles: DefaultDict[str, Set[FileNode]]) -> None:
        _, subDirNames, fileNames = next(os.walk(dirPath))
        dirName: str = os.path.split(dirPath)[-1]
        super().__init__(dirPath, dirName, True)

        self.files: List[FileNode] = [FileNode(dirPath, fileName) for fileName in fileNames if not isHidden(fileName)]
        for fileNode in self.files:
            allFiles[fileNode.name].add(fileNode)
            allFiles[fileNode.basename].add(fileNode)

        self.subDirs: List[DirNode] = [
            DirNode(os.path.join(dirPath, dirName), allFiles)
            for dirName in subDirNames
            if not isHidden(dirName)
        ]

    def display(self, indent: int = 0) -> str:
        return (
                (' ' * 4 * indent)
                + '%s -> %s\n' % (self, self.files)
                + ''.join(subDir.display(indent + 1) for subDir in self.subDirs)
        )


class Content(object):
    def __init__(self, contentDir: str) -> None:
        os.chdir(contentDir)
        self.allFiles: DefaultDict[str, Set[FileNode]] = defaultdict(set)
        self.root: DirNode = DirNode(".", self.allFiles)


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

    print('\nAll input files:', dict(content.allFiles))
