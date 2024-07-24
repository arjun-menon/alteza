import os
import shutil
import sys
import types
from contextlib import contextmanager
from time import time_ns
from typing import Optional, Generator, List, Dict, Any, Union, Literal

import sh  # type: ignore
from pypage import pypage  # type: ignore
from tap import Tap

from .fs import (
    FileNode,
    DirNode,
    NameRegistry,
    AltezaException,
    Md,
    NonMd,
    Fs,
    Fore,
    Style,
    PyPageNode,
)


class Args(Tap):  # pyre-ignore[13]
    content: str  # Directory to read the input content from.
    output: str  # Directory to send the output to. WARNING: This will be deleted.
    delete_output_dir_if_exists: bool = (
        False  # Delete output directory, if it already exists. (TODO)
    )
    copy_assets: bool = False  # Copy assets instead of symlinking to them
    trailing_slash: bool = (
        False  # Include a trailing slash for links to markdown page directories
    )
    seed: str = "{}"  # seed data to add to the initial/root env (TODO!)


class Content:
    def __init__(self, args: Args, fs: Fs) -> None:
        self.args = args
        self.rootDir: DirNode = fs.rootDir
        self.nameRegistry: NameRegistry = fs.nameRegistry
        self.fixSysPath()

        self.indentSpaces: Union[Literal[2], Literal[4]] = 2

    def linkObj(self, srcFile: PyPageNode, dstFile: FileNode) -> str:
        assert isinstance(dstFile, FileNode)
        dstName = dstFile.getLinkName()
        indentSpaces = " " * self.indentSpaces
        print(indentSpaces + f"{Fore.grey_42}Linking to:{Style.reset}", dstName)
        dstFile.makePublic()  # FixMe: Circular links can make pages public.

        dstFileName = dstFile.fileName
        if isinstance(dstFile, NonMd):
            dstFileName = dstFile.rectifiedFileName
        elif isinstance(dstFile, Md):
            dstFileName = (
                dstFile.realName
                # Add a "/" trailing slash if arg requests it
                + ("/" if self.args.trailing_slash else "")
            )

        srcPath = self.splitPath(srcFile.fullPath)[:-1]
        dstPath = self.splitPath(dstFile.fullPath)[:-1]
        commonLevel = 0
        for i in range(min(len(srcPath), len(dstPath))):
            if srcPath[i] == dstPath[i]:
                commonLevel += 1
        remainingPath = dstPath[commonLevel:] + [dstFileName]

        relativePath: List[str] = []
        if commonLevel < len(srcPath):
            stepsDown = len(srcPath) - commonLevel
            for _ in range(stepsDown):
                relativePath.append("..")
        for p in remainingPath:
            relativePath.append(p)
        if isinstance(srcFile, Md):
            relativePath = [".."] + relativePath

        relativePathStr = os.path.join("", *relativePath)

        return relativePathStr

    def invokePyPage(self, fileNode: PyPageNode, env: dict[str, Any]) -> None:
        print(f"{Fore.gold_1}Processing:{Style.reset}", fileNode.fullPath)
        env = env.copy()

        # Enrich with current file:
        env |= {"file": fileNode}

        toProcessFurther: str
        if isinstance(fileNode, (Md, NonMd)):
            toProcessFurther = Fs.readfile(fileNode.absoluteFilePath)
        else:
            raise AltezaException(f"{fileNode} Unsupported type of PyPageNode.")

        def link(name: str) -> str:
            dstFile: FileNode = self.nameRegistry.lookup(name)
            return self.linkObj(fileNode, dstFile)

        def linkObj(dstFile: FileNode) -> str:
            return self.linkObj(fileNode, dstFile)

        env |= {"link": link}
        env |= {"linkObj": linkObj}

        env |= {"lastUpdatedDatetime": fileNode.lastUpdated}
        # The formatting below might only work on Linux. https://stackoverflow.com/a/29980406/908430
        env |= {"lastUpdated": fileNode.lastUpdated.strftime("%Y %b %-d at %-H:%M %p")}

        if isinstance(fileNode, Md):
            env |= {"ideaDate": fileNode.ideaDate}

        # Invoke pypage
        pyPageOutput = pypage(toProcessFurther, env)

        # Perform Markdown processing
        if isinstance(fileNode, Md):
            mdResult = Md.processMarkdown(pyPageOutput)
            env.update(mdResult.metadata)
            pyPageOutput = mdResult.html

        if "public" in env:
            if env["public"] is True:
                fileNode.makePublic()
            elif env["public"] is False:
                fileNode.shouldPublish = False

        if isinstance(fileNode, Md):
            print(
                f"  {Fore.purple_3}Applying template...{Style.reset}"
            )  # TODO (see ideas.md)
            templateHtml = Content.getTemplateHtml(env)
            self.indentSpaces = 4
            # Re-process against `templateHtml` with PyPage:
            pyPageOutput = pypage(templateHtml, env | {"content": pyPageOutput})
            self.indentSpaces = 2

        fileNode.setPyPageOutput(pyPageOutput)
        fileNode.env = env

    def process(self) -> None:
        def walk(dirNode: DirNode, env: dict[str, Any]) -> None:
            env = env.copy()

            # Enrich with current dir:
            env |= {"dir": dirNode}

            # Run a __config__.py file, if one exists.
            configEnv = env.copy()
            if Fs.configFileName in (f.fileName for f in dirNode.files):
                print(
                    f"{Fore.dark_orange}Running:{Style.reset}",
                    os.path.join(dirNode.fullPath, Fs.configFileName),
                )
                exec(Fs.readfile(Fs.configFileName), configEnv)
            env |= self.getModuleVars(configEnv)

            # Ordering Note: We must recurse into the subdirectories first.
            for d in dirNode.subDirs:
                with enterDir(d.dirName):
                    walk(d, env)

            # Ordering Note: Files in the current directory must be processed after
            # all subdirectories have been processed so that they have access to
            # information about the subdirectories.
            for f in filter(lambda f: not f.isIndex(), dirNode.files):
                if isinstance(f, PyPageNode):
                    self.invokePyPage(f, env)
            # We must process the index file last.
            indexFilter = filter(lambda f: f.isIndex(), dirNode.files)
            indexFile: Optional[FileNode] = next(indexFilter, None)
            if indexFile is not None and isinstance(indexFile, PyPageNode):
                self.invokePyPage(indexFile, env)

        initial_env = self.getBasicHelpers()
        walk(self.rootDir, initial_env)

    @staticmethod
    def fixSysPath() -> None:
        """
        This is necessary for import statements inside executed .py to consider the current directory.
        Without this, for example, an import statement inside a `__config__.py` file will error out.
        See: https://stackoverflow.com/questions/57870498/cannot-find-module-after-change-directory
        """
        sys.path.insert(0, "")

    @staticmethod
    def getModuleVars(env: Dict[str, Any]) -> Dict[str, Any]:
        return {
            k: v
            for k, v in env.items()
            if (not k.startswith("_") and not isinstance(v, types.ModuleType))
        }

    @staticmethod
    def getBasicHelpers() -> Dict[str, Any]:
        return {"readfile": Fs.readfile, "sh": sh}

    @staticmethod
    def splitPath(path: str) -> List[str]:
        head, tail = os.path.split(path)
        if head == "":
            return [path]
        return Content.splitPath(head) + [tail]

    @staticmethod
    def getTemplateHtml(env: dict[str, Any]) -> str:
        if "template" not in env:
            raise AltezaException(
                "You must define a `template` var in some ancestral `__config__.py` file."
            )
        template = env["template"]
        if not isinstance(template, str):
            raise AltezaException("The `template` must be a string.")
        return template


@contextmanager
def enterDir(newDir: str) -> Generator[None, None, None]:
    # https://stackoverflow.com/a/13847807/908430
    oldDir = os.getcwd()
    os.chdir(newDir)
    try:
        yield
    finally:
        os.chdir(oldDir)


def run(args: Args) -> None:
    startTimeNs = time_ns()
    contentDir = args.content
    if not os.path.isdir(contentDir):
        raise AltezaException(
            f"The provided path '{contentDir}' does not exist or is not a directory."
        )

    with enterDir(args.content):
        fs = Fs()
        print(fs.nameRegistry)
        content = Content(args, fs)
        print("Processing...\n")
        content.process()
        print("\nSuccessfully completed processing.\n")

    print("File Tree:")
    print(fs.rootDir.displayDir())

    generate(args, content)

    elapsedMilliseconds = (time_ns() - startTimeNs) / 10**6
    # pylint: disable=consider-using-f-string
    print("\nTime elapsed: %.2f ms" % elapsedMilliseconds)


def generate(args: Args, content: Content) -> None:
    outputDir = args.output

    def walk(curDir: DirNode) -> None:
        for subDir in curDir.subDirs:
            if subDir.shouldPublish:
                os.mkdir(subDir.dirName)
                with enterDir(subDir.dirName):
                    walk(subDir)

        for fileNode in curDir.files:
            if fileNode.shouldPublish:
                if isinstance(fileNode, PyPageNode):
                    if isinstance(fileNode, Md):
                        os.mkdir(fileNode.realName)
                        with enterDir(fileNode.realName):
                            with open("index.html", "w", encoding="utf-8") as pageHtml:
                                pageHtml.write(fileNode.getPyPageOutput())

                    elif isinstance(fileNode, NonMd):
                        fileName = fileNode.rectifiedFileName
                        if os.path.exists(fileName):
                            raise AltezaException(
                                f"File {fileName} already exists, and conflicts with {fileNode}."
                            )
                        with open(fileName, "w", encoding="utf-8") as nonMdPage:
                            nonMdPage.write(fileNode.getPyPageOutput())

                    else:
                        raise AltezaException(
                            f"{fileNode} pyPage attribute is invalid."
                        )

                else:
                    if args.copy_assets:
                        shutil.copyfile(fileNode.absoluteFilePath, fileNode.fileName)
                    else:
                        os.symlink(fileNode.absoluteFilePath, fileNode.fileName)

    resetOutputDir(outputDir)

    print("Generating...")

    with enterDir(outputDir):
        walk(content.rootDir)


def resetOutputDir(outputDir: str) -> None:
    if os.path.isfile(outputDir):
        raise AltezaException(
            f"A file named {outputDir} already exists. Please move it or delete it. "
            "Note that if this had been a directory, we would have erased it."
        )
    if os.path.isdir(outputDir):
        print(
            f"Deleting directory {Fore.dark_red_2}%s{Style.reset} and all of its content...\n"
            % outputDir
        )
        shutil.rmtree(outputDir)
    os.mkdir(outputDir)
