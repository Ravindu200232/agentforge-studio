# SRS source index

This folder contains the source-of-truth catalogue and this human-readable
index. Raw downloaded data belongs in `../srs-data/`, where each archive has a
local receipt containing its retrieval timestamp, licence, attribution and
checksum.

| ID | Source | Licence / import status | Local data | How AgentForge uses it |
| --- | --- | --- | --- | --- |
| `pure-2017` | [PURE: a Dataset of Public Requirements Documents](https://zenodo.org/records/1414117) | CC-BY-3.0 — allowed with attribution | `../srs-data/pure-2017/requirements-xml.zip` | Structure and requirement-language evaluation. The source reports 79 documents / 34,268 sentences; the downloaded release has 18 XML files, recorded separately rather than treated as equivalent. |
| `promise-exp` | [PROMISE expanded requirements dataset](https://github.com/AleksandarMitrevski/se-requirements-classification/blob/master/0-datasets/PROMISE_exp/PROMISE_exp.arff) | CC-BY-SA-3.0 — allowed with attribution and share-alike | `../srs-data/promise-exp/PROMISE_exp.arff` | Functional/non-functional classification and measurable-quality checks. Its 969 verified ARFF rows supply the balanced 100-case local evaluation pack. |
| `ieee-29148-template` | [ISO/IEC/IEEE 29148 SRS template](https://github.com/DIN-DKE/ISO_IEC_IEEE_29148__SRS-Template) | Reference-only until the repository licence is verified at import time | No raw data | Section-structure cross-check for IEEE 830 / ISO/IEC/IEEE 29148 aligned output. The ISO standard itself is not copied here. |
| `gitreq-2026` | [GitReq quality-requirements dataset publication](https://arxiv.org/abs/2606.21810) | Reference-only — dataset licence is not yet verified | No raw data | Expert-validation and quality-category evidence only; never downloaded or sent to a model. |

## Attribution

- PURE: Ferrari, A., Spagnolo, G. O., & Gnesi, S. (2017), *PURE: a Dataset of
  Public Requirements Documents*.
- PROMISE: PROMISE Software Engineering Repository dataset; Jane
  Cleland-Huang (2007), with expanded-dataset attribution retained.

The machine-readable equivalent is [`catalog.json`](catalog.json).
