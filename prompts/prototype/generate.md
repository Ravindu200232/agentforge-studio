{{request}}

Make the prototype from the approved wireframes, with the web-artifacts-builder skill (`{{skill}}/SKILL.md`; read it first).

First read what the product is and how people use it, then the wireframes: every page under `{{wireframe}}/src/pages/` and the components they import, to see what each page holds and how the pages link. Then plan the prototype's flow, and write it.

`{{app}}` is the new prototype app, set up for you (step 1 of the skill). Write the finished product in it with the file tools: a high-fidelity, animated prototype that works like the real frontend. The wireframes are only the layout: never change them, and do not copy their files; the prototype's components are its own. Do not install packages or run the skill's scripts: the Studio bundles the app when you are done.

A prototype is a working frontend, not the wireframes in colour. Every button, link, form, tab, filter, menu and row action does what its label says: it opens the screen that comes next, changes what is shown, or answers with a message or a dialog. What a person does on one page shows on the others: keep the sample data in one shared place (a store in `src/lib`) that the pages read and change, so a saved form adds its row to the list, an approval changes a status, and a total follows its lines. Forms check what was typed, then go on to the next screen of their journey. Lists search, filter and sort, and a row opens its own detail page. Draw the empty and the error state too. Before you finish, walk every journey below in your head, from its first screen to its last, and make sure it can be clicked through.

Read what the product is, and how it should look:

{{inputs}}

{{design_direction}}

One page for each screen, keeping everything the wireframe has on it and the way the pages link, made real with believable content:

{{routes}}

{{sign_in}}

Pictures the customer uploaded (import one with `import x from "@/assets/uploads/<name>"`):

{{uploads}}

{{resume}}
