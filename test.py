#!/usr/bin/env python3

# pyre-strict

import os, yaml, sys, time, logging
import markdown # pyre-ignore
from pypage import pypage
from watchdog.observers import Observer # pyre-ignore
from watchdog.events import LoggingEventHandler # pyre-ignore
from typing import Dict, List, Tuple


class FsNode(object):
    def __init__(self, dir_path: str, name: str) -> None:
        self.name: str = name
        self.dir_path: str = dir_path
        self.abs_path: str = os.path.abspath(os.path.join(self.dir_path, self.name))

    def __repr__(self) -> str:
        return self.abs_path

class FileNode(FsNode):
    pass

class DirNode(FsNode):
    def __init__(self, dir_path: str) -> None:
        _, sub_dir_names, file_names = next(os.walk(dir_path))
        dir_name: str = os.path.split(dir_path)[-1]
        super().__init__(dir_path, dir_name)
        self.files: List[FileNode] = [FileNode(dir_path, file_name) for file_name in file_names]
        self.sub_dirs: List[DirNode] = [DirNode(os.path.join(dir_path, dir_name)) for dir_name in sub_dir_names]

    def display(self, indent: int = 0) -> str:
        return (' ' * 4 * indent) + '%s -> %s\n' % (self, self.files) + ''.join(subDir.display(indent + 1) for subDir in self.sub_dirs)


class Metadata(object):
    def __init__(self, metadata_dict: Dict[str, str]) -> None:
        self.metadata_dict = metadata_dict
    def __repr__(self) -> str:
        return '\n'.join('%s : %s' % (k, v) for k, v in self.metadata_dict.items())


def render(content_dir: str, output_dir: str) -> None:
    root = DirNode(content_dir)
    print(root.display())


###############################################################################


def process_markdown(md_filename: str) -> Tuple[Metadata, str]:
    with open(md_filename) as f:
        text = f.read()

    md = markdown.Markdown(extensions = ['meta'])
    html = md.convert(text)
    yaml_front_matter = ''

    for name, lines in md.Meta.items(): # pylint: disable=no-member
        yaml_front_matter += '%s : %s \n' % (name, lines[0])
        for line in lines[1:]:
            yaml_front_matter += ' ' * ( len(name) + 3 ) + line + '\n'

    yaml_metadata = yaml.safe_load(yaml_front_matter)
    metadata = Metadata(yaml_metadata)
    return metadata, html


def test_markdown_processing() -> None:
    # pylint: disable=unused-variable
    metadata, html = process_markdown('simple.md')
    print(metadata)


def test_change_monitoring() -> None:
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    event_handler = LoggingEventHandler() # type: ignore
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
    render('test_content', 'test_output')
    # test_markdown_processing()
    # test_change_monitoring()
