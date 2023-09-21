#!/usr/bin/env python3

from core.engine import process


def test_run() -> None:
    contentDir = "test_content"
    outputDir = "test_output"
    process(contentDir, outputDir)


def main() -> None:
    test_run()


if __name__ == "__main__":
    main()
