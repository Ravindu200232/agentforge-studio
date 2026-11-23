{{request}}

Edit the React wireframe in `{{app}}` with the file tools. Read `{{skill}}/SKILL.md` first and change only what the request needs. The Studio handles bundling. Do not install packages or run build scripts.

The wireframes stay low fidelity, whatever the request says. A change adds or alters structure, content, controls, states or navigation; it never makes the wireframes more finished, so a changed page must not turn into a high-fidelity design:

* Black, white and neutral greys only: no colour of any hue (not even red for an error or a delete). Show a state with words, outline icons, weight and borders (a "Low stock" pill, a dark outlined "Delete" button that opens a confirmation, an underlined link).
* If the request asks for a colour, a brand look, a gradient, a photo, a shadow, an animation, or for the page to look prettier, more modern or more polished, do the part of it that is structure or content (the section, the control, the copy, the layout), keep it low fidelity and grey, and say in your last sentence that colour and visual styling are for the prototype.
* An image is a light grey box with a thin diagonal cross and a caption saying what goes there; an avatar is a grey circle with initials; a chart is grey placeholder shapes with real labels and a legend; text is real, specific copy for this product, never lorem ipsum. No decorative illustrations, glass effects or marketing-style visuals.
* Write no colour value of your own: no `#hex`, `rgb()`, `hsl()` or named colour, no colour class such as `bg-red-500`, in a class, a `style`, an SVG `fill` or `stroke`, or `src/index.css`. Use `foreground`, `muted-foreground`, `muted`, `border`, `primary`, `secondary`, `accent` or `neutral-*`.
* Reuse project-authored components and the shared layout in `src/components/layout/`. Write new UI using semantic HTML and Tailwind. Match the spacing, sizes and structure of the neighbouring pages.

{{where}}
