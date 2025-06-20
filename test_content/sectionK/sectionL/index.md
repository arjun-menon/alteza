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

Lizard vars:<code>
* Lizard attribute x1 from env: {{ file('lizard').env['x1'] }}
* Lizard attribute x1 injected: {{ file('lizard').x1 }}
* Lizard attribute x2 from env: {{ file('lizard').env['x2'] }}
* Lizard attribute x2 injected: {{ file('lizard').x2 }}
</code>

Self-link <a href="{{ link('sectionL') }}">here</a>.
