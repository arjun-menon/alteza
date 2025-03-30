public = True

# The line below will manually make test_scratch2.txt public.
next(filter(lambda file: file.baseName == 'test_scratch2', dir.files)).makePublic()
