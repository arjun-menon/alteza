# Alteza [![PyPI](https://img.shields.io/pypi/v/alteza.svg)](https://pypi.org/project/alteza/) [![Type Checks](https://github.com/arjun-menon/appletree/actions/workflows/type-checks.yml/badge.svg)](https://github.com/arjun-menon/appletree/actions/workflows/type-checks.yml/) [![Test Run](https://github.com/arjun-menon/appletree/actions/workflows/test-run.yml/badge.svg)](https://github.com/arjun-menon/appletree/actions/workflows/test-run.yml/)

Alteza is a static site generator<sup>[<img height="10" width="10" src="https://upload.wikimedia.org/wikipedia/en/thumb/8/80/Wikipedia-logo-v2.svg/103px-Wikipedia-logo-v2.svg.png" />](https://en.wikipedia.org/wiki/Static_site_generator)</sup> driven by [PyPage](https://github.com/arjun-menon/pypage).
Examples of other static site generators can be [found here](https://github.com/collections/static-site-generators).

The differentiator with Alteza is that the site author (if familiar with Python) will have a lot more 
fine-grained control over the output, than what (as far as I'm aware) any of the existing options offer.

The learning curve is also shorter with Alteza. I've tried to follow part of [xmonad](https://xmonad.org/)'s philosophy
of keeping things small and simple. Alteza doesn't try to do a lot of things; instead it simply offers the core crucial
functionality that is common to most static site generators.

Alteza also imposes very little _required_ structure or a particular "way of doing things" on your website (other than
requiring unique names). You retain the freedom to organize your website as you wish. (The name _Alteza_ comes from
a word that may be translated to [illustriousness](https://m.interglot.com/en/es/illustriousness) in Español.)

A key design aspect of Alteza is writing little scripts and executing such code to generate your website. Your static
site can contain arbitrary Python that is executed at the time of site generation. [PyPage](https://github.com/arjun-menon/pypage),
in particular, makes it seamless to include actual Python code inside page templates. (This of
course means that you must run Alteza with trusted code, or in an isolated container.)

#### Installation

You can [install](https://docs.python.org/3/installing/) Alteza easily with [pip](https://pip.pypa.io/en/stable/):

```
pip install alteza
```
Try running `alteza -h` to see the command-line options available.

## User Guide

1. The directory structure is generally mirrored in the generated site.

2. By default, nothing is copied/published to the generated site.
    * A file must explicitly indicate using a `public: true` variable/field that it is to be published.
      * Therefore, directories with no public files do not exist in the generated site.
    * Files _reachable_ from marked-as-public files will also be publicly accessible.
      * Here, reachability is discovered when a provided `link` function is used to link to other files.

3. All file and directory names, except for index page files, _at all depth levels_ must be unique. This is to simplify use of the `link(name)` function. With unique file and directory names, one can simply link to a file or directory with just its name, without needing to disambiguate a non-unique name with its path. Note: Directories can only be linked to if the directory contains an index page.

4. There are two kinds of files: **static asset** files, and **PyPage** (i.e. dynamic *template/layout* or *content*) files. PyPage files get processed by the [PyPage](https://github.com/arjun-menon/pypage) template engine.

5. **Static asset** files are **_not_** read by Alteza. They are _selectively_ either **symlink**ed or **copied** to the output directory (you can choose which, with a command-line argument). Here, _selectively_ means that they are exposed in the output directory _only if they are linked to_ from a PyPage file using a special Alteza-provided `link(name)` function.

6. PyPage files are determined based on their file name extension. They are of two kinds:
   1. **Markdown** files (i.e. files ending with `.md`).
   2. Any file with a `.py` before its actual extension (_i.e. any file with a `.py` before the last `.` in its file name_). These are **Non-Markdown Pypage files**.

7. There is an inherited "environment"/`env` (this is just a collection of Python variables) that is injected into the lexical scope of every PyPage file, before it is processed/executed by PyPage. This `env` is a little different for each PyPage invocation--a copy of the inherited is `env` is created for each PyPage file. More on `env` in a later point below.

8. **Non-Markdown Pypage files** are simply processed with PyPage as-is (and there is no template application step for non-Markdown PyPage files). The `.py` part is removed from their name, and the output/result is copied to the generated site.

9. **Markdown** files:
    1. Markdown files are first processed with PyPage, with a copy of the inherited `env`.

    2. After this, the Markdown file is converted to HTML using the [Python-Markdown](https://python-markdown.github.io/reference/) library.

    3. Third, they have their "front matter" (if any) extracted using the Python-Markdown's library [Meta-Data](https://python-markdown.github.io/extensions/meta_data/) extension/feature.
       1. The first line with a `---` in the Markdown file ends the front matter section.
       2. The front matter is processed by Alteza as YAML using the [PyYAML](https://pyyaml.org/wiki/PyYAML).

    4. The fields from the YAML front matter the fields are injected into the `env`/environment.

    5. The HTML is injected into a `content` variable in `env`, and this `env` is passed to a `layout` **template** specified _in configuration_, for a second round of processing by PyPage. (Note: PyPage here is invoked on the template.)

       1. Templates are HTML files processed by PyPage. The PyPage-processed Markdown HTML output is passed to the template/layout as the `content` variable. The template itself is then executed by PyPage.

       2. The template/layout should use this `content` value via PyPage (with `{{ content }}`) in order to inject the `content` into itself.

       3. The template is specified using a `layout` or `layoutRaw` variable declared in a `__config__.py` file. (More on configuration files in a later point below.)

       4. A `layout` variable's value must be the name of a template.

          1. For example, you can write `layout: ordinary-page` in the YAML front matter of a Markdown file.

          2. Or, alternatively, you can also write `layout = "ordinary_page"` in a `__config__.py` file. If a `layout` variable is defined like this in a `__config__.py` all adjacent and descendant files will inherit this `layout` value.

             1. This can be used as a way of defining a _**default**_ layout/template.

             2. Of course, the default can be overridden in a Markdown file by specifying a layout name in the YAML front matter, or with a new default in a descendant `__config__.py`.

          3. Lastly, alternatively, a `layoutRaw` can also be defined whose value must be the entire contents of a template PyPage-HTML file. A convenience function `readfile` is provided for this. For example, you can write something like `layout = readfile('some_layout.html')` in a config file. A `layoutRaw`, if specified, takes precedence over `layout`. Using this `layoutRaw` approach is not recommended.

       5. Layouts/templates may be overridden in descendant `__config__.py` files. Or, may be overridden in the Markdown file _**itself**_ using YAML front matter (by specifying a `layout: ...`), or even in a PyPage multiline code tag (not an inline code tag) inside a PyPage file (with a `layout = ...`).

   6. Markdown files result in **_a directory_** with the base name (_i.e. without the `.md` extension_), with an `index.html` file containing the Markdown's output.

10. The **Environment** (`env`) and **Configuration** (`__config__.py`, etc.):

    1. _Note:_ Python code in both `.md` and other `.py.*` files are run using Python's built-in [`exec`](https://docs.python.org/3/library/functions.html#exec) (and [`eval`](https://docs.python.org/3/library/functions.html#eval)) functions, and when they're run, we passed in a dictionary for their `globals` argument. We call that dict the **environment**, or `env`.

    2. Configuration is done through file(s) called `__config__.py`.

       1. First, we recursively go through all directories top-down.

       2. At each directory (descending downward), we execute an `__config__.py` file, if one is present. After execution, we absorb any variables in it that do not start with a `_` into the `env` dict.

    3. The deepest `.md`/`.py.*` files get executed first. After it executes, we check if a `env` contains a field `public` that is set as `True`. If it does, we mark that file for publication. Other than recording the value of `public` after each dynamic file is executed, any modification to `env` made by a dynamic file are discarded (and not absorbed, unlike with `__config__.py`).
       * I would not recommend using `__config__.py` to set `public` as `True`, as that would make the entire directory and all its descendants public (unless that behavior is exactly what is desired). Reachability with `link` (described below) is, in my opinion, a better way to make _only reachable_ content publicly exposed.

11. The **Name Registry** and the **`link`** function.

    1. The name of every file in the input content is stored in a "name registry" of sorts that's used by `link`.

       1. Currently, names, without their file extension, have to be unique across input content. This might change in the future.

       2. The Name Registry will error out if it encounters any non-unique names. (I understand this is a significant limitation, so I _might_ support making this opt-out behavior with a `--nonunique` flag in the future.)

    2. Any non-dynamic content file that has been `link`-ed to is marked for publication (i.e. copying or symlinking).

    3. A Python function named `link` is injected into the top level `env`.

       1. This function can be used to get relative links to any other file. `link` will automatically determine and return the relative path to a file.
          * For example, one can do `<a href="{{link('some-other-blog-post')}}">`, and the generated site will have a relative link to it (i.e. to its directory if a Markdown file, and to the file itself otherwise).

       2. Reachability of files is determined using this function, and unreachable files will be treated as non-public (and thus not exist in the generated site).

    4. A file name's extension must be omitted while using `link` (including the `.py*` for any file with `.py` before its extension).
       * i.e., e.g. one must write `link('magic-turtle')` for the file `magic-turtle.md`, and `link('pygments-styles')` for the file `pygments-styles.py.css`.
       * Directories containing index files should just be referred to by the directory name. For example, the index page `about-me/hobbies/index.md` (or `about-me/hobbies/index.py.html`) should just be linked to with a `link('hobbies')`.

### Usage, Testing & Development

#### Running

If you've installed Alteza with pip, you can just run `alteza`, e.g.:
```sh
alteza -h
```
If you're working on Alteza itself, then run the `alteza` module itself, from the project directory directly, e.g. `python3 -m alteza -h`.

#### Command-line Arguments
The `-h` argument above will print the list of available arguments:
```
usage: __main__.py --content CONTENT --output OUTPUT [--clear_output_dir] [--copy_assets] [--seed SEED] [-h]

options:
  --content CONTENT   (str, required) Directory to read the input content from.
  --output OUTPUT     (str, required) Directory to send the output to. WARNING: This will be deleted.
  --clear_output_dir  (bool, default=False) Delete the output directory, if it already exists.
  --copy_assets       (bool, default=False) Copy static assets instead of symlinking to them.
  --seed SEED         (str, default={}) Seed JSON data to add to the initial root env.
  -h, --help          show this help message and exit
```
As might be obvious above, you set the `content` to your content directory. The output directory will be deleted entirely, before being written to.

To test against `test_content` (and generate output to `test_output`), run it like this:
```sh
python -m alteza --content test_content --output test_output --clear_output_dir
```

#### Code Style

I'm using `black`. To re-format the code, just run: `black alteza`.
Fwiw, I've configured my IDE (_PyCharm_) to always auto-format with `black`.

### Type Checking

To ensure better code quality, Alteza is type-checked with five different type checking systems: [Mypy](https://mypy-lang.org/), Meta's [Pyre](https://pyre-check.org/), Microsoft's [Pyright](https://github.com/microsoft/pyright), Google's [Pytype](https://github.com/google/pytype), and [Pyflakes](https://pypi.org/project/pyflakes/); as well as linted with [Pylint](https://pylint.pycqa.org/en/latest/index.html).

To run some type checks:
```sh
mypy alteza  # should have zero errors
pyflakes alteza  # should have zero errors
pyre check  # should have zero errors as well
pyright alteza  # should have zero errors also
pytype alteza  # should have zero errors too
```
Or, all at once with: `mypy alteza ; pyflakes alteza ; pyre check ; pyright alteza ; pytype alteza`. Pytype is pretty slow, so feel free to omit it.

#### Linting
Linting policy is very strict. [Pylint](https://pylint.pycqa.org/en/latest/index.html) must issue a perfect 10/10 score, otherwise the Pylint CI check will fail.  On a side note, you can see **a UML diagram** of the Alteza code if you click on any one of the completed workflow runs for the [Pylint CI check](https://github.com/arjun-menon/alteza/actions/workflows/pylint.yml).

To test whether lints are passing, simply run:
```
pylint -j 0 alteza
```
To run it along with all the type checks (excluding `pytype`), just run: `mypy alteza ; pyre check ; pyright alteza ; pyflakes alteza ; pylint -j 0 alteza`. I run this often.

Of course, when it makes sense, lints should be suppressed next to the relevant line, in code. Also, unlike typical Python code, the naming convention generally-followed in this codebase is `camelCase`. Pylint checks for names have mostly been disabled.

### Dependencies

To install dependencies for development, run:
```sh
python3 -m pip install -r requirements.txt
python3 -m pip install -r requirements-dev.txt
```

To use a virtual environment (after creating one with `python3 -m venv venv`):
```sh
source venv/bin/activate
# ... install requirements ...
# ... do some development ...
deactive # end the venv
```

---

#### License
This project is licensed under the AGPL v3, but I'm reserving the right to re-license it under a license with fewer restrictions, e.g. the Apache License 2.0, and any PRs constitute consent to re-license as such.
