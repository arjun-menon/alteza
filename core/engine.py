import os
import types
import shutil
from contextlib import contextmanager
from time import time_ns
from typing import Generator, List, Dict, Any

# pyre-ignore[21]
import sh  # type: ignore [import]

# pyre-ignore[21]
from pypage import pypage  # type: ignore [import]

from core.fs_crawl import (
    FileNode,
    DirNode,
    displayDir,
    NameRegistry,
    fs_crawl,
    Md,
    NonMd,
    readfile,
    config_py_file,
    Fore,
    Style,
)


class Content(object):
    def __init__(self, rootDir: DirNode, nameRegistry: NameRegistry) -> None:
        self.rootDir: DirNode = rootDir
        self.nameRegistry = nameRegistry

    def link(self, srcFile: FileNode, name: str) -> str:
        if name not in self.nameRegistry.allFiles:
            print(
                f"Link error: `{name}` was not found in the name registry."
                f" The {self.nameRegistry}"
            )
            raise Exception(f"Link error: {name}")

        dstFile: FileNode = self.nameRegistry.allFiles[name]
        dstFile.makePublic()

        dstFileName = dstFile.fileName
        if isinstance(dstFile.pyPage, NonMd):
            dstFileName = dstFile.pyPage.rectifiedFileName
        elif isinstance(dstFile.pyPage, Md):
            dstFileName = dstFile.basename  # todo: maybe pass an arg to + "/"

        srcPath = splitPath(srcFile.fullPath)[:-1]
        dstPath = splitPath(dstFile.fullPath)[:-1]
        print("srcPath:", srcPath)
        print("dstPath:", dstPath)
        commonLevel = 0
        for i in range(min(len(srcPath), len(dstPath))):
            if srcPath[i] == dstPath[i]:
                commonLevel += 1
        remainingPath = dstPath[commonLevel:] + [dstFileName]
        print("Remaining Path:", remainingPath)
        print("Common Level:", commonLevel)

        relativePath: List[str] = []
        if commonLevel < len(srcPath):
            stepsDown = len(srcPath) - commonLevel
            for _ in range(stepsDown):
                relativePath.append("..")
        for p in remainingPath:
            relativePath.append(p)
        if isinstance(srcFile.pyPage, Md):
            relativePath = [".."] + relativePath

        relativePathStr = os.path.join("", *relativePath)
        print("relativePath", relativePathStr)

        return relativePathStr

    def processWithPyPage(self, fileNode: FileNode, env: dict[str, Any]) -> None:
        assert fileNode.pyPage is not None
        print(f"{Fore.grey_42}Processing:{Style.reset}", fileNode.fullPath)
        env = env.copy()
        toProcessFurther: str

        if isinstance(fileNode.pyPage, NonMd):
            toProcessFurther = fileNode.pyPage.fileContent
        elif isinstance(fileNode.pyPage, Md):
            toProcessFurther = fileNode.pyPage.html
            env.update(fileNode.pyPage.metadata)
        else:
            raise Exception(f"{fileNode} pyPage attribute is invalid.")

        # Inject link
        def link(name: str) -> str:
            return self.link(fileNode, name)

        env |= {"link": link}

        # Invoke pypage
        pyPageOutput = pypage(toProcessFurther, env)

        # TODO: Do Markdown processing here. And perhaps NonMd reading as well.

        if "public" in env and env["public"] is True:
            fileNode.makePublic()

        if isinstance(fileNode.pyPage, Md):
            defaultHtmlTemplate = Content.getDefaultHtmlTemplate(env)
            # Re-process against `defaultHtmlTemplate` with PyPage:
            pyPageOutput = pypage(defaultHtmlTemplate, env | {"body": pyPageOutput})

        fileNode.pyPageOutput = pyPageOutput

    @staticmethod
    def getDefaultHtmlTemplate(env: dict[str, Any]) -> str:
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

    @staticmethod
    def getBasicHelpers() -> Dict[str, Any]:
        return {"readfile": readfile, "sh": sh}

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
                if f.pyPage is not None:
                    self.processWithPyPage(f, env.copy())

        initial_env = self.getBasicHelpers()
        walk(self.rootDir, initial_env)


def splitPath(path: str) -> List[str]:
    head, tail = os.path.split(path)
    if head == "":
        return [path]
    else:
        return splitPath(head) + [tail]


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
        print(nameRegistry)
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
                if fileNode.pyPage is not None:
                    assert fileNode.pyPageOutput is not None
                    assert isinstance(fileNode.pyPageOutput, str)

                    if isinstance(fileNode.pyPage, Md):
                        os.mkdir(fileNode.basename)
                        with enterDir(fileNode.basename):
                            with open("index.html", "w") as pageHtml:
                                pageHtml.write(fileNode.pyPageOutput)
                    elif isinstance(fileNode.pyPage, NonMd):
                        fileName = fileNode.pyPage.rectifiedFileName
                        if os.path.exists(fileName):
                            raise Exception(
                                f"File {fileName} already exists, and conflicts with {fileNode}."
                            )
                        with open(fileName, "w") as nonMdFile:
                            nonMdFile.write(fileNode.pyPageOutput)

                    else:
                        raise Exception(f"{fileNode} pyPage attribute is invalid.")

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
