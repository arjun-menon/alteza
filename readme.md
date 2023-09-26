
# Alteza   [![Type Checks](https://github.com/arjun-menon/appletree/actions/workflows/type-checks.yml/badge.svg)](https://github.com/arjun-menon/appletree/actions/workflows/type-checks.yml/) [![Test Run](https://github.com/arjun-menon/appletree/actions/workflows/test-run.yml/badge.svg)](https://github.com/arjun-menon/appletree/actions/workflows/test-run.yml/)

Alteza is a static site generator driven by [PyPage](https://github.com/arjun-menon/pypage).
Examples of other static site generators can be [found here](https://github.com/collections/static-site-generators).

The differentiator with Alteza is that the site author (if familiar with Python) will have a lot more 
fine-grained control over the output, than what (as far as I'm aware) any of the existing options offer.

The learning curve is also shorter with Alteza. I've tried to follow part of [xmonad](https://xmonad.org/)'s philosophy
of keeping things small and simple. Alteza doesn't try to do a lot of things; instead it simply offers the core crucial
functionality that is common to most static site generators.

Alteza also imposes very little _required_ structure or a particular "way of doing things" on your website. You retain
the freedom of organize your website as you wish. (The name _Alteza_ comes from a word that may be
translated to [illustrious](https://m.interglot.com/en/es/illustriousness) in Español.)

A core design decision of Alteza is executing code (and writing little scripts) to generate your website. (This of
course means that you must run Alteza with trusted code, or in an isolated container.)

## User Guide

1. The directory structure is generally mirrored in the generated site.

2. By default, nothing is copied/published to the generated site.
    * A file must explicitly indicate using a `public: true` variable/field that it is to be published.
      * So directories with no public files, are non-existent in the generated site.
    * Files _reachable_ from marked-as-public files will also be publicly accessible.
      * Here, reachability is discovered when a provided `link` function is used to link to other files.

3. There are two kinds of files that are subject to processing with [PyPage](https://github.com/arjun-menon/pypage): Markdown files (ending with `.md`) and any file with a `.py` before its actual extension.
    * Markdown Files:
        * Markdown files are first processed to have their "front matter" extracted using [Meta-Data](https://python-markdown.github.io/extensions/meta_data/).
          * The first blank line or `---` ends the front matter section.
          * The front matter is processed as YAML, and the fields are injected into the `pypage` environment.
        * ~~The Markdown file is processed using `pypage`, with its Python environment enhanced by the YAML fields from the front matter~~.
        * The environment dictionary after the Markdown is processed by pypage is treated as the "return value" of this `.md` file. ~~This "return value" dictionary has a `content` key added to it which maps to the `pypage` output for this `.md` file~~. 
        * This Markdown file is passed to a **template** specified in configuration, for a second round of processing by PyPage.
          * Templates are HTML files processed by PyPage. The PyPage-processed Markdown HTML output is passed to the template as the variable `body` variable. The template itself is executed by PyPage.
            * The template should use this `body` value via PyPage (with `{{ boydy }}` in order to render the `body`'s contents.
          * (See more on configuration files in the next section.)
          * The template is defined using a `template` variable declared in a `__config__.py` file.
          * The `template`'s value must be the entire contents of a template HTML file. A convenience function `readfile` is provided for this. So you can write `template = readfile('some_template.html')` in a config file.
          * Templates may be overriden in descendant `__config__.py` files, or in the Markdown _**itself**_ using front matter.
        * Markdown files result in **_a directory_**, with an `index.html` file containing the Markdown's output.
    * Other Dynamic Files (_i.e. any file with a `.py` before the last `.` in its file name_):
      * These files are processed with PyPage _once_ with no template application step afterward.
    * Other content files are not read. They are _selectively_ either **symlink**ed or **copied**.

4. Python Environment and Configuration:
   * _Note:_ Python code in both `.md` and other `.py.*` files are run using Python's built-in [`exec`](https://docs.python.org/3/library/functions.html#exec) (and [`eval`](https://docs.python.org/3/library/functions.html#eval)) functions, and when they're run, we passed in a dictionary for their `globals` argument. We call that dict the **environment**, or `env`.
   * Configuration is done through file(s) called `__config__.py`.
     * First, we recursively go through all directories top-down.
     * At each directory (descending downward), we execute an `__config__.py` file, if one is present. After
   execution, we absorb any variables in it that do not start with a `_` into the `env` dict.
       * This behavior cna be used to override values. For example a top-level directory can define a `default_template`, which can then be overriden by inner directories.
   * The deepest `.md`/`.py.*` files get executed first. After it executes, we check if a `env` contains a field `public` that is set as `True`. If it does, we mark that file for publication. Other than recording the value of `public` after each dynamic file is executed, any modification to `env` made by a dynamic file are discarded (and not absorbed, unlike with `__config__.py`).
     * I would recommend not using `__config__.py` to set `public` as `True`, as that would make the entire directory and all its descendants public (unless that behavior is exactly what is desired). Reachability with `link` (described below) is, in my opinion, a better way to make _only reachable_ content public.

5. Name Registry and `link`.
    * The name of every file in the input content is stored in a "name registry" of sorts that's used by `link`.
      * Currently, names, without their file extension, have to be unique across input content. This might change in the future.
      * The Name Registry will error out if it encounters any non-unique names. (I understand this is a significant limitation, so I might support marking this simply opt-in behavior with a `--unique` flag in the future.)
    * Any non-dynamic content file that has been `link`-ed to is marked for publication (i.e. copying or symlinking).
    * A Python function named `link` is injected into the top level `env`.
      * This function can be used to get relative links to any other file. `link` will automatically determine & return the relative path to a file.
        * For example, one can do `<a href="{{link('some-other-blog-post')}}">`, and the generated site will have a relative link to it (i.e. to its directory if a Markdown file, and to the file itself otherwise).
      * Reachability of files is determined using this function, and unreachable files will be treated as non-public (and thus not exist in the generated site).
    * Extensions may be omitted for dynamic files (i.e. `.md` for Markdown, and `.py*` for any file with `.py` before its extension).
      * I.e. one can write both `link('magic-turtle')` or `link('magic-turtle.md')` for the file `magic-turtle.md`, and `link('pygments-styles')` or `link('pygments-styles.py.css')` for the file `pygments-styles.py.css`.

## Testing

To run, execute the `core` module itself, from the project directory:
```sh
python3 -m core -h
```
The `-h` argument above will print the available options:
```
(venv) python3 -m core -h
usage: __main__.py [--copy_assets] [--trailing_slash] [--content_dir CONTENT_DIR] [--output_dir OUTPUT_DIR] [-h]

options:
  --copy_assets         (bool, default=False) Copy assets instead of symlinking to them
  --trailing_slash      (bool, default=False) Include a trailing slash in links to markdown pages
  --content_dir CONTENT_DIR
                        (str, default=test_content) Directory to read the input content from.
  --output_dir OUTPUT_DIR
                        (str, default=test_output) Directory to send the output. WARNING: This will be deleted first.
  -h, --help            show this help message and exit
```
As might be obvious above, you set the `content_dir` to your content directory. The output directory will be deleted entirely, before being written to.

To just run the standard test suite (`test_content`), just run it without any argument (`python3 -m core`).

### Type checking & reformatting
To run some type checks:
```sh
mypy core  # should have zero errors
pyre check  # should have zero errors as well
pyright core  # should have zero errors also
pytype core  # should have zero errors too
```
Or all at once with: `mypy core ; pyre check ; pyright core ; pytype core`.

To re-format the code, just run: `black core`.

### Dependencies

To install dependencies, run:
```sh
python3 -m pip install -r requirements.txt
```

To use a virtual environment (after creating one with `python3 -m venv venv`):
```sh
source venv/bin/activate
python3 -m pip install -r requirements.txt
# ... do some testing ...
deactive # end the venv
```

---

#### License
This project is licensed under the AGPL v3, but I'm reserving the right to re-license it under a license with fewer restrictions, e.g. the Apache License 2.0, and any PRs constitute consent to re-license as such.
