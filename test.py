#!/usr/bin/env python3

import os, yaml, markdown
import sys, time, logging
from pypage import pypage
from watchdog.observers import Observer
from watchdog.events import LoggingEventHandler


class DirNode(object):
    def __init__(self, dir_path):
        self.dirPath = dir_path
        dir_path_components = os.path.split(dir_path)
        self.dirName = dir_path_components[-1]
        self.fileNames = None
        self.subDirs = None
        walk_result = next(os.walk(self.dirPath))
        print('Directory: ', *walk_result)
        dir_path, sub_dir_names, file_names = walk_result
        assert self.dirPath == dir_path
        self.fileNames = file_names
        self.subDirs = []
        for subDirName in sub_dir_names:
            subDir = DirNode(os.path.join(dir_path, subDirName))
            self.subDirs.append(subDir)

    def __repr__(self, indent=0):
        r = (' ' * 4 * indent) + '%s -> %s\n' % (self.dirName, self.fileNames)
        for subDir in self.subDirs:
            r += subDir.__repr__(indent + 1)
        return r


class Metadata(object):
    def __init__(self, metadata_dict):
        for k, v in metadata_dict.items():
            self.__dict__[k] = v
    def __repr__(self):
        return '\n'.join('%s : %s' % (k, v) for k, v in self.__dict__.items())


def render(content_dir, output_dir):
    root = DirNode(content_dir)
    print(root)

###############################################################################

def process_markdown(md_filename):
    with open(md_filename) as f:
        text = f.read()

    md = markdown.Markdown(extensions = ['meta'])
    html = md.convert(text)
    yaml_front_matter = ''

    for name, lines in md.Meta.items():
        yaml_front_matter += '%s : %s \n' % (name, lines[0])
        for line in lines[1:]:
            yaml_front_matter += ' ' * ( len(name) + 3 ) + line + '\n'

    yaml_metadata = yaml.load(yaml_front_matter)
    metadata = Metadata(yaml_metadata)
    return metadata, html


def test_markdown_processing():
    metadata, html = process_markdown('simple.md')
    print()
    print(metadata)
    print()
    print(metadata.title)


def test_change_monitoring():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    event_handler = LoggingEventHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    # try:
    #     while True:
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     observer.stop()
    time.sleep(2)
    observer.stop()
    observer.join()


if __name__ == "__main__":
    render('test_content', 'test_output')
    test_markdown_processing()
    test_change_monitoring()
