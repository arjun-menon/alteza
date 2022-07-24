from core.common_imports import *


class Metadata(object):
    def __init__(self, metadataDict: Dict[str, str]) -> None:
        self.metadataDict = metadataDict

    def __repr__(self) -> str:
        return "\n".join("%s : %s" % (k, v) for k, v in self.metadataDict.items())


def processMarkdownFile(markdownFileName: str) -> Tuple[Metadata, str]:
    with open(markdownFileName) as f:
        text = f.read()

    md = markdown.Markdown(extensions=["meta"])
    html = md.convert(text)
    yamlFrontMatter = ""

    for name, lines in md.Meta.items():  # pylint: disable=no-member
        yamlFrontMatter += "%s : %s \n" % (name, lines[0])
        for line in lines[1:]:
            yamlFrontMatter += " " * (len(name) + 3) + line + "\n"

    yamlMetadata = yaml.safe_load(yamlFrontMatter)
    metadata = Metadata(yamlMetadata)
    return metadata, html
