from core.common_imports import *


class Metadata(object):
    def __init__(self, metadataDict: Dict[str, str]) -> None:
        self.metadataDict = metadataDict

    def __repr__(self) -> str:
        return "\n".join("%s : %s" % (k, v) for k, v in self.metadataDict.items())


def processMarkdownFile(markdownFileName: str) -> tuple[Metadata, str]:
    with open(markdownFileName) as f:
        text = f.read()

    md = markdown.Markdown(extensions=["meta"])
    html: str = md.convert(text)
    yamlFrontMatter = ""

    for name, lines in md.Meta.items():  # type: ignore [attr-defined]
        yamlFrontMatter += "%s : %s \n" % (name, lines[0])
        for line in lines[1:]:
            yamlFrontMatter += " " * (len(name) + 3) + line + "\n"

    yamlMetadata = yaml.safe_load(yamlFrontMatter)
    metadata: Metadata = Metadata(yamlMetadata)
    return metadata, html
