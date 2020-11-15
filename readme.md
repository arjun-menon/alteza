
Mandrake is / will be a static site generator in the spirit of [Jekyll](https://jekyllrb.com/), [Hugo](https://gohugo.io/), [Gutenberg](https://www.getgutenberg.io/), etc. I'm building this because I want to offer the site author a lot more fine-grained control over the output, than what any of the existing options offer.

Overview
--------

In the spirit of [Readme Driven Development](http://tom.preston-werner.com/2010/08/23/readme-driven-development.html), this readme provides an overview and lays out the structure of this project.

*General Ideas & Goals*

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
		* Markdown
		* HTML
	* Python source files (ending in `.py3` or `.py`). You are expected to export certain specifically named functions from your module. This will be covered in detail later.If these functions are not present, Mandrake will ignore your module until it is altered. Mandrake won't spwan a new Python processes to execute your modules, but will directly import them (using `importlib`) in the main Mandrake process. The onus is on you, the user, to make sure that your Python modules are _safe and fast_. Mandrake will catch all exceptions (and log them), but nothing prevents you from calling `sys.exit(1)` (and killing the server). If your module causes Python to crash, the whole server will go down. Furthermore, it is your responsibility to ensure that your module does everything very quickly, since you do not want to hog the Mandrake process. The server runs in a different thread from the one running your code, _however_, as Python isn't truly multi-threaded due to the GIL, doing heavy work will likely cause drastic drops in the server's response times. The general principle is: keep these Python modules light and simple.
	* A Python function named `link` will be made available to the kinds of content above. This function will be used to link to other files within the content space. Reachability of files is determined using this function, and unreachable files will be treated as non-public (as described in point 1).

*How the site is updated*

There will be a symlink named `site` that will point to a folder containing the actual output.

During the initial launch, and then upon every change that is detected (e.g. [via watchdog](https://github.com/gorakhargosh/watchdog)), mandrake (in early versions) will re-process everything, and output the result to a folder named `site-built-at-YYYY-MM-DD-HH-MM-SS-MS-timezone`. It will overwrite the symlink `site` with it pointing to this folder. If there is an older `site-built-...` folder, then mandrake will run `rm -rf` on it (by default, but can be turned off by the user with a flag - for debugging, for example).
