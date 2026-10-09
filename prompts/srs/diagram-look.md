# Review one diagram by looking at it

You are reviewing a diagram that belongs to a software requirements specification. The picture attached is a real screenshot of it, as it is drawn on screen.

Diagram: **{{title}}** (a {{kind}} diagram)

The Mermaid source it was drawn from, so you can tell what is meant to be there:

```
{{source}}
```

Look at the picture the way a careful analyst would before handing the document over, and list what is visibly wrong with how it is drawn. Judge only what you can see; report a problem only when you can point at it.

What counts as a problem:

- an error picture instead of a diagram (a bomb icon, "Syntax error in text", a mermaid version number, a blank canvas);
- text that is cut off, overlaps a line or another box, runs out of its shape, or is so small that it cannot be read at this size (a diagram drawn so wide or so tall that its labels are tiny);
- boxes, tables or shapes that sit on top of one another, or lines that run straight through a box or a label so that it cannot be read;
- an element that should be connected to the others (the source links it) but floats alone, or a connection whose label is missing or unreadable;
- raw markup in a label: `<br>`, `&lt;`, `\n`, quotes or brackets that were meant to be formatting;
- a layout that is hard to follow: one very long row or column where the diagram could be compact, a tangle of crossing lines, a main flow that runs against the rest;
- shapes with no label, or the same label repeated for different things.

Do not judge the specification itself (whether the right things are in the diagram), the colours you would prefer, or anything you cannot see in the picture. A diagram that is drawn cleanly has no problems: say so.

Answer with ONE JSON object and nothing else, in exactly this shape:

```json
{
  "page": "{{kind}}",
  "looks_ok": false,
  "summary": "one sentence on how the diagram looks",
  "defects": [
    {"severity": "high | medium | low",
     "where": "the part of the diagram, in words a person can find it by (the names written on it)",
     "problem": "what is wrong, as seen",
     "fix": "the change to the source that would put it right"}
  ]
}
```

`high` is a diagram that cannot be read or is not a diagram; `medium` is a clear visible flaw; `low` is a small polish. Give at most 8 defects, the most important first. When the diagram looks right, `looks_ok` is true and `defects` is an empty list.
