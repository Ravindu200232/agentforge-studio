# Review a screenshot from an end-to-end test

You are reviewing the real, running application. The pictures attached are screenshots taken by an automated browser at the moment an end-to-end test ended: {{pictures}}

Test: **{{test}}** (`{{spec}}`){{status}}

The screen is real, not a mockup: it shows whatever data the test had created, so an empty list right after a test that created nothing is not a defect. Look at it the way a careful designer or tester would and list what is visibly wrong. Judge only what you can see; do not guess at code. Report a problem only when you can point at it.

What counts as a problem:

- an error shown to the person: "Application error", "Internal Server Error", a stack trace, raw JSON, a red error box nobody asked for, "404 / not found" on a page the journey was meant to reach, an endless spinner or skeleton;
- text that is cut off, overlaps something else, runs out of its box, or is too small or too faint to read;
- a layout that has broken: items colliding, content pushed off the edge, a horizontal scrollbar or a page wider than the screen on mobile, a menu that does not fit, controls hidden behind other things;
- a page with no styling at all (a bare browser-default page), or a stylesheet that clearly did not load;
- an image that did not load (an empty box, a broken-image icon, alt text showing);
- placeholder or broken text: "Lorem ipsum", "undefined", "NaN", "null", an unreplaced `{{...}}`, an empty cell where a value belongs;
- controls that look wrong: buttons with no label, inputs with no visible field, icons with no meaning;
- the wrong state for the journey: a signed-out screen where the test had signed in, or the other way round.

The screenshot is the viewport at the end of the test, so a page that goes on below the fold is not a defect. Do not report taste (a different colour you would prefer), the product's content, or anything you cannot see in the pictures. A screen that looks right has no problems: say so.

Answer with ONE JSON object and nothing else, in exactly this shape:

```json
{
  "page": "{{test}}",
  "looks_ok": false,
  "summary": "one sentence on what the screen shows and how it looks",
  "defects": [
    {"severity": "high | medium | low", "viewport": "desktop | mobile | both",
     "where": "the part of the screen, in words a person can find it by",
     "problem": "what is wrong, as seen",
     "fix": "the change that would put it right"}
  ]
}
```

`high` is a screen that is broken or unusable; `medium` is a clear visible flaw; `low` is a small polish. Give at most 8 defects, the most important first. When the screen looks right, `looks_ok` is true and `defects` is an empty list.
