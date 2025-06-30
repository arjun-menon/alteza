#!/usr/bin/env python3
import time
from sys import exit
from .driver import Driver, Args


def main() -> int:
	return Driver(Args().parse_args()).run()


# See: https://chriswarrick.com/blog/2014/09/15/python-apps-the-right-way-entry_points-and-scripts/

if __name__ == '__main__':
	rc = main()
	if rc != 0:
		print(f'Exiting with error code {rc}...')
		time.sleep(3)
		exit(rc)
