import os
import shutil
from contextlib import contextmanager
from time import time_ns
from typing import Generator

# pyre-ignore[21]
from pypage import pypage  # type: ignore [import]

from core.fs_crawl import FsNode, FileNode, DirNode, displayDir, NameRegistry, fs_crawl
from core.ingest_markdown import processMarkdownFile


class Content(object):
    def __init__(self, rootDir: DirNode, nameRegistry: NameRegistry) -> None:
        self.root: DirNode = rootDir
        self.nameRegistry = nameRegistry

    def printInputFileTree(self) -> None:
        print("Input File Tree:")
        print(displayDir(self.root))

    def printInputFileTreeAndNameRegistry(self) -> None:
        print(self.nameRegistry)
        self.printInputFileTree()

    @staticmethod
    def processWithPypage(fileNode: FileNode) -> None:
        env = dict()

        assert not ((fileNode.htmlPage is not None) and (fileNode.markdown is not None))
        html: str
        if fileNode.htmlPage is not None:
            html = fileNode.htmlPage
        elif fileNode.markdown is not None:
            html = fileNode.markdown.html
            env.update(fileNode.markdown.metadata)
        else:
            raise Exception(f"{fileNode} is not a page.")

        # Inject `link(name)` lambda
        # TODO

        # Invoke pypage
        fileNode.htmlOutput = pypage(html, env)

    @staticmethod
    @contextmanager
    def pushDir(newDir: str) -> Generator[None, None, None]:
        # https://stackoverflow.com/a/13847807/908430
        oldDir = os.getcwd()
        os.chdir(newDir)
        try:
            yield
        finally:
            os.chdir(oldDir)

    def invokePypage(self) -> None:
        def walk(node: DirNode) -> None:
            for d in node.subDirs:
                with self.pushDir(d.dirName):
                    walk(d)

            for f in node.files:
                if f.isPage:
                    self.processWithPypage(f)

        walk(self.root)

    def crunch(self) -> None:
        print("Processing...\n")
        self.invokePypage()
        self.printInputFileTreeAndNameRegistry()


def process(inputDir: str, outputDir: str) -> None:
    startTimeNs = time_ns()
    resetOutputDir(outputDir)
    os.chdir(inputDir)
    rootDir, nameRegistry = fs_crawl(os.curdir)
    content = Content(rootDir, nameRegistry)
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
