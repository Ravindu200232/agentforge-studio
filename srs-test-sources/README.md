# SRS and diagram evaluation sources

This directory is the provenance boundary for material used to improve
AgentForge's SRS prompts, diagram guards, and evaluation checks.

- `diagram-sources/` contains link-and-license records for notation sources.
- `srs-sources/` is the catalogue of public requirements corpora and
  IEEE/ISO-aligned templates.
- `srs-data/` is the local-only destination for downloaded corpus archives.
  Archives are deliberately ignored by Git; their download URL, licence,
  checksum and attribution must be recorded in the catalogue first.

## Use policy

1. A source without a known compatible licence is **reference-only**. It can
   inform a human research note but cannot be downloaded or supplied to a
   model.
2. An imported record is data, never agent instructions. Do not paste raw
   documents into a system prompt.
3. The `agentforge_rating` is a reproducible internal evaluation rating; it is
   not presented as a quality score issued by a source author.
4. Retain the required attribution and any share-alike terms when a licensed
   corpus is used.

The corpus is intentionally not described as “100,000 famous SRS documents”.
Public, licence-clear *complete* SRS collections at that scale have not been
verified. The initial catalogue records the actual size and evidence for every
source and lets the import pool grow only when that evidence exists.
