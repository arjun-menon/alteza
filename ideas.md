

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

