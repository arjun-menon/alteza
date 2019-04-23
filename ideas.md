
Flexible Static Site Generator
==============================

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


Older Ideas
===========

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

