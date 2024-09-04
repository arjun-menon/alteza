
Flexible Static Site Generator
------------------------------

#### Ideas...
* Top 1:
  * Proper object exposed for each PyPage file.
    * Proper YAML field capture.
    * Maybe inject post-processing fields (gathered with `getModuleVars`) into this object with `setattr`.
  * Document all built-in functions, and config fields (like the `skip` config var), etc.
  * Obsidian style Wiki Links.
  * Update the `YYYY-MM-DD-` handler to allow `YYYY-MM-DD ` as well.
  * A `nameEncode` configurable function, with a `defaultNameEncode`.
    * Convert something like "Purpose of Life" to `purpose-of-life`.
    * This will allow us to use the file name as title, like in Obsidian.
    * Use a regex & validate that what's returned by `nameEncode` is acceptable for a URL.
    * Document this behavior: with Name Registry, this will make the unique names rule non-case-sensitive, at least with `defaultNameEncode` converting all chars to lower case.
  * Rename `subDirs` to `dirs`, etc.?
  * An `after` function defined in __config__.py that gets run after all children are processed.
  * Installing pip requirements.txt for the site being built.
  * Maybe: Expose `content` for user post-processing functions.

**_Completed_**:
- [x] Rebuild automatically with a fs watching library.
- [x] Implement a `skip` config var.
- [x] Document most built-in functions.
- [x] 
- [x] 
- [x] 
- [x] 
- [x] 

---

* Top 2:
  * A `--dev` flag with supports auto-refresh, using an approach similar to: https://github.com/baalimago/wd-41/blob/main/internal/wsinject/delta_streamer.ws.go
  * Also, the `--dev` flag serve the site. E.g. see: https://stackoverflow.com/questions/33028624/run-python-httpserver-in-background-and-continue-script-execution
  * Add a trailing `/` slash for Markdown page dirs since: (a) if a Markdown page is turned into a dir/collection of smaller essays, this would allow that change to happen naturally/seamlessly, and (b) since many web servers including the one used by GH pages add a trailing `/` slash to directories using a 301 Redirect anyways.
  * Caching in the GitHub action. See:
    * https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows
    * https://github.com/actions/setup-python#caching-packages-dependencies
    * https://jcdan3.medium.com/4-ways-to-speed-up-your-github-action-workflows-a0b08067a6c6
  * Enforce directory name uniqueness--currently multiple directories that are all without index pages can share the same name.
  * Rectify `linkName` (if necessary).
  * In addition to the `files`  field, we'll need some other fields.
    * Add `pages` (for Md & HTML), and `pyPages` (for all pypages).
      * Maybe eliminate `Page` node, and merge the `lastUpdated` feature to `FileNode`, since `Page` doesn't really make sense as a parent class of `NonMd`.
    * Enrich `FileNode`, `PyPageNode`, etc., with any other information that might be helpful (e.g. the page's output).
      * Enhance `FileNode` with the page's title? (What about plain HTML pages -- is BeautifulSoup-based title extraction warranted here?)
  * Implement --seed for seeding the initial environment.
  * Obsidian Vault recognition.
  * Auto site gen symlink swap. Have a `site-gen-output` directory. Gen output to a time-stamped directory inside it, e.g. `site-gen-2023-11-15-HH-MM-milliseconds`. Create a `current` symlink inside the `site-gen-output` directory that points to it. If a `current` already exists, make a copy of it called `previous` (overwriting any old `previous`). Then, create `current` (overwriting, if necessary). But, before overwriting an existing `previous`, get the directory it points, and `shutil.rmtree` that directory. Thus, outside use can simply be achieved by pointing to `site-gen-output/output`.
* A `permalink` front matter field, which changes what `FileNode.getLinkName` returns.
* Require full path when there is a name registry name conflict?
* Need to have dev dependencies listed somewhere separately somehow, to avoid pulling needless deps when users install.
* Move support with a root-level `move.json` file and `--move` file. Auto-generating a redirect page, with a built-in redirect HTML template that can be overriden with a user-provided template.
* Add a `dateTimeFormat` option, and add a `lastUpdated` which uses it to transform `lastUpdatedDatetime` into a pretty string.
* (For the far future, for when a site starts taking in the order 5 minutes or more to generate; Strictly An Site Generation Speed Optimization): `__skip_if_no_git_diff__: True` in `__config.py__`: Provided an "old output" reference exists (e.g. a `gh-pages`-like branch on the repo); Skip processing a subdirectory if the `git diff` for that directory between the current commit and the previous commit indicates that nothing has changed, and simply retain the contents of the existing output directory.
* Index Flag: An `index` bool (that is set to `True` by default on pages with a `realBasename` of `index) which causes it to processed after all other files have been processed.
* (For the future) Optional publishing of a non-canonical copy to Medium using Medium’s Publishing API, with the canonical URLs set to point to the canonical host domain.
* Use pip compile, to freeze package versions.
  * Don't forget to add it to dependabot.yml.
* Support for this: https://python-markdown.github.io/extensions/wikilinks/ ?
  * Use `build_url` to talk to `link` to return the correct url?
  * Enhance the NameRegistry with Markdown pages' titles as well, so a WikiLink can refer to a page by its title?
* Maybe run the Markdown processing twice -- first to grab front matter, and inject it into
  the env (discarding the html out); and the second time to actually grab the html.
* Changing Name Registry to allow is to handle multiple files with the same basename. (Low Priority)
  * I'll need some sort of algorithm/approach to handle these.
  * Modify name registry so that if there are names with multiple matches, we just
    print a warning listing the multiple matches for each name, and print a message
    recommending using unique names.
  * A `--unique` flag to mandate unique names.
* Watch option `--watch` that rebuilds automatically.
* Simple built-in HTTP server option `--serve` that serves the output directory.
* Development `--dev` options which turns on both `--watch` and `--serve`.
  * Maybe a WebSocket that tells the listener if a site rebuild is _in progress_.
* Obsidian Vault internal links recognition?
* Fix the `link` circular issue by tracing links after processing, from every `public` node. (low priority?)
* Generating a "Site Structure" Mermaid output, and adding it to the GitHub Action summary, based on page links?
* (Low value) Use some graph visualization library to draw a visual map of the website.
* Limit pypage processing to `.py.html` (and `.md`) files.
  * (In the far future:) Perhaps add pypage processing (plus front matter) support for RST as well. 
* GitHub action to publish a website to `gh-pages`-like branch of the same repo (the branch as configured).
  * Minor: Optional Canonical URL addition, in case the website is being published in multiple places. 
* A function called `after(dirNode)`, if defined in `__config.py__`, gets called after the directory has been 
  completely processed (i.e. including pypage, template application, etc). The final resultant HTML output will
  be available (for page `FileNode`s) from the optional `htmlOutput` field in `FileNode`.
* Should I allow `config.py` if a `__config__.py` is missing?
* Allow name registry to refer to any file without an extension, as long as that file name w/o extension is unique.
  If not, require the extension to be specified.
* (For the future:) add a `post-processing` step which executes `Callable[[FileNode], None]` on every _page_ after its processing has been completed.
* ~~Try https://python-poetry.org/ ?~~
* (For the future): Auto-compression of images to different sizes, and img tags with `srcset` being inserted, if Markdown image syntax (i.e. a link with a `!` in front of it) is used.
* (For the _far_ future): allow referencing an "assets" or "resources" repo (or such folder in a different repo) -- for/if the time comes when you don't want to slow down rebuilds of a website due to there being many heavy static assets in it.
  * Alternatively, the assets could also be in a folder inside Dropbox or Tresorit, but that's publicly served.
    * Alteza needs to be able to recognize this, verify such files exist on the local disk (at some specified location), but also appropriately adjust `link` so that in the generated website, they link to the correct public (possibly-different-domain) URL.
  * Investigate if there's a **free, public** service to host static assets like PDFs, audio, and video, which can be relied upon to fairly quickly served (via CDN?) and have stable long-lived URLs.
* Update GitHub action once https://github.com/orgs/community/discussions/10985 has been implemented.
* Some "extra" flags for extensions/features that are opt-in.
  * For example an `--extra_sitemap_xml` flag which generates a `sitemap.xml` file.
    * https://www.searchenginejournal.com/technical-seo/xml-sitemaps/
* To look into for a GitHub Pages action:
  * https://github.com/actions/upload-pages-artifact
  * https://github.com/actions/deploy-pages
  * https://github.com/actions/configure-pages
  * Documentation:
    * https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
* Stricken from readme:
  * ~~The Markdown file is processed using `pypage`, with its Python environment enhanced by the YAML fields from the front matter~~.
  * The environment dictionary after the Markdown is processed by pypage is treated as the "return value" of this `.md` file. ~~This "return value" dictionary has a `content` key added to it which maps to the `pypage` output for this `.md` file~~.
* In the GitHub action: an option to pip install a `requirements.txt` file. (It'd just do `touch requirements.txt; pip install requirements.txt`.) Or maybe not an option, but always-on behavior.
* Archiving URLs.
  * See: https://gwern.net/archiving
  * Perhaps with https://github.com/oduwsdl/archivenow

Older Ideas 2
=============
### General Ideas & Goals (WIP)

(Note: this is written in the spirit of [Readme Driven Development](http://tom.preston-werner.com/2010/08/23/readme-driven-development.html).)

### Basic Operation

1. First, we recursively go through all directories.
2. At each directory (descending downward), we execute an `__config__.py` file, if one is present. After
   execution, we absorb any variables in it that do not start with a `_` into an `env` dict.
3. Process all `.md` files and any file with a `.py` before its actual extension with `pypage`. Pass the `env` dict to Pypage.
   1. Pypage is called on the "leaf nodes" (innermost files) first, and then upwards.
   2. Thus, the `.md` and `.html` files in the parent directory receives a list of objects representing the processed results of all its subdirectories. (And, this is repeated, recursively upwards).
4. Resultant HTML output is copied to the output directory (and non-HTML output symlinked there).

#### Key Ideas:

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
      * HTML files ending with the extension `.pypage.html` are directly processed by `pypage`.
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


Older Ideas 1
=============

Key Ideas
---------

* Follow React-like principles of:
 - Child doesn't know anything about parent
 - Top-down data flow

* Simple _importable_ `.py` files that are used instead of YAML or JSON configs.
  - Maybe, let even the front matter be executable Python code.

* By default, no file is public.
  - Files need to have a `publish` property or something to be copied over.
  - But we'll need some way of saying everything in this directory and its descendants should all be copied.
  - We'll also need some reachability algorithm -- to figure out which files should be copied.
    + Maybe just search a file for string paths? But that wouldn't work for children / files in subdirectories.

* pypage everywhere?
  - Or maybe paypage is _only activated -- when a `.py` appears before the actual extension?_

Blogging Structure
------------------

- Use LOTS of categories (folders / sub-sections) while blogging!


Older Ideas 0
=============

Posts Processing
----------------
Everything under /posts, like:
	/tech/aaa.md
	/life/bbb.md
	/world/cccc.md

...all get merged together to a single root ("www.arjungmenon.com/articles/"):
	/articles/aaa.md
	/articles/bbb.md
	/articles/ccc.md

So all posts must have _unique_ permalinks/names.


File Processing
---------------

With most files, pypage-site looks for the YAML front-matter delimiter ("---") in all files, 
extracts the YAML varibales, and uses them in order to decide whether and how to handle it.

Markdown files are treated differently however. Any file ending with the extension ``.md`` or 
``.markdown`` (case-insensitive), is run through Python Markdown first, and the 
[Meta-Data](https://pythonhosted.org/Markdown/extensions/meta_data.html) (if any) obtained from 
it passed through PyYAML, and the variables obtained hence are used to decide if further 
processing is necessary.

This is useful since most simple pages (such as blog posts) will simply consist of content, and 
will not make use of pypage preprocessing.



assert that metadata.date is of the Python date type
    if not raise an error that it's not in the right date format (yyyy-mm-dd)



pypage-site

- you're doing: txt -- (docutils.rST) --> html_body -- (pypage) --> html_page

- Custom h1/h2/h3/etc level rST extension

- password protection (with nodejs & SJCL)

- Related Posts rST extension

- you don't need escape write(...) calls because docutils or python-markdown will take care of it. (?)

