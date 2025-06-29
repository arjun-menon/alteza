from setuptools import setup

from alteza.version import version, name, repo_url, download_url, author, author_email

setup(
	name=name,
	version=version,
	python_requires='>=3.10',
	description='Super-flexible Static Site Generator',
	# Ref: https://packaging.python.org/en/latest/discussions/install-requires-vs-requirements/
	install_requires=[
		# Standard dependencies:
		'pypage >= 2.2.1',
		'markdown >= 3.6',
		'mdx-breakless-lists >= 1.0.1',
		'mdx_truly_sane_lists >= 1.3',
		'pygments >= 2.16.1',
		'pyyaml >= 6.0.1',
		'colored >= 2.2.4',
		'sh >= 2.0.7',
		'typed-argument-parser >= 1.10.1',
		'watchdog >= 4.0.1',
		'tqdm >= 4.67.1',
		'pygit2 >= 1.16.2',
	],
	long_description=open('README.md').read(),
	long_description_content_type='text/markdown',
	url=repo_url,
	download_url=download_url,
	author=author,
	author_email=author_email,
	keywords=['static site generator', 'static sites', 'ssg'],
	license='AGPL-3.0-or-later',
	# Ref:https://docs.python.org/3.11/distutils/examples.html
	packages=['alteza'],
	entry_points={
		'console_scripts': [f'{name}=alteza.__main__:main'],
	},
	classifiers=[
		'Development Status :: 4 - Beta',
		'Intended Audience :: Developers',
		'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
		'Topic :: Internet :: WWW/HTTP :: Dynamic Content :: Content Management System',
		'Topic :: Internet :: WWW/HTTP :: Site Management',
		'Topic :: Software Development :: Libraries :: Python Modules',
		'Topic :: Text Processing :: Markup :: Markdown',
		'Topic :: Text Processing :: Markup :: HTML',
		'Operating System :: OS Independent',
		'Environment :: Console',
		'License :: OSI Approved :: GNU Affero General Public License v3',
	],
)
