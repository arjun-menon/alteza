
appletree will be a static site generator driven by [pypage](https://github.com/arjun-menon/pypage).
Examples of other static site generator include [Jekyll](https://jekyllrb.com/), [Hugo](https://gohugo.io/), [Gutenberg](https://www.getgutenberg.io/), etc.

The differentiator with appletree is that the site author (expected to be fluent in Python) will have a lot more fine-grained control over the output, than what any of the existing options offer.

## Testing

To run, execute the `core` module itself, from the project directory:
```sh
python3 -m core
```

### Type checking & reformatting
To run some type checks:
```sh
mypy core  # should have zero errors
pyre check  # should have zero errors as well
pyright core  # should have zero errors also
pytype core  # should have zero errors too
```
Or all at once with:
```sh
mypy core ; pyre check ; pyright core ; pytype core
````

To re-format the code, just run: `black core`.

### Depedencies

To install dependencies, run:
```sh
brew install watchman # on macOS
python3 -m pip install -r requirements.txt
```

To use a virtual environment (after creating one with `python3 -m venv venv`):
```sh
source venv/bin/activate
python3 -m pip install -r requirements.txt
# ... do some testing ...
deactive # end the venv
```

### General Ideas & Goals (WIP)

(Note: this is written in the spirit of [Readme Driven Development](http://tom.preston-werner.com/2010/08/23/readme-driven-development.html).)

#### Key Ideas:

1. Recursively go through all directories.
2. At each directory (descending downward), import an `__config__.py` file, if one is present, and absorb its variables into an `env` dict.
3. Process all `.md` and `.html` files with `pypage`. Pass the `env` dict to Pypage.
   1. Pypage is called on the "leaf nodes" (innermost files) first, and then upwards.
   2. Thus, the `.md` and `.html` files in the parent directory receives a list of objects representing the processed results of all its subdirectories. (And, this is repeated, recursively upwards).
4. Resultant HTML output is copied to the output directory (and non-HTML output symlinked there).
