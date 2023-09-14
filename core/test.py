from core.engine import process


def run() -> None:
    contentDir = "test_content"
    outputDir = "test_output"
    process(contentDir, outputDir)
