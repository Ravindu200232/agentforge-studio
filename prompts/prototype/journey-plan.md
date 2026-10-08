You are clicking through one journey of a prototype in a browser, step by step, the way a real person would. The journey is **{{journey}}**, walked by {{who}}.

Step {{number}} of {{total}}: "{{step}}"

The screen the browser is on: **{{page}}** (route `{{route}}`), headed "{{heading}}".

What the screen says, from the top of it:

{{text}}

What can be used on this screen, each with a number (a menu button opens a list; what is in the list is only there once it is open):

{{elements}}

Decide what the person does on this screen to carry out the step, using only the numbered things above.

- A step that only looks, reads or checks something needs nothing done: answer with no actions.
- Fill in what the step names, and any other field a real person has to complete before the page lets them go on, with believable values (a name like "Ada Perera", an email like "ada.perera@example.com", a phone number like "0771234567", a sensible number or date). For a list or a choice use one of the options shown; for a box to tick say `fill` with `yes`; for a field that asks for a photo say `fill` with `photo`.
- For a search or a filter use words and numbers that are really on the screen, and keep them broad so that something is left to open afterwards.
- Then press the one thing a person would press to carry the step out. That click comes last, because the page may change after it.
- A dialog that is open is part of the screen (its buttons are marked "dialog"). When the step says to confirm, save, send or cancel, press the dialog's own button for it.
- Never invent a number that is not in the list, never press anything that signs the person out, and never follow a link to another website.
- At most {{most}} actions.

Reply with ONLY one JSON object:

{"actions": [{"do": "fill", "element": 3, "value": "..."}, {"do": "click", "element": 7}], "why": "one sentence"}
