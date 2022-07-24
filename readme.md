
appletree will be a static site generator driven by [pypage](https://github.com/arjun-menon/pypage).
Examples of other static site generator include [Jekyll](https://jekyllrb.com/), [Hugo](https://gohugo.io/), [Gutenberg](https://www.getgutenberg.io/), etc.
The differentiator with appletree is that the site author (expected to be fluent in Python) will have a lot more fine-grained control over the output, than what any of the existing options offer.

(Note: this is written in the spirit of [Readme Driven Development](http://tom.preston-werner.com/2010/08/23/readme-driven-development.html).)

## General Ideas & Goals (WIP)

1. The directory structure is generally mirrored in the generated site.

2. By default, nothing is copied/published to the generated site.
    * A file must explicitly indicate using a `public: true` variable/field that it is to be published.
      * So directories with no public files, are non-existent in the generated site.
    * Files _reachable_ from marked-as-public files will also be publicly accessible.
      * Here, reachability is discovered when a provided `link` function is used to link to other files.

3. There are two kinds of files that are subject to processing: dynamic `pypage` content files and Python modules.
    * Dynamic content files:
      * By default, there are two kinds of dynamic content files: Markdown (`.md`) and HTML (`.htm` and `.html`).
      * Additional dynamic content file types can be specified through configuration.
        * Functions to help process them can also be provided in configuration.
      * HTML files are directly processed through `pypage`.
      * Markdown files:
        * Markdown files are first processed to have their "front matter" extracted using [Meta-Data](https://python-markdown.github.io/extensions/meta_data/).
          * The first blank line or `---` ends the front matter section.
          * The front matter is processed as YAML, and the fields are injected into the `pypage` environment.
        * The Markdown file is processed using `pypage`, with its Python environment enhanced by the YAML fields from the front matter.
        * The environment dictionary after the Markdown is processed by pypage is treated as the "return value" of this `.md` file. This "return value" dictionary has a `content` key added to it which maps to the `pypage` output for this `.md` file. 
        * This Markdown file is passed to the HTML `pypage` template specified in configuration, for further processing.
    * Python modules (files ending in `.py3` or `.py`, or directories with `__init__.py`):
      * They are imported directly with `importlib`.
      * You are expected to provide a `generate` function (exposed in `__all__`).
        * Python module files are expected to return a `FileContent` object.
        * Python module directories are expected to return a `DirContent` object.
      * You have to make sure that your modules are safe and fast.
        * We catch all exceptions (and log them), but nothing prevents the module from having an infinite loop or calling `sys.exit(1)`.
          * An exception should result in the module being skipped over (and no content generated for it).
    * Python Environment:
      * Certain variables, including additional ones specified via configuration, are passed into the environment for all dynamic content during processing by pypage. (For example, the `link` function.)

4. Other non-dynamic content files are not read. They are _selectively_ **copied**.
    * A Python function named `link` will be made available to link to all kinds of content.
      * This function should _always_ be used to link to other files.
        * In `pypage`, one can do `<a href="{{link('foo/bar')}}">`, for example.
      * Reachability of files is determined using this function, and unreachable files will be treated as non-public (as described in point 1).
    * Any non-dynamic content file that has been `link`-ed to is marked for publication (i.e. copying).
5. Name registry for `link`.
    * All files and directories are stored in a name registry (together).
    * If a unique name, anything can be linked to with `link` with just its name. So `link('foobar')` will work, and `link` will automatically determine & return the relative path to `foobar`.
      * Extensions can be omitted for files, if the file name without extension is unique.

## Future Feature Goals
* Config file instead of command-line params.
* Symlink swapping
  * Have the option to provide the name of a symlink name that will be updated to point to the directory containing the actual output.
  * When run against a content directory named `foo`, output the generated site to a new directory named `foo-gen-YYYY-MM-DD-HH-MM-SS-MS-timezone`.
  * Overwrite the symlink, and have it point to this directory.
  * Auto-deletion of older generated sites. Configurable options:
    * Auto delete when space is below a specified threshold.
      * Auto delete _**proximate**_ version.
      * Calculate time diffs between versions (newer minus older).
      * Pick the one with the lowest time diff for deletion.
    * Auto delete old versions always:
      * If there is an older `foo-gen-...` directory, then run `rm -rf` on it.
      * Basically delete all old versions.
* Unique names.
    * Files and directories everywhere (anywhere, at any depth) must have **unique names**.
      * This rule even applies to non-dynamic content that is never linked to (and never copied).
      * File _extensions are ignored_ in the application of this rule, so `a.md` and `a.py` clashes.
      * If a name clash is detected, we will error out and exit doing zero work.
* Automatic rebuilds with watchdog.
  * Use `watchdog` (a filesystem watcher) to monitor for changes.
  * Maintains a dependency graph for all the files.
  * Each file being a node in the graph, when file A depends on file B, there is a directed edge going in reverse, from file B to file A. Cyclical dependencies are okay.
     * When a file is changed, it is re-executed if it is "exectuable", and re-execute every file that depends on it.
* Parallel builds
* Build time-out after X seconds.
* Site served by a simple web server.
  * Maybe an asynchronous web framework using uvicorn and starlett.
    * Maybe make the whole site live-serveable with this server. 
  * Additional dev mode features: 
    * Error details provided as an overlay injected into the page.
    * Socket-based rebuild watch. Re-build in-progress indicator overlay.
      * Injected script listens for rebuild notification from server & reloads page.
