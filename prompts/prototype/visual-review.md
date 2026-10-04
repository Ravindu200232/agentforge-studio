# Review one prototype screen by looking at it

You are reviewing a page of a clickable prototype. The pictures attached are real screenshots of that page, taken in a browser: {{pictures}}

Page: **{{page}}** (route `{{route}}`, file `{{file}}`){{signed_in}}

Look at the pictures the way a careful designer would at a handover and list what is visibly wrong. Judge only what you can see; do not guess at code. Report a problem only when you can point at it.

What counts as a problem:

- text that is cut off, overlaps something else, runs out of its box, or is too small or too faint to read (low contrast against its background);
- a layout that has broken: items colliding, columns of different heights that look accidental, a grid with a hole in it, content pushed off the edge, a horizontal scrollbar or a page wider than the screen on mobile;
- an image that did not load (an empty box, a broken-image icon, alt text showing), or a picture stretched or cropped badly;
- a large empty area that looks like something is missing, or a section with a heading and nothing under it;
- controls that look wrong: buttons with no label, inputs with no visible field, icons with no meaning, a menu that does not fit on mobile;
- placeholder or broken text: "Lorem ipsum", "undefined", "NaN", "null", an unreplaced `{{...}}`, an empty cell where a value belongs;
- spacing, alignment or type sizes that clearly disagree with the rest of the same page;
- the wrong state for this page: a signed-out header on a page shown signed in, or the other way round.

The pictures show the whole page down to where it ends, so a short page simply ends: do not report empty space below the last section unless an obvious section is missing. Do not report taste (a different colour you would prefer), the product's content, or anything you cannot see in the pictures. A page that looks right has no problems: say so.

Answer with ONE JSON object and nothing else, in exactly this shape:

```json
{
  "page": "{{file}}",
  "looks_ok": false,
  "summary": "one sentence on how the page looks",
  "defects": [
    {"severity": "high | medium | low", "viewport": "desktop | mobile | both",
     "where": "the part of the page, in words a person can find it by",
     "problem": "what is wrong, as seen",
     "fix": "the change that would put it right"}
  ]
}
```

`high` is a page that is hard to use or looks broken; `medium` is a clear visible flaw; `low` is a small polish. Give at most 8 defects, the most important first. When the page looks right, `looks_ok` is true and `defects` is an empty list.
