
import yaml, markdown

with open('simple.md') as f:
    text = f.read()

md = markdown.Markdown(extensions = ['meta'])

html = md.convert(text)
# print html

yaml_frontmatter = str()

for name, lines in md.Meta.iteritems():
    yaml_frontmatter += '%s : %s \n' % (name, lines[0])
    for line in lines[1:]:
        yaml_frontmatter += ' ' * ( len(name) + 3 ) + line + '\n'

print yaml_frontmatter

yaml_metadata = yaml.load(yaml_frontmatter)

print yaml_metadata

class Metadata(object):
    def __init__(self, metadata_dict):
        self.metadata_dict = metadata_dict
        for k, v in metadata_dict.iteritems():
            self.__dict__[k] = v
    def __repr__(self):
        return '\n'.join('%s : %s' % (k, v) for k, v in yaml_metadata.iteritems())

metadata = Metadata(yaml_metadata)

print 
print metadata
print 
print metadata.title
