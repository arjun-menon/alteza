
Mandrake is a blogging framework in the spirit of [Jekyll](https://jekyllrb.com/), [Hugo](https://gohugo.io/), [Gutenberg](https://www.getgutenberg.io/), etc. I'm building this because I want far more control that what any of the existing options offer.

Overview
--------

In the spirit of [Readme Driven Development](http://tom.preston-werner.com/2010/08/23/readme-driven-development.html), this readme provides an overview and lays out the structure of this project.

*General Ideas*

Below, the word "public" refers to generated public-facing website.

 1. The directory structure is generally mirrored in the public site.

 2. By default, nothing is public.
 	* A file must explicitly indicate (in some way) that it is to be public.
 	* Files reachable from marked-as-public files will also be publicly accessible.
 	* Reachability is discovered when specific constructs are used to reference other files.
 	* (Duh: Directories with no public files, are non-existent in the public site.)

3. Mandrake maintains a dependency graph for all of the files.
	* It does a full initial recursive scan of the directory you start it in, and then starts up `watchdog` (a filesystem watcher) to monitor for changes.
	* Each file being a node in the graph, when file A depends on file B, there is a directed edge going in reverse, from file B to file A. Cyclical dependencies are okay.
	* When a file is changed, it is re-executed if it is "exectuable" (as described below), and every file that depends on it is re-executed.

4. There are two kinds of files that are significant to Mandrake: `pypage` content files and Python modules. Both types of files are treated as Python "executables".
	* Content files are executed by the `pypage` templating engine. In order to determine if a file is an _executable_ `pypage` file, Mandrake runs a set of simple test functions against every file. You can add additional functions to this set. By default, two kinds of files are recognized:
		* Markdown files containing front matter.
		* HTML
	* Python source files (ending in `.py3` or `.py`). You are expected to export certain specifically named functions from your module. This will be covered in detail later.If these functions are not present, Mandrake will ignore your module until it is altered. Mandrake won't spwan a new Python processes to execute your modules, but will directly import them (using `importlib`) in the main Mandrake process. The onus is on you, the user, to make sure that your Python modules are _safe and fast_. Mandrake will catch all exceptions (and log them), but nothing prevents you from calling `sys.exit(1)` (and killing the server). If your module causes Python to crash, the whole server will go down. Furthermore, it is your responsibility to ensure that your module does everything very quickly, since you do not want to hog the Mandrake process. The server runs in a different thread from the one running your code, _however_, as Python isn't truly multi-threaded due to the GIL, doing heavy work will likely cause drastic drops in the server's response times. The general principle is: keep these Python modules light and simple.

