from core.common_imports import *
from core.gather_files import gather_files, displayDir


def process(contentDir: str, outputDir: str) -> None:
    content = gather_files(contentDir)

    print("Input File Tree:")
    print(displayDir(content.root))
    print(content.nameRegistry)
