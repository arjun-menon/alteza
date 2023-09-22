import os
import shutil
import importlib
import sys
from contextlib import contextmanager
from time import time_ns
from typing import Generator, Dict, Any, Set

# pyre-ignore[21]
from pypage import pypage  # type: ignore [import]

from core.fs_crawl import FsNode, FileNode, DirNode, displayDir, NameRegistry, fs_crawl
from core.ingest_markdown import processMarkdownFile


class Content(object):
    config_py_file = "__config__.py"
    config_py_name = "__config__"

    def __init__(self, rootDir: DirNode, nameRegistry: NameRegistry) -> None:
        self.rootDir: DirNode = rootDir
        self.nameRegistry = nameRegistry
        self.fixSysPath()

    @staticmethod
    def processWithPypage(fileNode: FileNode, env: dict[str, Any]) -> None:
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
    def fixSysPath() -> None:
        """
        This is necessary for importlib to consider the current directory.
        See: https://stackoverflow.com/questions/57870498/cannot-find-module-after-change-directory
        """
        sys.path.insert(0, "")

    @staticmethod
    # pyre-ignore[2]
    def getModuleVars(module: Any) -> Dict[str, Any]:
        limitTo = None
        if "__all__" in module.__dict__:
            names = module.__dict__["__all__"]
            if not (isinstance(names, list) and all(isinstance(k, str) for k in names)):
                raise Exception(f"{module}'s __all__ is not a list of strings.")
            limitTo = names

        return {
            k: v
            for k, v in module.__dict__.items()
            if not k.startswith("_")
            and ((k in limitTo) if limitTo is not None else True)
        }

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

    @staticmethod
    def warnAboutOverrides(
        existingVals: Dict[str, Any], newVals: Dict[str, Any], filePath: str
    ) -> None:
        for v in newVals:
            if v in existingVals:
                print(
                    f"Value `{v}` is being overriden by {filePath} for this directory..."
                )

    def invoke(self) -> None:
        def walk(node: DirNode, env: dict[str, Any]) -> None:
            env = env.copy()

            # Check for a config, and update env.
            configVals = {}
            if self.config_py_file in (f.fileName for f in node.files):
                # configModule = importlib.import_module(self.config_py_name)
                configModule = __import__(self.config_py_name)
                configVals = self.getModuleVars(configModule)

                cF = [f for f in node.files if f.fileName == self.config_py_file][0]
                print(configVals, cF.fullPath)
                self.warnAboutOverrides(env, configVals, cF.fullPath)
            # Note that `|=` doesn't create a copy unlike `x = x | y`.
            env |= configVals

            # Ordering Note: We must recurse into the subdirectories first.
            for d in node.subDirs:
                with self.pushDir(d.dirName):
                    walk(d, env.copy())

            # Ordering Note: Files in the current directory must be processed after
            # all subdirectories have been processed so that they have access to
            # information about the subdirectories.
            for f in node.files:
                if f.isPage:
                    self.processWithPypage(f, env)

        walk(self.rootDir, dict())

    def crunch(self) -> None:
        self.invoke()


def process(inputDir: str, outputDir: str) -> None:
    startTimeNs = time_ns()
    resetOutputDir(outputDir)

    os.chdir(inputDir)
    rootDir, nameRegistry = fs_crawl()
    print(nameRegistry)
    print("Input File Tree:")
    print(displayDir(rootDir))
    content = Content(rootDir, nameRegistry)

    print("Processing...\n")
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
