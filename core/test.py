from watchdog.observers import Observer  # pyre-ignore
from watchdog.events import LoggingEventHandler  # pyre-ignore

from core.engine import *


def testMarkdownProcessing() -> None:
    # pylint: disable=unused-variable
    metadata, html = processMarkdownFile("test_content/sectionY/simple.md")
    print(metadata)


def testChangeDetectionMonitoring() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    eventHandler = LoggingEventHandler()  # type: ignore
    observer = Observer()
    observer.schedule(eventHandler, path, recursive=True)
    observer.start()
    # try:
    #     while True:
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     observer.stop()
    time.sleep(1)
    observer.stop()
    observer.join()


def run():
    # process("test_content", "test_output")
    testMarkdownProcessing()
    # testChangeDetectionMonitoring()
