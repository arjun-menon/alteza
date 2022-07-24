# formatted with black
# pyre-strict


from core.ingest_markdown import *


class FsNode(object):
    def __init__(self, dirPath: str, name: str, isDir: bool) -> None:
        self.dirPath: str = dirPath
        self.name: str = name
        self.fullPath: str = self.dirPath if isDir else os.path.join(
            self.dirPath, self.name
        )
        self.dirPathAbs: str = os.path.abspath(self.dirPath)
        self.fullPathAbs: str = os.path.abspath(self.fullPath)

    def __repr__(self) -> str:
        return self.fullPathAbs


class FileNode(FsNode):
    def __init__(self, dirPath: str, name: str) -> None:
        super().__init__(dirPath, name, False)

        self.basename: str = ""
        self.extname: str = ""
        self.basename, self.extname = os.path.splitext(name)


def isHidden(name: str) -> bool:
    return name.startswith(".")


class DirNode(FsNode):
    def __init__(self, dirPath: str, allFiles: DefaultDict[str, Set[FileNode]]) -> None:
        _, subDirNames, fileNames = next(os.walk(dirPath))
        dirName: str = os.path.split(dirPath)[-1]
        super().__init__(dirPath, dirName, True)

        self.files: List[FileNode] = [
            FileNode(dirPath, fileName)
            for fileName in fileNames
            if not isHidden(fileName)
        ]
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
                (" " * 4 * indent)
                + "%s -> %s\n" % (self, self.files)
                + "".join(subDir.display(indent + 1) for subDir in self.subDirs)
        )


class Content(object):
    def __init__(self, contentDir: str) -> None:
        self.contentDirAbsPath: str = os.path.abspath(contentDir)
        os.chdir(self.contentDirAbsPath)
        self.allFiles: DefaultDict[str, Set[FileNode]] = defaultdict(set)
        self.root: DirNode = DirNode(".", self.allFiles)
        print(self.root.display())

    def walk(self, node: DirNode) -> None:
        for f in node.files:
            print(f.basename, "->", f.extname)

        for d in node.subDirs:
            self.walk(d)

    def process(self) -> None:
        # print()
        # print(self.allFiles)
        self.walk(self.root)


def resetOutputDir(outputDir: str) -> None:
    if os.path.isfile(outputDir):
        raise Exception("There is a file named %s." % outputDir)
    if os.path.isdir(outputDir):
        print("Deleting directory %s and all of its content..." % outputDir)
        shutil.rmtree(outputDir)
    os.mkdir(outputDir)


def process(contentDir: str, outputDir: str) -> None:
    resetOutputDir(outputDir)

    content = Content(contentDir)

    print("Processing...")
    content.process()
