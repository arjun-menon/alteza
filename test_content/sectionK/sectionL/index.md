Welcome to Section L

<ol>
{{
for file in dir.files:
    write('<li><a href="%s">%s</a></li>' % 
        (linkObj(file), file.getTitle()))
}}
</ol>
