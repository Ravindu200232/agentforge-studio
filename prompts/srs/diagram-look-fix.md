# Draw the diagram again, fixing what the screenshot shows

The {{kind}} diagram below was drawn and photographed, and a reviewer who looked at the picture found these visible problems:

{{defects}}

The picture attached is the screenshot the reviewer looked at.

The Mermaid source it was drawn from:

```
{{source}}
```

Rewrite the source so that the problems are gone:

- keep everything the diagram says: the same elements, the same names, the same relationships and the same notation. Only how it is laid out and written changes;
- shorten a label that runs out of its shape (keep its meaning), break a long one into lines with `<br/>`, change the direction (`LR` or `TD`) or group related elements in a `subgraph` when that makes it compact and readable;
- remove what only makes the picture wrong: duplicate links that cross for nothing, raw markup in a label, a shape with no label;
- the source must still open with `{{declaration}}`.

Reply with the corrected Mermaid source only: no fence, no explanation, nothing before or after it.
