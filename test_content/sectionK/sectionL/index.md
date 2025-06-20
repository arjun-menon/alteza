title: Section L
---
Welcome to Section L

<ol>
{{
for f in dir.files:
    write('<li><a href="%s">%s</a> <code>%s</code> </li>' % 
        (link(f), f.title,  ' -> ' + f.fullPath))
}}
</ol>

Lizard attribute x1: {{ file('lizard').env['x1'] }}

Lizard attribute x2: {{ file('lizard').env['x2'] }}

Self-link <a href="{{ link('sectionL') }}">here</a>.
