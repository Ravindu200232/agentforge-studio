# Local corpus data

Downloaded archives belong here, but are ignored by Git. Before adding an
archive, add or update the matching record in `../srs-sources/catalog.json`
with its licence, source URL, retrieval date, SHA-256, and attribution.

Only records marked `allowed_with_attribution` or
`allowed_with_attribution_and_share_alike` are eligible for automated import.
`reference_only` means exactly that: do not download, train on, or send its
content to a model.

To build the first 100 label-balanced evaluation cases from the downloaded
CC-BY-SA PROMISE corpus, run `python tools/srs_corpus.py build-evaluation
promise-exp --size 100`. The generated JSONL records its source row, category,
licence, attribution, deterministic AgentForge rating and SHA-256 receipt.
