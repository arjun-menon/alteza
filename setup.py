from setuptools import setup

version = "0.7.0"

name = "alteza"

repo_url = "https://github.com/arjun-menon/%s" % name
download_url = "%s/archive/v%s.tar.gz" % (repo_url, version)

setup(
    name=name,
    version=version,
    description="Super-flexible Static Site Generator",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url=repo_url,
    download_url=download_url,
    author="Arjun G. Menon",
    author_email="contact@arjungmenon.com",
    keywords=["static site generator", "static sites", "ssg"],
    license="AGPL-3.0-or-later",
    package_dir={"alteza": "core"},
    packages=["alteza"],
    entry_points={
        "console_scripts": [f"{name}=core.__main__:main"],
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
