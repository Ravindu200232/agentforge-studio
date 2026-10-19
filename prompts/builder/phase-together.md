## Built at the same time as other phases

Other agents are building other phases of this application at this very moment. So:

- Write the files of your own pages (their routes, handlers, components and helpers). Do not rewrite a file the foundation wrote or another phase may be writing: the shared layout, the navigation, the data models, `lib/` and the configuration.
- When one of your pages needs something shared that is not there yet, add it in a new file of your own; to add one field to a shared model, change only that line with `replace_text`.
- Record your pages only in this phase's own record named above.
