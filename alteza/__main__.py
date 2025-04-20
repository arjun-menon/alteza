#!/usr/bin/env python3
from .driver import Driver, Args


def main() -> None:
	Driver(Args().parse_args()).run()


# See: https://chriswarrick.com/blog/2014/09/15/python-apps-the-right-way-entry_points-and-scripts/

if __name__ == '__main__':
	main()
