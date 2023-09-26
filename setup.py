from setuptools import setup

version = "0.7.0"

name = "alteza"

repo_url = "https://github.com/arjun-menon/%s" % name
download_url = "%s/archive/v%s.tar.gz" % (repo_url, version)

setup(
    name=name,
    version=version,
    description="Super-flexible Static Site Generator",
    # Ref: https://packaging.python.org/en/latest/discussions/install-requires-vs-requirements/
    install_requires=[
        # Standard dependencies:
        "pypage >= 2.0.8",
        "markdown >= 3.4.4",
        "pygments >= 2.16.1",
        "pyyaml >= 6.0.1",
        "colored >= 2.2.3",
        "sh >= 2.0.6",
        "typed-argument-parser >= 1.8.1",
        # Dev dependencies:
        "black",
        "pip-tools",
        "mypy ~= 1.5.1",
        "pyre-check ~= 0.9.18",
        "pyright ~= 1.1.327",
        "pytype ~= 2023.9.19",
        "types-PyYAML >= 6.0.12.12",
        "types-Markdown >= 3.4.2.10",
    ],
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url=repo_url,
    download_url=download_url,
    author="Arjun G. Menon",
    author_email="contact@arjungmenon.com",
    keywords=["static site generator", "static sites", "ssg"],
    license="AGPL-3.0-or-later",
    # Ref:https://docs.python.org/3.11/distutils/examples.html
    packages=["alteza"],
    entry_points={
        "console_scripts": [f"{name}=alteza.__main__:main"],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: Content Management System",
        "Topic :: Internet :: WWW/HTTP :: Site Management",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Text Processing :: Markup :: Markdown",
        "Topic :: Text Processing :: Markup :: HTML",
        "Operating System :: OS Independent",
        "Environment :: Console",
        "License :: OSI Approved :: GNU Affero General Public License v3",
    ],
)
