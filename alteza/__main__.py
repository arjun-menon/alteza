#!/usr/bin/env python3
import sys
from .driver import Driver, Args


def main() -> int:
	return Driver(Args().parse_args()).run()


# See: https://chriswarrick.com/blog/2014/09/15/python-apps-the-right-way-entry_points-and-scripts/

if __name__ == '__main__':
	sys.exit(main())
