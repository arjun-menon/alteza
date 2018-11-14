#!/usr/bin/env python3

import os, yaml, markdown
import sys, time, logging
from pypage import pypage
from watchdog.observers import Observer
from watchdog.events import LoggingEventHandler

class DirNode(object):
    def __init__(self, dirPath):
        self.dirPath = dirPath
        dirPathComponents = os.path.split(dirPath)
        self.dirName = dirPathComponents[-1]
        self.fileNames = None
        self.subDirs = None

    def establish(self):
        print('Directory: ', self.dirPath, end='')
        walkResult = next(os.walk(self.dirPath))
        print(walkResult)
        dirPath, subDirNames, fileNames = walkResult
        assert self.dirPath == dirPath
        self.fileNames = fileNames
        self.subDirs = []
        for subDirName in subDirNames:
            subDir = DirNode(os.path.join(dirPath, subDirName))
            subDir.establish()
            self.subDirs.append(subDir)

    def __repr__(self, indent=0):
        r = (' ' * 4 * indent) + '%s -> %s\n' % (self.dirName, self.fileNames)
        for subDir in self.subDirs:
            r += subDir.__repr__(1)
        return r

root = DirNode('test_content')
root.establish()
print(root)

# for dirpath, dirnames, filenames in os.walk('test_content'):
#     print('--------------------------------------------')
#     print(dirpath, dirnames, filenames)
#
#     # print path to all subdirectories first.
#     # for subdirname in dirnames:
#     #     print(os.path.join(dirpath, subdirname))
#
#     # print path to all filenames.
#     # for filename in filenames:
#     #     print(os.path.join(dirpath, filename))

with open('simple.md') as f:
    text = f.read()

md = markdown.Markdown(extensions = ['meta'])

html = md.convert(text)
# print html

yaml_frontmatter = str()

for name, lines in md.Meta.items():
    yaml_frontmatter += '%s : %s \n' % (name, lines[0])
    for line in lines[1:]:
        yaml_frontmatter += ' ' * ( len(name) + 3 ) + line + '\n'

print(yaml_frontmatter)

yaml_metadata = yaml.load(yaml_frontmatter)

print(yaml_metadata)

class Metadata(object):
    def __init__(self, metadata_dict):
        self.metadata_dict = metadata_dict
        for k, v in metadata_dict.items():
            self.__dict__[k] = v
    def __repr__(self):
        return '\n'.join('%s : %s' % (k, v) for k, v in yaml_metadata.items())

metadata = Metadata(yaml_metadata)

print() 
print(metadata)
print() 
print(metadata.title)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    event_handler = LoggingEventHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
