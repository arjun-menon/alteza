#!/usr/bin/env python3

from argparse import ArgumentParser, Namespace

from core.engine import process


def test_run(args: Namespace) -> None:
    contentDir = "test_content"
    outputDir = "test_output"
    process(args, contentDir, outputDir)


def main() -> None:
    parser = ArgumentParser(description="Appletree: Flexible Static Site Generator")
    parser.add_argument(
        "--copy-assets",
        action="store_true",
        default=False,
        help="Copy assets instead of symlinking to them",
    )
    parser.add_argument(
        "--trailing-slash",
        action="store_true",
        default=False,
        help="Include a trailing slash in links to markdown pages",
    )
    args: Namespace = parser.parse_args()

    test_run(args)


if __name__ == "__main__":
    main()
