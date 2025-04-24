title: {{ "Joyful " + "Squirrel" }}
x1y: :-)
---

Here's a joyful squirrel.

<img src="{{link("squirrel")}}">

{{ markdown("""Now, _it looks quite **cheerful**_, doesn't it?""") }}

Want to learn about a [magic turtle]({{link("magic-turtle")}})?

What about a [[curious-cat]]? <small>(Or a [[baby-squirrel]] or a [[baby-chipmunk]]?)</small>

This is [what a "megabyte" is]({{link("just_a_test")}}).

<style>li { margin-top: 0.5em; }</style>

A few data points:
  * This page was created (or renamed) on {{getCreateDate("%B %-d, %Y")}}.
      * We got this from git history.
  * But we got the idea for this on {{getIdeaDate("%B %-d, %Y")}}.
      * We got this from the file name prefix of this file.
      * And it's great we can track both dates.
  * This page was last modified on {{getLastModified()}}.
    - We got this from git history as well.
        - But note that spawning a git process could be slow.

Slug tests:
* This is [[slug-test-1]].
    * This is also the same [[Slug Test 1]].

Back to the [parent](..) level.
