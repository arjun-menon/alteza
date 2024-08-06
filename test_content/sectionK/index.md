title: Just Section K
---

<p>
The directories here are:
<ol>
{% for d in dir.subDirs %}
{% if d.title %}
<li>
<a href="{{link(d)}}">{{d.title}}</a>
</li>
{% endif %}
{% endfor %}
</ol>
</p>

<a href="..">Root/home</a>.
