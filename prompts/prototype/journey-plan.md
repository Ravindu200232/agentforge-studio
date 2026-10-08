# What a person does on this screen for this step of a journey

You are clicking through one journey of a clickable prototype, step by step, the way a real person would, in a browser. The journey is **{{journey}}**, walked by {{who}}.

Step {{number}} of {{total}}: "{{step}}"

The screen the browser is on: **{{page}}** (`{{file}}`), headed "{{heading}}".{{signed_in}}

What the screen says, from the top of it:

{{text}}

What can be used on this screen, each with a number (a menu button opens a list; what is in the list is only there once it is open):

{{elements}}

Decide what the person does on this screen to carry out the step, using only the numbered things above.

- A step that only looks, reads or checks something ("sees", "reads", "lands back") needs nothing done: answer with no actions.
- Fill in what the step names, and any other field a real person has to complete before the page lets them go on, with believable demo values: a name like "Ada Perera", an email like "ada.perera@example.com", the password `Demo!2026`, a phone number like "0771234567", an address like "12 Galle Road, Colombo 03", a sensible number or date. For a list or a choice, use one of the options shown; for a box to tick, say `fill` with `yes`. For a field that asks for a photo, say `fill` with `photo`.
- For a search or a filter, use words and numbers that are really on the screen (a brand or a model it shows) and keep them broad, a price range at least as wide as the prices shown, so that something is left to open afterwards.
- Then press the one thing a person would press to carry the step out (a button or a link). That click comes last, because the page may change after it.
- A dialog that is open is part of the screen (its buttons are in the list, marked "dialog"). When the step says to confirm, save, send or cancel, press the dialog's own button for it; when all the step asks is to open something, there is nothing more to do.
- Only what is on this screen: never invent a number that is not in the list. Never press anything that signs the person out, and never follow a link to another website.
- At most {{most}} actions.

Reply with ONLY one JSON object:

{"actions": [{"do": "fill", "element": 3, "value": "..."}, {"do": "click", "element": 7}], "why": "one sentence"}
