import os
import sys
import types
import shutil
import sh  # type: ignore
from tap import Tap
from time import time_ns
from contextlib import contextmanager
from typing import Generator, List, Dict, Any
from pypage import pypage  # type: ignore
from .fs import (
    FileNode,
    DirNode,
    displayDir,
    NameRegistry,
    fs_crawl,
    Md,
    Page,
    NonMd,
    readfile,
    config_py_file,
    Fore,
    Style,
)


class Args(Tap):  # pyre-ignore[13]
    content: str  # Directory to read the input content from.
    output: str  # Directory to send the output. WARNING: This will be deleted.
    copy_assets: bool = False  # Copy assets instead of symlinking to them
    trailing_slash: bool = (
        False  # Include a trailing slash for links to markdown page directories
    )


class Content(object):
    def __init__(
        self, args: Args, rootDir: DirNode, nameRegistry: NameRegistry
    ) -> None:
        self.args = args
        self.rootDir: DirNode = rootDir
        self.nameRegistry = nameRegistry
        self.fixSysPath()

    def link(self, srcFile: FileNode, name: str) -> str:
        print(f"  {Fore.grey_42}Linking to:{Style.reset}", name)
        dstFile: FileNode = self.nameRegistry.lookup(name)
        dstFile.makePublic()  # FixMe: Circular links can make pages public.

        dstFileName = dstFile.fileName
        if isinstance(dstFile.page, NonMd):
            dstFileName = dstFile.page.rectifiedFileName
        elif isinstance(dstFile.page, Md):
            dstFileName = (
                dstFile.pageName
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
        if isinstance(srcFile.page, Md):
            relativePath = [".."] + relativePath

        relativePathStr = os.path.join("", *relativePath)

        return relativePathStr

    def invokePyPage(self, fileNode: FileNode, env: dict[str, Any]) -> None:
        assert fileNode.page is not None
        print(f"{Fore.dark_orange}Processing:{Style.reset}", fileNode.fullPath)
        env = env.copy()

        # Enrich with current file:
        env |= {"file": fileNode}

        toProcessFurther: str
        if isinstance(fileNode.page, NonMd) or isinstance(fileNode.page, Md):
            toProcessFurther = readfile(fileNode.absoluteFilePath)
        else:
            raise Exception(f"{fileNode} pyPage attribute is invalid.")

        # Inject link
        def link(name: str) -> str:
            return self.link(fileNode, name)

        env |= {"link": link}

        if isinstance(fileNode.page, Page):
            env |= {"lastUpdated": fileNode.page.lastUpdated}
        if isinstance(fileNode.page, Md) and fileNode.page.draftDate is not None:
            env |= {"draftDate": fileNode.page.draftDate}

        # Invoke pypage
        pyPageOutput = pypage(toProcessFurther, env)

        # Perform Markdown processing
        if isinstance(fileNode.page, Md):
            mdResult = Md.processMarkdown(pyPageOutput)
            env.update(mdResult.metadata)
            pyPageOutput = mdResult.html

        if "public" in env:
            if env["public"] is True:
                fileNode.makePublic()
            elif env["public"] is False:
                fileNode.shouldPublish = False

        if isinstance(fileNode.page, Md):
            templateHtml = Content.getTemplateHtml(env)
            # Re-process against `templateHtml` with PyPage:
            pyPageOutput = pypage(templateHtml, env | {"body": pyPageOutput})

        fileNode.pyPageOutput = pyPageOutput

    def process(self) -> None:
        def walk(node: DirNode, env: dict[str, Any]) -> None:
            env = env.copy()

            # Enrich with current dir:
            env |= {"dir": node}

            # Run a __config__.py file, if one exists.
            configEnv = env.copy()
            if config_py_file in (f.fileName for f in node.files):
                print(
                    f"{Fore.gold_1}Running:{Style.reset}",
                    os.path.join(node.fullPath, config_py_file),
                )
                exec(readfile(config_py_file), configEnv)
            env |= self.getModuleVars(configEnv)

            # Ordering Note: We must recurse into the subdirectories first.
            for d in node.subDirs:
                with enterDir(d.dirName):
                    walk(d, env)

            # Ordering Note: Files in the current directory must be processed after
            # all subdirectories have been processed so that they have access to
            # information about the subdirectories.
            for f in node.files:
                if f.page is not None:
                    self.invokePyPage(f, env)

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
        return {"readfile": readfile, "sh": sh}

    @staticmethod
    def splitPath(path: str) -> List[str]:
        head, tail = os.path.split(path)
        if head == "":
            return [path]
        else:
            return Content.splitPath(head) + [tail]

    @staticmethod
    def getTemplateHtml(env: dict[str, Any]) -> str:
        if "template" not in env:
            raise Exception(
                "You must define a `template` var in some ancestral `__config__.py` file."
            )
        template = env["template"]
        if not isinstance(template, str):
            raise Exception("The `template` must be a string.")
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
        raise Exception(f"The provided path '{contentDir}' is not a directory.")

    with enterDir(args.content):
        rootDir, nameRegistry = fs_crawl()
        print(nameRegistry)
        content = Content(args, rootDir, nameRegistry)
        print("Processing...\n")
        content.process()
        print("\nSuccessfully completed processing.\n")

    print("File Tree:")
    print(displayDir(rootDir))

    generate(args, content)

    elapsedMilliseconds = (time_ns() - startTimeNs) / 10**6
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
                if fileNode.page is not None:
                    assert fileNode.pyPageOutput is not None
                    assert isinstance(fileNode.pyPageOutput, str)

                    if isinstance(fileNode.page, Md):
                        os.mkdir(fileNode.pageName)
                        with enterDir(fileNode.pageName):
                            with open("index.html", "w") as pageHtml:
                                pageHtml.write(fileNode.pyPageOutput)
                    elif isinstance(fileNode.page, NonMd):
                        fileName = fileNode.page.rectifiedFileName
                        if os.path.exists(fileName):
                            raise Exception(
                                f"File {fileName} already exists, and conflicts with {fileNode}."
                            )
                        with open(fileName, "w") as nonMdFile:
                            nonMdFile.write(fileNode.pyPageOutput)

                    else:
                        raise Exception(f"{fileNode} pyPage attribute is invalid.")

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
        raise Exception(
            "There already exists a file named %s. (Please move/delete it.)" % outputDir
        )
    if os.path.isdir(outputDir):
        print(
            f"Deleting directory {Fore.dark_red_2}%s{Style.reset} and all of its content...\n"
            % outputDir
        )
        shutil.rmtree(outputDir)
    os.mkdir(outputDir)
