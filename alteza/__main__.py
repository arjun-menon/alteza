#!/usr/bin/env python3
from .driver import Engine, Args


def main() -> None:
	Engine(Args().parse_args()).run()


# See: https://chriswarrick.com/blog/2014/09/15/python-apps-the-right-way-entry_points-and-scripts/

if __name__ == '__main__':
	main()
