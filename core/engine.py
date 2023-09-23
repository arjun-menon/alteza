import os
import types
import shutil
from contextlib import contextmanager
from time import time_ns
from typing import Generator, Dict, Any

# pyre-ignore[21]
from pypage import pypage  # type: ignore [import]

from core.fs_crawl import (
    FileNode,
    DirNode,
    displayDir,
    runOnFsNodeAndAscendantNodes,
    NameRegistry,
    fs_crawl,
    config_py_file,
    Fore,
    Style,
)


class Content(object):
    def __init__(self, rootDir: DirNode, nameRegistry: NameRegistry) -> None:
        self.rootDir: DirNode = rootDir
        self.nameRegistry = nameRegistry

    def link(self, name: str) -> str:
        if name not in self.nameRegistry.allFiles:
            print(
                f"Link error: `{name}` was not found in the name registry."
                f" The {self.nameRegistry}"
            )
            raise Exception(f"Link error: {name}")

        fileNode: FileNode = self.nameRegistry.allFiles[name]
        fileNode.shouldPublish = True
        runOnFsNodeAndAscendantNodes(fileNode, lambda fsNode: fsNode.makePublic())

        relativePath = fileNode.absoluteFilePath  # TODO + FIXME

        return relativePath

    @staticmethod
    def processWithPyPage(fileNode: FileNode, env: dict[str, Any]) -> None:
        print(f"{Fore.grey_42}Processing:{Style.reset}", fileNode.fullPath)
        assert not ((fileNode.htmlPage is not None) and (fileNode.markdown is not None))
        html: str
        if fileNode.htmlPage is not None:
            html = fileNode.htmlPage
        elif fileNode.markdown is not None:
            html = fileNode.markdown.html
            env.update(fileNode.markdown.metadata)
        else:
            raise Exception(f"{fileNode} is not a page.")

        # Invoke pypage
        pageHtmlOutput = pypage(html, env)
        default_template = Content.getDefaultTemplate(env)
        fileNode.htmlOutput = pypage(default_template, env | {"body": pageHtmlOutput})

    @staticmethod
    def getDefaultTemplate(env: dict[str, Any]) -> str:
        if "default_template" not in env:
            raise Exception(
                "You must define a `default_template` in some ancestral `__config__.py` file."
            )
        default_template = env["default_template"]
        if not isinstance(default_template, str):
            raise Exception("The `default_template` must be a string.")
        return default_template

    @staticmethod
    def getModuleVars(env: Dict[str, Any]) -> Dict[str, Any]:
        return {
            k: v
            for k, v in env.items()
            if (not k.startswith("_") and not isinstance(v, types.ModuleType))
        }

    def getBasicHelpers(self) -> Dict[str, Any]:
        return {"link": self.link, "readfile": readfile}

    def process(self) -> None:
        def walk(node: DirNode, env: dict[str, Any]) -> None:
            env = env.copy()

            # Run a __config__.py file, if one exists.
            configEnv = env.copy()
            if config_py_file in (f.fileName for f in node.files):
                print(
                    f"{Fore.dark_red_2}Running:{Style.reset}",
                    os.path.join(node.fullPath, config_py_file),
                )
                exec(readfile(config_py_file), configEnv)

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
                    self.processWithPyPage(f, env.copy())

        initial_env = self.getBasicHelpers()
        walk(self.rootDir, initial_env)


def readfile(file_path: str) -> str:
    with open(file_path, "r") as a_file:
        return a_file.read()


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

    with enterDir(inputDir):
        rootDir, nameRegistry = fs_crawl()
        content = Content(rootDir, nameRegistry)
        print("Processing...\n")
        content.process()
        print("\nSuccessfully completed processing.\n")

    print("File Tree:")
    print(displayDir(rootDir))

    generate(outputDir, content)

    elapsedMilliseconds = (time_ns() - startTimeNs) / 10**6
    print("\nTime elapsed: %.2f ms" % elapsedMilliseconds)


def generate(outputDir: str, content: Content) -> None:
    def walk(curDir: DirNode) -> None:
        for subDir in curDir.subDirs:
            if subDir.shouldPublish:
                os.mkdir(subDir.dirName)
                with enterDir(subDir.dirName):
                    walk(subDir)

        for fileNode in curDir.files:
            if fileNode.shouldPublish:
                if fileNode.isPage:
                    os.mkdir(fileNode.basename)
                    with enterDir(fileNode.basename):
                        with open("index.html", "w") as pageHtml:
                            assert isinstance(fileNode.htmlOutput, str)
                            pageHtml.write(fileNode.htmlOutput)
                else:
                    os.symlink(fileNode.absoluteFilePath, fileNode.fileName)

    resetOutputDir(outputDir)

    print("Generating...")

    with enterDir(outputDir):
        walk(content.rootDir)


def resetOutputDir(outputDir: str) -> None:
    if os.path.isfile(outputDir):
        raise Exception("There is a file named %s." % outputDir)
    if os.path.isdir(outputDir):
        print("Deleting directory %s and all of its content...\n" % outputDir)
        shutil.rmtree(outputDir)
    os.mkdir(outputDir)
