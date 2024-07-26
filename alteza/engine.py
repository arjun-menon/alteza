import contextlib
import itertools
import json
import os
import shutil
import sys
import time
import types
from typing import Optional, Generator, List, Dict, Set, Any

import sh  # type: ignore
from pypage import pypage  # type: ignore
from tap import Tap

from .fs import (
    FsNode,
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
    clear_output_dir: bool = False  # Delete the output directory, if it already exists.
    copy_assets: bool = False  # Copy static assets instead of symlinking to them.
    seed: str = "{}"  # Seed JSON data to add to the initial root env.


class Content:
    def __init__(self, args: Args, fs: Fs) -> None:
        self.args = args
        self.indentSpaces: int = 2
        self.rootDir: DirNode = fs.rootDir
        self.nameRegistry: NameRegistry = fs.nameRegistry
        self.seed: Dict[str, Any] = json.loads(args.seed)
        self.fixSysPath()

    def linkObj(self, srcFile: PyPageNode, dstFile: FileNode) -> str:
        assert isinstance(dstFile, FileNode)
        dstName = dstFile.getLinkName()
        indentSpaces = " " * self.indentSpaces
        print(indentSpaces + f"{Fore.grey_42}Linking to:{Style.reset}", dstName)
        srcFile.linksTo.append(dstFile)

        if dstFile.isIndex():
            dstFileName = ""
        elif isinstance(dstFile, Md):
            dstFileName = dstFile.realName
        elif isinstance(dstFile, NonMd):
            dstFileName = dstFile.rectifiedFileName
        else:
            dstFileName = dstFile.fileName

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
        if isinstance(srcFile, Md) and not srcFile.isIndex():
            relativePath = [".."] + relativePath

        print("relPath:", relativePath)
        relativePathStr = os.path.join("", *relativePath)

        return relativePathStr

    def invokePyPage(self, pyPageNode: PyPageNode, env: dict[str, Any]) -> None:
        print(f"{Fore.gold_1}Processing:{Style.reset}", pyPageNode.fullPath)
        env = env.copy()

        # Enrich with current file:
        env |= {"file": pyPageNode}

        toProcessFurther: str
        if isinstance(pyPageNode, (Md, NonMd)):
            toProcessFurther = Fs.readfile(pyPageNode.absoluteFilePath)
        else:
            raise AltezaException(f"{pyPageNode} Unsupported type of PyPageNode.")

        def link(name: str) -> str:
            dstFile: FileNode = self.nameRegistry.lookup(name)
            return self.linkObj(pyPageNode, dstFile)

        def linkObj(dstFile: FileNode) -> str:
            return self.linkObj(pyPageNode, dstFile)

        env |= {"link": link}
        env |= {"linkObj": linkObj}

        env |= {"getLastModifiedObj": lambda: pyPageNode.lastModifiedObj}
        env |= {"getLastModified": pyPageNode.getLastModified}
        env |= {"getIdeaDateObj": pyPageNode.getIdeaDateObj}
        env |= {"getIdeaDate": pyPageNode.getIdeaDate}

        # Invoke pypage
        pyPageOutput = pypage(toProcessFurther, env)

        # Perform Markdown processing
        if isinstance(pyPageNode, Md):
            mdResult = Md.processMarkdown(pyPageOutput)
            env.update(mdResult.metadata)
            pyPageOutput = mdResult.html

        if "public" in env:
            if env["public"] is True:
                pyPageNode.makePublic()
            elif env["public"] is False:
                pyPageNode.shouldPublish = False

        if isinstance(pyPageNode, Md):
            print(
                f"  {Fore.purple_3}Applying template...{Style.reset}"
            )  # TODO (see ideas.md)
            templateHtml = Content.getTemplateHtml(env)
            self.indentSpaces += 2
            # Re-process against `templateHtml` with PyPage:
            pyPageOutput = pypage(templateHtml, env | {"content": pyPageOutput})
            self.indentSpaces -= 2

        pyPageNode.setPyPageOutput(pyPageOutput)
        pyPageNode.env = env

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

        initial_env = self.seed | self.getBasicHelpers()
        walk(self.rootDir, initial_env)

        self._makeNodesReachableFromPublicNodesPublic()

    def _makeNodesReachableFromPublicNodesPublic(self) -> None:
        if "/" in self.nameRegistry.allFiles:
            # Make the root (/) level index page public, if it exists.
            rootIndex = self.nameRegistry.allFiles["/"]
            rootIndex.makePublic()

        publicNodes: List["FsNode"] = []

        def gatherPublicNodes(fsNode: FsNode) -> None:
            if isinstance(fsNode, DirNode):
                for dirNode in itertools.chain(fsNode.subDirs, fsNode.files):
                    gatherPublicNodes(dirNode)
            if fsNode.shouldPublish:
                publicNodes.append(fsNode)

        gatherPublicNodes(self.rootDir)

        print("\nInitial pre-reachability public files:")
        for node in filter(lambda pNode: isinstance(pNode, FileNode), publicNodes):
            print("/" + node.fullPath)

        seen: Set["FsNode"] = set()

        def makeReachableNodesPublic(fsNode: FsNode) -> None:
            if fsNode in seen:
                return
            seen.add(fsNode)

            if not fsNode.shouldPublish:
                fsNode.makePublic()

            for linkedToNode in fsNode.linksTo:
                makeReachableNodesPublic(linkedToNode)

        for node in publicNodes:
            makeReachableNodesPublic(node)

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


class Generate:
    # pylint: disable=too-few-public-methods
    # This class is just here to organize a bunch of related functions together.
    # This class should never be instantiated. Generate.generate should
    # be called to write the output of a processed Content object.
    @staticmethod
    def _writeMdContents(md: Md) -> None:
        if os.path.exists("index.html"):
            raise AltezaException(
                f"An index.html already exists, and conflicts with {md}, at {os.getcwd()}."
            )
        with open("index.html", "w", encoding="utf-8") as pageHtml:
            pageHtml.write(md.getPyPageOutput())

    @staticmethod
    def _writeMd(md: Md) -> None:
        if not md.isIndex():
            os.mkdir(md.realName)
            with enterDir(md.realName):
                Generate._writeMdContents(md)
        else:
            Generate._writeMdContents(md)

    @staticmethod
    def _writeNonMd(nonMd: NonMd) -> None:
        fileName = nonMd.rectifiedFileName
        if os.path.exists(fileName):
            raise AltezaException(
                f"File {fileName} already exists, and conflicts with {nonMd}."
            )
        with open(fileName, "w", encoding="utf-8") as nonMdPageFile:
            nonMdPageFile.write(nonMd.getPyPageOutput())

    @staticmethod
    def _writePyPageNode(pyPageNode: PyPageNode) -> None:
        if isinstance(pyPageNode, Md):
            Generate._writeMd(pyPageNode)

        elif isinstance(pyPageNode, NonMd):
            Generate._writeNonMd(pyPageNode)

        else:
            raise AltezaException(f"{pyPageNode} pyPage attribute is invalid.")

    @staticmethod
    def _linkStaticAsset(fileNode: FileNode, shouldCopy: bool) -> None:
        if shouldCopy:
            shutil.copyfile(fileNode.absoluteFilePath, fileNode.fileName)
        else:
            os.symlink(fileNode.absoluteFilePath, fileNode.fileName)

    @staticmethod
    def _resetOutputDir(outputDir: str, shouldDelete: bool) -> None:
        if os.path.isfile(outputDir):
            raise AltezaException(
                f"A file named {outputDir} already exists. Please move it or delete it. "
                "Note that if this had been a directory, we would have erased it."
            )
        if os.path.isdir(outputDir):
            if not shouldDelete:
                raise AltezaException(
                    f"Specified output directory {outputDir} already exists.\n"
                    "Please use --clear_output_dir to delete it prior to site generation."
                )
            print(
                f"Deleting directory {Fore.dark_red_2}%s{Style.reset} and all of its content...\n"
                % outputDir
            )
            shutil.rmtree(outputDir)
        os.mkdir(outputDir)

    @staticmethod
    def generate(args: Args, content: Content) -> None:
        def walk(curDir: DirNode) -> None:
            for subDir in filter(lambda node: node.shouldPublish, curDir.subDirs):
                os.mkdir(subDir.dirName)
                with enterDir(subDir.dirName):
                    walk(subDir)

            for fileNode in filter(lambda node: node.shouldPublish, curDir.files):
                if isinstance(fileNode, PyPageNode):
                    Generate._writePyPageNode(fileNode)
                else:
                    Generate._linkStaticAsset(fileNode, args.copy_assets)

        outputDir = args.output
        Generate._resetOutputDir(outputDir, args.clear_output_dir)

        print("Generating...")
        with enterDir(outputDir):
            walk(content.rootDir)


@contextlib.contextmanager
def enterDir(newDir: str) -> Generator[None, None, None]:
    # https://stackoverflow.com/a/13847807/908430
    oldDir = os.getcwd()
    os.chdir(newDir)
    try:
        yield
    finally:
        os.chdir(oldDir)


def run(args: Args) -> None:
    startTimeNs = time.time_ns()
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

    Generate.generate(args, content)

    elapsedMilliseconds = (time.time_ns() - startTimeNs) / 10**6
    # pylint: disable=consider-using-f-string
    print("\nTime elapsed: %.2f ms" % elapsedMilliseconds)
