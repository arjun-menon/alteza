#!/usr/bin/env python3
# formatted with black
# pyre-strict

import os, shutil, yaml, sys, time, logging
import markdown  # pyre-ignore
from pypage import pypage
from watchdog.observers import Observer  # pyre-ignore
from watchdog.events import LoggingEventHandler  # pyre-ignore
from typing import Dict, List, Tuple, Set, DefaultDict
from collections import defaultdict


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


class Metadata(object):
    def __init__(self, metadataDict: Dict[str, str]) -> None:
        self.metadataDict = metadataDict

    def __repr__(self) -> str:
        return "\n".join("%s : %s" % (k, v) for k, v in self.metadataDict.items())


def resetOutputDir(outputDir: str) -> None:
    if os.path.isfile(outputDir):
        raise Exception("There is a file named %s." % outputDir)
    if os.path.isdir(outputDir):
        print("Deleting directory %s and all of its content..." % outputDir)
        shutil.rmtree(outputDir)
    os.mkdir(outputDir)


def mandrake(contentDir: str, outputDir: str) -> None:
    resetOutputDir(outputDir)

    content = Content(contentDir)

    print("Processing...")
    content.process()


###############################################################################


def processMarkdownFile(markdownFileName: str) -> Tuple[Metadata, str]:
    with open(markdownFileName) as f:
        text = f.read()

    md = markdown.Markdown(extensions=["meta"])
    html = md.convert(text)
    yamlFrontMatter = ""

    for name, lines in md.Meta.items():  # pylint: disable=no-member
        yamlFrontMatter += "%s : %s \n" % (name, lines[0])
        for line in lines[1:]:
            yamlFrontMatter += " " * (len(name) + 3) + line + "\n"

    yamlMetadata = yaml.safe_load(yamlFrontMatter)
    metadata = Metadata(yamlMetadata)
    return metadata, html


def testMarkdownProcessing() -> None:
    # pylint: disable=unused-variable
    metadata, html = processMarkdownFile("simple.md")
    print(metadata)


def testChangeDetectionMonitoring() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    eventHandler = LoggingEventHandler()  # type: ignore
    observer = Observer()
    observer.schedule(eventHandler, path, recursive=True)
    observer.start()
    # try:
    #     while True:
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     observer.stop()
    time.sleep(1)
    observer.stop()
    observer.join()


if __name__ == "__main__":
    mandrake("test_content", "test_output")
    # testMarkdownProcessing()
    # testChangeDetectionMonitoring()
