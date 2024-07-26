Welcome to Section L

<ol>
{{
for file in dir.files:
    write('<li><a href="%s">%s</a> <code>%s</code> </li>' % 
        (linkObj(file), file.getTitle(),  ' -> ' + file.fullPath))
}}
</ol>

Self-link <a href="{{ link('sectionL') }}">here</a>.
