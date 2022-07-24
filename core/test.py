from core.engine import *


def resetOutputDir(outputDir: str) -> None:
    if os.path.isfile(outputDir):
        raise Exception('There is a file named %s.' % outputDir)
    if os.path.isdir(outputDir):
        print('Deleting directory %s and all of its content...\n' % outputDir)
        shutil.rmtree(outputDir)
    os.mkdir(outputDir)


def testEngineProcessing() -> None:
    contentDir = "test_content"
    outputDir = "test_output"

    resetOutputDir(outputDir)

    process(contentDir, outputDir)


def testMarkdownProcessing() -> None:
    # pylint: disable=unused-variable
    metadata, html = processMarkdownFile("test_content/sectionY/simple.md")
    print(metadata)


def run():
    testEngineProcessing()
    # testMarkdownProcessing()
