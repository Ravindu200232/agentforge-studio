# Look at one journey of a clickable prototype

{{who}} was walked through this journey of a clickable prototype in a real browser, one step at a time: the browser clicked and typed, and a screenshot was taken at every step. The pictures attached are those screenshots, in the order of the steps. {{pictures}}

Journey **{{journey}}** (`{{id}}`).

The steps, and what the browser did to carry out each:

{{steps}}

This is a **clickable prototype**, not the finished application: it is a handful of static pages with fixed demo data and no server behind them. Judge it as that, and be generous:

- What a person does in one step does not have to show up anywhere else. A change made in one screen is not expected to appear on another screen, in another person's view (the shop owner changes an order and the shopper sees it), on the next visit, or in a list, a counter or a total. A form that is saved may only say it was saved. Do not count any of that as a problem or as a step not done.
- One page may stand in for many: every phone, order or review may open the same detail page, and the demo data on it need not be the item that was clicked. That is fine.
- A step is done when the screen it happens on is showing and the person could do what the step says there: the control is on the screen and pressing it gives some answer (the next screen, a message, a dialog, a changed state). Do not ask for the exact result the step describes when only a real server could produce it.
- A dialog that is still open at the end of a step, or a form that was filled in and not yet sent, is how a person is in the middle of a step: not a problem.
- What is a problem: the screen is blank, broken or the wrong screen altogether; the control the step needs is not there, or pressing it does nothing at all that a person can see; a link that goes nowhere; text that is cut off, overlapping or unreadable; an image that did not load; a layout that has fallen apart; the header showing the wrong signed-in state.

For every step, say whether the screenshot shows the step carried out, the way a careful tester would at a handover:

- `ok` is true when the picture shows the screen the step happens on, in the state the step describes (an order marked cancelled, a phone listed, a review on the page, a form filled in, the next screen the step lands on). It is false when the wrong screen is showing, the step's result is not there, or the browser could not do the step (the notes say when it could not).
- `summary` is one sentence on what the picture shows.
- `defects` are things that are visibly wrong on that screen: text cut off or overlapping, a broken layout, an image that did not load, text too faint to read, a "Lorem ipsum", "undefined", "NaN" or empty cell where a value belongs, the signed-out header on a page the person is signed in to (or the other way round). Judge only what you can see; do not report taste, and do not report a problem you cannot point at.

Then say whether the journey as a whole could be carried out by clicking through the prototype: `completes` is true when a person could go through every step on the screens the steps name, even where the prototype's demo data does not change. It is false only when a step could not be done at all.

Answer with ONE JSON object and nothing else, in exactly this shape, with one entry in `steps` for every step above, in order:

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

`high` is a step that cannot be done, or a screen that looks broken; `medium` is a clear visible flaw; `low` is a small polish. At most 5 defects for a step, the most important first.
