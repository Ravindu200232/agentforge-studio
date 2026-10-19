# Review one page of the application

You are reviewing the real, running application. The pictures attached are of one whole page, from the top to the bottom, opened {{who}} by an automated browser: {{pictures}}

Page: **{{page}}**{{status}}

The page is real, not a mockup: it shows the data the application holds now, so an empty list is not a defect when nothing has been added. Look at it the way a careful designer or tester would and list what is visibly wrong. Judge only what you can see; do not guess at code. Report a problem only when you can point at it.

What counts as a problem:

- an error shown to the person: "Application error", "Internal Server Error", a stack trace, raw JSON, a red error box nobody asked for, "404 / not found", an endless spinner or skeleton;
- text that is cut off, overlaps something else, runs out of its box, or is too small or too faint to read;
- a layout that has broken: items colliding, content pushed off the edge, a table or row wider than the screen on mobile, a menu that does not fit, controls hidden behind other things;
- a page with no styling at all (a bare browser-default page), or a stylesheet that clearly did not load;
- an image that did not load (an empty box, a broken-image icon, alt text showing);
- placeholder or broken text: "Lorem ipsum", "undefined", "NaN", "null", an unreplaced `{{...}}`, an empty cell where a value belongs;
- controls that look wrong: buttons with no label, inputs with no visible field, icons with no meaning;
- the wrong state: a signed-out page where it was opened signed in, a sign-in page where the page itself was wanted, or the other way round.

Do not report taste (a different colour you would prefer), the product's content, or anything you cannot see in the pictures. A page that looks right has no problems: say so.

Answer with ONE JSON object and nothing else, in exactly this shape:

```json
{
  "page": "{{page}}",
  "looks_ok": false,
  "summary": "one sentence on what the page shows and how it looks",
  "defects": [
    {"severity": "high | medium | low", "viewport": "desktop | mobile | both",
     "where": "the part of the page, in words a person can find it by",
     "problem": "what is wrong, as seen",
     "fix": "the change that would put it right"}
  ]
}
```

`high` is a page that is broken or unusable; `medium` is a clear visible flaw; `low` is a small polish. Give at most 8 defects, the most important first. When the page looks right, `looks_ok` is true and `defects` is an empty list.
