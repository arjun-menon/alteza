#!/usr/bin/env python3
from .engine import run, Args


def main() -> None:
    run(Args().parse_args())


# See: https://chriswarrick.com/blog/2014/09/15/python-apps-the-right-way-entry_points-and-scripts/

if __name__ == "__main__":
    main()
