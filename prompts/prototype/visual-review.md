You are reviewing one page of a prototype. The pictures attached are real screenshots of that page, taken in a browser: {{pictures}}

Page: **{{page}}** (route `{{route}}`)

Look at the pictures the way a careful designer would at a handover and list what is visibly wrong. Judge only what you can see, and report a problem only when you can point at it: text that is cut off, overlaps something or is hard to read; a layout that has broken (items colliding, content pushed off the edge, a page wider than the screen on mobile); an image that did not load or is badly stretched; a large empty area where something looks missing; controls that look wrong; placeholder or broken text ("Lorem ipsum", "undefined", "NaN", an unreplaced `{{...}}`); spacing or type sizes that clearly disagree with the rest of the page.

Do not report taste, the product's content, or anything you cannot see. A page that looks right has no problems: say so.

Answer with ONE JSON object and nothing else:

```json
{
  "page": "{{route}}",
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

`high` is a page that is hard to use or looks broken, `medium` a clear visible flaw, `low` a small polish. At most 8 defects, the most important first. When the page looks right, `looks_ok` is true and `defects` is empty.
