import os
import shutil
from contextlib import contextmanager
from time import time_ns
from typing import Generator

# pyre-ignore[21]
from pypage import pypage  # type: ignore [import]

from core.fs_crawl import FsNode, FileNode, DirNode, displayDir, NameRegistry
from core.ingest_markdown import processMarkdownFile


@contextmanager
def pushDir(newDir: str) -> Generator[None, None, None]:
    # https://stackoverflow.com/a/13847807/908430
    oldDir = os.getcwd()
    os.chdir(newDir)
    try:
        yield
    finally:
        os.chdir(oldDir)


class Content(object):
    def __init__(self, contentDir: str) -> None:
        os.chdir(contentDir)
        self.root: DirNode = DirNode(os.curdir)
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
            env = dict()

            assert not (
                (fileNode.htmlPage is not None) and (fileNode.markdown is not None)
            )
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

        def walk(node: DirNode) -> None:
            for f in node.files:
                if f.isPage:
                    processWithPypage(f)
            for d in node.subDirs:
                with pushDir(d.dirName):
                    walk(d)

        walk(self.root)

    def crunch(self) -> None:
        print("Processing markdown...\n")
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
