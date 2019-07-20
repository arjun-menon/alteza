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
    def __init__(self, dir_path: str, name: str, is_dir: bool) -> None:
        self.dir_path: str = dir_path
        self.name: str = name
        self.full_path: str = self.dir_path if is_dir else os.path.join(
            self.dir_path, self.name
        )

    def __repr__(self) -> str:
        return self.full_path


class FileNode(FsNode):
    def __init__(self, dir_path: str, name: str) -> None:
        super().__init__(dir_path, name, False)

        self.basename: str = ""
        self.extname: str = ""
        self.basename, self.extname = os.path.splitext(name)


class DirNode(FsNode):
    def __init__(self, dir_path: str, all_files: DefaultDict[str, Set[str]]) -> None:
        _, sub_dir_names, file_names = next(os.walk(dir_path))
        dir_name: str = os.path.split(dir_path)[-1]
        super().__init__(dir_path, dir_name, True)

        self.files: List[FileNode] = [
            FileNode(dir_path, file_name) for file_name in file_names
        ]
        for file_name in file_names:
            all_files[file_name].add(os.path.join(dir_path, file_name))

        self.sub_dirs: List[DirNode] = [
            DirNode(os.path.join(dir_path, dir_name), all_files)
            for dir_name in sub_dir_names
        ]

    def display(self, indent: int = 0) -> str:
        return (
            (" " * 4 * indent)
            + "%s -> %s\n" % (self, self.files)
            + "".join(subDir.display(indent + 1) for subDir in self.sub_dirs)
        )


class Content(object):
    def __init__(self, content_dir: str) -> None:
        self.content_dir_abspath: str = os.path.abspath(content_dir)
        os.chdir(self.content_dir_abspath)
        self.all_files: DefaultDict[str, Set[str]] = defaultdict(set)
        self.root = DirNode(".", self.all_files)
        print(self.root.display())

    def process(self) -> None:
        print()
        print(self.all_files)
        pass


class Metadata(object):
    def __init__(self, metadata_dict: Dict[str, str]) -> None:
        self.metadata_dict = metadata_dict

    def __repr__(self) -> str:
        return "\n".join("%s : %s" % (k, v) for k, v in self.metadata_dict.items())


def reset_output_dir(output_dir: str) -> None:
    if os.path.isfile(output_dir):
        raise Exception("There is a file named %s." % output_dir)
    if os.path.isdir(output_dir):
        print("Deleting directory %s and all of its content..." % output_dir)
        shutil.rmtree(output_dir)
    os.mkdir(output_dir)


def mandrake(content_dir: str, output_dir: str) -> None:
    reset_output_dir(output_dir)

    content = Content(content_dir)

    print("Processing...")
    content.process()


###############################################################################


def process_markdown(md_filename: str) -> Tuple[Metadata, str]:
    with open(md_filename) as f:
        text = f.read()

    md = markdown.Markdown(extensions=["meta"])
    html = md.convert(text)
    yaml_front_matter = ""

    for name, lines in md.Meta.items():  # pylint: disable=no-member
        yaml_front_matter += "%s : %s \n" % (name, lines[0])
        for line in lines[1:]:
            yaml_front_matter += " " * (len(name) + 3) + line + "\n"

    yaml_metadata = yaml.safe_load(yaml_front_matter)
    metadata = Metadata(yaml_metadata)
    return metadata, html


def test_markdown_processing() -> None:
    # pylint: disable=unused-variable
    metadata, html = process_markdown("simple.md")
    print(metadata)


def test_change_monitoring() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    event_handler = LoggingEventHandler()  # type: ignore
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
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
    # test_markdown_processing()
    # test_change_monitoring()
