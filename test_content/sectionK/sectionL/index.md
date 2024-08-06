title: Section L
---
Welcome to Section L

<ol>
{{
for file in dir.files:
    write('<li><a href="%s">%s</a> <code>%s</code> </li>' % 
        (link(file), file.title,  ' -> ' + file.fullPath))
}}
</ol>

Self-link <a href="{{ link('sectionL') }}">here</a>.
