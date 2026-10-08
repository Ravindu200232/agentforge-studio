{{who}} was walked through this journey of a prototype in a real browser, one step at a time: the browser clicked and typed, and a screenshot was taken at every step. The pictures attached are those screenshots, in the order of the steps. {{pictures}}

Journey **{{journey}}** (`{{id}}`).

The steps, and what the browser did to carry out each:

{{steps}}

This is a prototype, not the finished application: it works like the real frontend (pages, forms, dialogs, messages) with sample data and no server behind it. Judge it as that, and be generous. What a person does in one step does not have to show up in another screen, on the next visit, or in a list, counter or total; a saved form may only say it was saved. A step is done when the screen it happens on is showing and the person could do what the step says there: the control is on the screen and pressing it gives some answer (the next screen, a message, a dialog, a changed state). A dialog left open at the end of a step, or a form filled in and not yet sent, is a person in the middle of a step: not a problem.

What is a problem: a blank, broken or wrong screen; a control the step needs that is not there, or does nothing a person can see; a link that goes nowhere; text that is cut off, overlapping or unreadable; an image that did not load; a layout that has fallen apart.

For every step say whether the screenshot shows the step carried out: `ok` is true when it shows the screen the step happens on in the state the step describes, false when the wrong screen is showing, the result is not there, or the browser could not do the step (the notes say when). `summary` is one sentence on what the picture shows. `defects` are things visibly wrong on that screen; judge only what you can see.

Then say whether the journey as a whole could be carried out by clicking through the prototype: `completes` is true when a person could go through every step on the screens the steps name; false only when a step could not be done at all.

Answer with ONE JSON object and nothing else, with one entry in `steps` for every step above, in order:

```json
{
  "journey": {"completes": false, "summary": "one sentence on whether a person can get through this journey"},
  "steps": [
    {"id": "{{id}}-S01", "ok": true, "summary": "what the picture shows",
     "defects": [
       {"severity": "high | medium | low", "where": "the part of the screen, in words a person can find it by",
        "problem": "what is wrong, as seen", "fix": "the change that would put it right"}
     ]}
  ]
}
```

`high` is a step that cannot be done or a screen that looks broken, `medium` a clear visible flaw, `low` a small polish. At most 5 defects for a step, the most important first.
