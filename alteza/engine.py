import contextlib
import itertools
import json
import os
import shutil
import sys
import time
import types
from typing import Callable, Optional, Generator, List, Dict, Set, Any

import sh  # type: ignore
from pypage import pypage  # type: ignore
from tap import Tap
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer as WatchdogObserver

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
    PageNode,
    PyPageNode,
)


class Args(Tap):  # pyre-ignore[13]
    content: str  # Directory to read the input content from.
    output: str  # Directory to send the output to. WARNING: This will be deleted.
    clear_output_dir: bool = False  # Delete the output directory, if it already exists.
    copy_assets: bool = False  # Copy static assets instead of symlinking to them.
    seed: str = "{}"  # Seed JSON data to add to the initial root env.
    watch: bool = False  # Watch for content changes, and rebuild.


class Content:
    def __init__(self, args: Args, fs: Fs) -> None:
        self.args = args
        self.inTemplate: bool = False
        self.templateCache: Dict[str, str] = {}
        self.seenTemplateLinks: Set[FileNode] = set()
        self.rootDir: DirNode = fs.rootDir
        self.nameRegistry: NameRegistry = fs.nameRegistry
        self.seed: Dict[str, Any] = json.loads(args.seed)
        self.fixSysPath()

    def linkObj(
        self, srcFile: FileNode, dstFile: FileNode, pathOnly: bool = False
    ) -> str:
        if not pathOnly:
            srcFile.linksTo.append(dstFile)  # This is used to determine reachability.
            if dstFile not in self.seenTemplateLinks:
                print(
                    " " * (4 if self.inTemplate else 2)
                    + f"{Fore.grey_42}Linking to:{Style.reset} {dstFile.getLinkName()}",
                )
                if self.inTemplate:
                    self.seenTemplateLinks.add(dstFile)

        dstFileName = self.getFileUrlName(dstFile)

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
        if isinstance(srcFile, Md) and not srcFile.isIndex() and not pathOnly:
            relativePath = [".."] + relativePath

        relativePathStr = os.path.join("", *relativePath)
        return relativePathStr

    @staticmethod
    def getFileUrlName(dstFile: FileNode) -> str:
        if dstFile.isIndex():
            return ""
        if isinstance(dstFile, Md):
            return dstFile.realName
        if isinstance(dstFile, NonMd):
            return dstFile.rectifiedFileName
        return dstFile.fileName

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

        def linkObj(dstFile: FileNode, pathOnly: bool = False) -> str:
            return self.linkObj(pyPageNode, dstFile, pathOnly)

        def link(name: str, pathOnly: bool = False) -> str:
            dstFile: FileNode = self.nameRegistry.lookup(name)
            return linkObj(dstFile, pathOnly)

        def path(name: str) -> str:
            return link(name, True)

        env |= {"link": link}
        env |= {"linkObj": linkObj}
        env |= {"path": path}

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

        # TODO: Enrich with `file` enhanced with `env`.

        if "public" in env:
            if env["public"] is True:
                pyPageNode.makePublic()
            elif env["public"] is False:
                pyPageNode.shouldPublish = False

        if isinstance(pyPageNode, Md):
            templateHtml = self.getTemplateHtml(env)
            self.inTemplate = True
            # Re-process against `templateHtml` with PyPage:
            pyPageOutput = pypage(templateHtml, env | {"content": pyPageOutput})
            self.inTemplate = False

        pyPageNode.setPyPageOutput(pyPageOutput)
        pyPageNode.env = env

    def runConfigIfAny(self, dirNode: DirNode, env: dict[str, Any]) -> Dict[str, Any]:
        # Run a __config__.py file, if one exists.
        configEnv = env.copy()
        configFileL = [f for f in dirNode.files if f.fileName == Fs.configFileName]
        if configFileL:
            configFile: FileNode = configFileL[0]

            def path(name: str) -> str:
                return self.linkObj(configFile, self.nameRegistry.lookup(name), True)

            configEnv |= {"path": path}

            print(
                f"{Fore.dark_orange}Running:{Style.reset}",
                os.path.join(dirNode.fullPath, Fs.configFileName),
            )
            exec(Fs.readfile(Fs.configFileName), configEnv)
        return configEnv

    @staticmethod
    def getSkipNames(env: dict[str, Any]) -> List[str]:
        skipNames = []
        if "skip" in env:
            skipVar = env["skip"]
            if isinstance(skipVar, list):
                for skipName in skipVar:
                    if isinstance(skipName, str):
                        skipNames.append(skipName)
                    else:
                        raise AltezaException(
                            "`skip` must be a list of strings representing names to be skipped.\n"
                            + f"`{skipName}` is not a string."
                        )
            else:
                raise AltezaException("`skip` must be a list of names.")
        return skipNames

    def process(self) -> None:
        def walk(dirNode: DirNode, env: dict[str, Any]) -> None:
            env = env.copy()  # Duplicate env.
            env |= {"dir": dirNode}  # Enrich with current dir.
            env |= self.getModuleVars(self.runConfigIfAny(dirNode, env))  # Run config.
            skipNames = self.getSkipNames(env)  # Process `skip`.

            # Ordering Note: We must recurse into the subdirectories first.
            for d in dirNode.subDirs:
                if d.dirName not in skipNames:
                    with enterDir(d.dirName):
                        walk(d, env)

            # Ordering Note: Files in the current directory must be processed after
            # all subdirectories have been processed so that they have access to
            # information about the subdirectories.
            for pyPageNode in dirNode.getPyPagesOtherThanIndex():
                if pyPageNode.getLinkName() not in skipNames:
                    self.invokePyPage(pyPageNode, env)

            # We must process the index file last.
            indexPage: Optional[PageNode] = dirNode.getIndexPage()
            if indexPage is not None and isinstance(indexPage, PyPageNode):
                self.invokePyPage(indexPage, env)

            # TODO: Enrich dirNode with `env`/info from index?

        initial_env = self.seed | self.getBasicHelpers()

        walk(self.rootDir, initial_env)

        self.tracePublic()

    def tracePublic(self) -> None:
        """Make all nodes reachable from public nodes public. (Called after processing.)"""
        if "/" in self.nameRegistry.allFiles:
            # Always make the root (/) level index page public, if it exists.
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

    def getTemplateHtml(self, env: dict[str, Any]) -> str:
        if "layoutRaw" in env:
            templateRaw = env["layoutRaw"]
            if not isinstance(templateRaw, str):
                raise AltezaException("The `layoutRaw` must be a string.")
            print(f"  {Fore.purple_3}Applying raw template...{Style.reset}")
            return templateRaw
        if "layout" in env:
            templateName = env["layout"]
            print(
                f"  {Fore.purple_3}Applying template: "
                f"{Fore.blue_violet}{templateName}{Fore.purple_3}...{Style.reset}"
            )
            if templateName in self.templateCache:
                return self.templateCache[templateName]
            templateFile = self.nameRegistry.lookup(templateName)
            templateRaw = Fs.readfile(templateFile.absoluteFilePath)
            self.templateCache[templateName] = templateRaw
            return templateRaw
        raise AltezaException(
            "You must define a `layout` or `layoutRaw` in some ancestral `__config__.py` file."
        )


@contextlib.contextmanager
def enterDir(newDir: str) -> Generator[None, None, None]:
    # https://stackoverflow.com/a/13847807/908430
    oldDir = os.getcwd()
    os.chdir(newDir)
    try:
        yield
    finally:
        os.chdir(oldDir)


class Engine:
    # This class is just here to organize a bunch of related functions together.
    # This class should never be instantiated, and most functions not called directly.
    # Engine.generate(...) is called to write the output of a processed Content object.
    # Similarly, Engine.run(args) is used to invoke Alteza overall.
    @staticmethod
    def generateMdContents(md: Md) -> None:
        if os.path.exists("index.html"):
            raise AltezaException(
                f"An index.html already exists, and conflicts with {md}, at {os.getcwd()}."
            )
        with open("index.html", "w", encoding="utf-8") as pageHtml:
            pageHtml.write(md.getPyPageOutput())

    @staticmethod
    def generateMd(md: Md) -> None:
        if not md.isIndex():
            os.mkdir(md.realName)
            with enterDir(md.realName):
                Engine.generateMdContents(md)
        else:
            Engine.generateMdContents(md)

    @staticmethod
    def generateNonMd(nonMd: NonMd) -> None:
        fileName = nonMd.rectifiedFileName
        if os.path.exists(fileName):
            raise AltezaException(
                f"File {fileName} already exists, and conflicts with {nonMd}."
            )
        with open(fileName, "w", encoding="utf-8") as nonMdPageFile:
            nonMdPageFile.write(nonMd.getPyPageOutput())

    @staticmethod
    def generatePyPageNode(pyPageNode: PyPageNode) -> None:
        if isinstance(pyPageNode, Md):
            Engine.generateMd(pyPageNode)

        elif isinstance(pyPageNode, NonMd):
            Engine.generateNonMd(pyPageNode)

        else:
            raise AltezaException(f"{pyPageNode} pyPage attribute is invalid.")

    @staticmethod
    def generateStaticAsset(fileNode: FileNode, shouldCopy: bool) -> None:
        if shouldCopy:
            shutil.copyfile(fileNode.absoluteFilePath, fileNode.fileName)
        else:
            os.symlink(fileNode.absoluteFilePath, fileNode.fileName)

    @staticmethod
    def generate(args: Args, content: Content) -> None:
        def walk(curDir: DirNode) -> None:
            for subDir in filter(lambda node: node.shouldPublish, curDir.subDirs):
                os.mkdir(subDir.dirName)
                with enterDir(subDir.dirName):
                    walk(subDir)

            for fileNode in filter(lambda node: node.shouldPublish, curDir.files):
                if isinstance(fileNode, PyPageNode):
                    Engine.generatePyPageNode(fileNode)
                else:
                    Engine.generateStaticAsset(fileNode, args.copy_assets)

        with enterDir(args.output):
            walk(content.rootDir)

    @staticmethod
    def checkContentDir(contentDir: str) -> None:
        if not os.path.isdir(contentDir):
            raise AltezaException(
                f"The provided path '{contentDir}' does not exist or is not a directory."
            )

    @staticmethod
    def resetOutputDir(outputDir: str, shouldDelete: bool) -> None:
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
    def processContent(args: Args) -> Content:
        with enterDir(args.content):
            print("Analyzing content directory...")
            fs = Fs()
            print(fs.nameRegistry)
            content = Content(args, fs)
            print("Processing...\n")
            content.process()
            print("\nSuccessfully completed processing.\n")

        print("File Tree:")
        print(fs.rootDir.displayDir())

        return content

    @staticmethod
    def makeSite(args: Args) -> None:
        startTimeNs = time.time_ns()

        Engine.checkContentDir(args.content)
        Engine.resetOutputDir(args.output, args.clear_output_dir)

        content = Engine.processContent(args)
        print("Generating...")
        Engine.generate(args, content)

        elapsedMilliseconds = (time.time_ns() - startTimeNs) / 10**6
        # pylint: disable=consider-using-f-string
        print("\nSite generation complete. Time elapsed: %.2f ms" % elapsedMilliseconds)

    class WatchdogEventHandler(FileSystemEventHandler):
        def __init__(self) -> None:
            self.timeOfMostRecentEvent: Optional[int] = None

        def on_any_event(self, event: FileSystemEvent) -> None:
            self.timeOfMostRecentEvent = max(
                self.timeOfMostRecentEvent or 0, time.time_ns()
            )

    @staticmethod
    def runWatchdog(contentDir: str, action: Callable[[], None]) -> None:
        timeIntervalNs = 2 * 10**8
        timeIntervalSecs = 0.2

        def watching() -> None:
            print(f"\nWatching for changes in {contentDir}...")

        eventHandler = Engine.WatchdogEventHandler()
        observer = WatchdogObserver()
        observer.schedule(eventHandler, contentDir, recursive=True)
        observer.start()
        try:
            watching()
            while True:
                time.sleep(timeIntervalSecs)
                if eventHandler.timeOfMostRecentEvent:
                    timeSinceMostRecentEvent = time.time_ns() - (
                        eventHandler.timeOfMostRecentEvent or 0
                    )
                    if timeSinceMostRecentEvent > timeIntervalNs:
                        eventHandler.timeOfMostRecentEvent = None
                        print("\nDetected a change.\n")
                        action()
                        watching()
        finally:
            observer.stop()
            observer.join()

    @staticmethod
    def run(args: Args) -> None:
        Engine.makeSite(args)

        if args.watch:
            Engine.runWatchdog(args.content, lambda: Engine.makeSite(args))
