import os
import sys
import types
import shutil
from contextlib import contextmanager
from time import time_ns
from typing import Generator, Dict, Any, Set

# pyre-ignore[21]
from pypage import pypage  # type: ignore [import]

from core.fs_crawl import (
    FileNode,
    DirNode,
    displayDir,
    NameRegistry,
    fs_crawl,
    config_py_file,
)


class Content(object):
    def __init__(self, rootDir: DirNode, nameRegistry: NameRegistry) -> None:
        self.rootDir: DirNode = rootDir
        self.nameRegistry = nameRegistry

    @staticmethod
    def processWithPyPage(fileNode: FileNode, env: dict[str, Any]) -> None:
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
    def getModuleVars(env: Dict[str, Any]) -> Dict[str, Any]:
        return {
            k: v
            for k, v in env.items()
            if (not k.startswith("_") and not isinstance(v, types.ModuleType))
        }

    def process(self) -> None:
        def walk(node: DirNode, env: dict[str, Any]) -> None:
            env = env.copy()

            # Check for a config, and update env.
            configEnv = env.copy()
            if config_py_file in (f.fileName for f in node.files):
                with open(config_py_file) as configFile:
                    lines = configFile.readlines()
                    exec("\n".join(lines), configEnv)

            # Note that `|=` doesn't create a copy unlike `x = x | y`.
            env |= self.getModuleVars(configEnv)

            # Ordering Note: We must recurse into the subdirectories first.
            for d in node.subDirs:
                with enterDir(d.dirName):
                    walk(d, env)

            # Ordering Note: Files in the current directory must be processed after
            # all subdirectories have been processed so that they have access to
            # information about the subdirectories.
            for f in node.files:
                if f.isPage:
                    self.processWithPyPage(f, env)

        walk(self.rootDir, dict())


@contextmanager
def enterDir(newDir: str) -> Generator[None, None, None]:
    # https://stackoverflow.com/a/13847807/908430
    oldDir = os.getcwd()
    os.chdir(newDir)
    try:
        yield
    finally:
        os.chdir(oldDir)


def process(inputDir: str, outputDir: str) -> None:
    startTimeNs = time_ns()
    resetOutputDir(outputDir)

    with enterDir(inputDir):
        rootDir, nameRegistry = fs_crawl()
        print(nameRegistry)
        print("Input File Tree:")
        print(displayDir(rootDir))
        content = Content(rootDir, nameRegistry)
        print("Processing...\n")
        content.process()

    copyContent(outputDir, content)

    elapsedMilliseconds = (time_ns() - startTimeNs) / 10**6
    print("\nTime elapsed: %.2f ms" % elapsedMilliseconds)


def copyContent(outputDir: str, content: Content) -> None:
    def walk(node: DirNode) -> None:
        for subDirNode in node.subDirs:
            walk(subDirNode)
        for fileNode in node.files:
            outputPath = os.path.join(outputDir, fileNode.fullPath)
            print(outputPath)

    walk(content.rootDir)


def resetOutputDir(outputDir: str) -> None:
    if os.path.isfile(outputDir):
        raise Exception("There is a file named %s." % outputDir)
    if os.path.isdir(outputDir):
        print("Deleting directory %s and all of its content...\n" % outputDir)
        shutil.rmtree(outputDir)
    os.mkdir(outputDir)
