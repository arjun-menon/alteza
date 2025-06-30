import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any

import pygit2  # type: ignore


class AltezaException(Exception):
	"""Alteza Exception"""


@dataclass
class PublicNodeCounts:
	fileCount: int = 0
	dirCount: int = 0

	def total(self) -> int:
		return self.fileCount + self.dirCount


class StopWatch:
	def __init__(self) -> None:
		self.startNs: int = 0
		self.endNs: int = 0
		self.t: int = 0

	def __enter__(self) -> 'StopWatch':
		self.startNs = time.perf_counter_ns()
		return self

	def __exit__(self, *args: Any) -> None:
		self.endNs = time.perf_counter_ns()
		self.t = self.endNs - self.startNs


@dataclass
class MultiRunTimes:
	times: List[int] = field(default_factory=list)

	def add(self, sw: StopWatch) -> None:
		self.times.append(sw.t)

	def total(self) -> int:
		return sum(self.times)

	def count(self) -> int:
		return len(self.times)

	def average(self) -> float:
		return sum(self.times) / self.count()


# pylint: disable=too-many-branches, no-member
def getFilesCommitDates(filePaths: List[str], repoPath: str = '.') -> Dict[str, Tuple[datetime, datetime]]:
	"""
	Get the first commit date (file introduction) and last commit date (last modified)
	for a list of files, handling renames correctly.

	Args:
	    filePaths: List of file paths relative to the repository root
	    repoPath: Path to the git repository, defaults to current directory

	Returns:
	    Dictionary mapping each file path to a tuple of (first_commit_date, last_commit_date)
	    Both dates are datetime objects.
	"""
	repo = pygit2.Repository(repoPath)  # type: ignore
	result: Dict[str, Tuple[datetime, datetime]] = {}

	# Track file history through renames
	fileHistory: Dict[str, Dict[str, datetime]] = {}

	# Initialize tracking for each file
	for filePath in filePaths:
		fileHistory[filePath] = {'first': None, 'last': None}  # type: ignore

	# Walk through all commits from newest to oldest
	walker = repo.walk(repo.head.target, pygit2.GIT_SORT_TIME | pygit2.GIT_SORT_REVERSE)  # type: ignore

	for commit in walker:
		commit_date = datetime.fromtimestamp(commit.commit_time)

		# Get the diff for this commit
		if len(commit.parents) == 0:
			# Initial commit - compare against empty tree
			parent_tree = None
		else:
			# Regular commit - compare against first parent
			parent_tree = commit.parents[0].tree

		try:
			diff = repo.diff(parent_tree, commit.tree)  # type: ignore
		except Exception:
			# Skip if we can't get the diff
			continue

		# Process each delta (file change) in the diff
		for delta in diff.deltas:  # type: ignore
			old_file = delta.old_file.path if delta.old_file else None
			new_file = delta.new_file.path if delta.new_file else None

			# Check if this change involves any of our tracked files
			files_to_update = set()

			# Handle different types of changes
			if delta.status == pygit2.GIT_DELTA_ADDED and new_file:  # type: ignore
				# File was added
				if new_file in filePaths:
					files_to_update.add(new_file)
			elif delta.status == pygit2.GIT_DELTA_MODIFIED and new_file:  # type: ignore
				# File was modified
				if new_file in filePaths:
					files_to_update.add(new_file)
			elif delta.status == pygit2.GIT_DELTA_RENAMED:  # type: ignore
				# File was renamed
				if old_file in filePaths:
					# Update the tracking to follow the rename
					if new_file and new_file not in fileHistory:
						fileHistory[new_file] = fileHistory[old_file].copy()
					files_to_update.add(old_file)
				if new_file in filePaths:
					files_to_update.add(new_file)
			elif delta.status == pygit2.GIT_DELTA_DELETED and old_file:  # type: ignore
				# File was deleted - this could be the last modification
				if old_file in filePaths:
					files_to_update.add(old_file)

			# Update the commit dates for affected files
			for filePath in files_to_update:
				if filePath in fileHistory:
					# Update first commit date (earliest)
					if fileHistory[filePath]['first'] is None:
						fileHistory[filePath]['first'] = commit_date
					else:
						fileHistory[filePath]['first'] = min(fileHistory[filePath]['first'], commit_date)

					# Update last commit date (latest)
					if fileHistory[filePath]['last'] is None:
						fileHistory[filePath]['last'] = commit_date
					else:
						fileHistory[filePath]['last'] = max(fileHistory[filePath]['last'], commit_date)

	# Build the result dictionary
	for filePath in filePaths:
		if filePath in fileHistory and fileHistory[filePath]['first'] is not None:
			result[filePath] = (
				fileHistory[filePath]['first'],
				fileHistory[filePath]['last'] or fileHistory[filePath]['first'],
			)

	return result
