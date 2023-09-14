from typing import Optional
from core.common_imports import *


class Markdown(object):
    def __init__(self, metadata: Optional[Dict[str, str]], html: str) -> None:
        self.metadata: Dict[str, str] = metadata if metadata is not None else dict()
        self.html = html


def processMarkdownFile(markdownFileName: str) -> Markdown:
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
    return Markdown(yamlMetadata, html)
