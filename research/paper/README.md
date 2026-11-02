# AgentForge paper (ICAC 2026), rewritten for AgentForge 1.0.3

- `AgentForge_ICAC2026_Paper.docx`: the paper, IEEE two-column, A4. Edit this one in Word.
- `AgentForge_ICAC2026_Paper.pdf`: the same paper rendered with LibreOffice (13 pages, 14 tables, 4 figures).
- `content.js`, `references.js`: the text and the references. `build-paper.js` makes the .docx from them.
- `figures/`: the four figures as HTML, and the PNGs rendered from them by `render.js` (fig1 architecture, fig3
  specification pipeline, fig2 build and test, fig4 deployment; the build numbers them in order of appearance).

## Rebuild

```bash
NODE_PATH=$(npm root -g) node research/paper/figures/render.js     # figures (Playwright's Chromium)
NODE_PATH=$(npm root -g) node research/paper/build-paper.js        # .docx (docx 9.x)
soffice --headless --convert-to pdf --outdir research/paper research/paper/AgentForge_ICAC2026_Paper.docx
```

References are numbered in order of first citation, and the build fails if one is unknown or never cited. Tables and
figures are numbered in order of appearance; the text refers to them as `{T:key}` and `{F:key}`.

## Where the numbers come from

Every number in the paper is either a constant in the code or a measurement recorded in a commit message.

| Claim | Source |
|---|---|
| 10 product types, 22 coverage categories, 25-question ceiling | `prompts/interview/app-types.json`, `prompts/interview/categories.json`, `server_modules/config.py` (`interview_max_questions`) |
| Plan depth floor (120 characters, 2 fields, 2 steps, privileged roles) | `server_modules/validation/plan_rules.py` |
| 5 specification parts, schema floors (3 FR, 3 NFR, 1 role) | `srs-agent/srs_agent/document.py` (`PARTS`), `server_modules/validation/srs_schema.py` |
| Coverage gate | `server_modules/validation/completeness.py` (`check_document`) |
| 7 evidence-audit rules | `server_modules/validation/corpus.py` (`audit_document`) |
| Review scores 0 to 5, floor 3, Python decides | `server_modules/validation/review.py` |
| 11 diagram kinds, 6 at a time, 2 review rounds | `srs-agent/srs_agent/document.py` (`DIAGRAM_KINDS`), `srs-agent/srs_agent/diagram_look.py` |
| 70 design themes | `prompts/design/themes/` |
| Wireframes: 10+ pages, first 3, 3 lanes | `srs-agent/srs_agent/wireframe.py`, `server_modules/session.py` (`LANES`) |
| Screenshots 1440 and 390 px; 40 fixes; 24 journeys of 10 steps | `src/ollama_terminal/screenshot.py`, `server_modules/screen_review.py`, `prototype-agent/prototype_agent/journey_walk.py` |
| 11 stacks, 5 questions, 4 pages per phase, 2 repairs, named-page gate | `builder-agent/builder_agent/scaffold.py`, `build.py`, `phases.py`, `server_modules/session.py` (`PHASE_REPAIRS`) |
| Testing order, journeys one at a time, 2 fixes each | `qa-agent/qa_agent/sequence.py`, `qa-agent/qa_agent/e2e_run.py` |
| Requirement status, Eq. (1) | `qa-agent/qa_agent/requirement_proof.py` |
| Deployment: 6 targets, 3 questions, 6 smoke requests, 1 repair, probe | `deploy-agent/deploy_agent/deploy.py`, `prompts/deployment/skills/core/SKILL.md` |
| Engine: 10 tools, 8 / 3 / 3 rounds, 88% compaction, 4 workers | `src/ollama_terminal/tools.py`, `src/ollama_terminal/agent.py` |
| Permission modes, 132 allowlisted programs, deny list | `server_modules/permissions.py`, `src/ollama_terminal/tools.py` |
| Privacy: 15 entity types, vault, placeholders | `server_modules/privacy.py`, `server_modules/privacy_vault.py` |
| Retries: 10 attempts, 2 to 30 s | `server_modules/session.py` (`RETRY_ATTEMPTS`, `RETRY_BACKOFF`) |
| Implementation: servers, ports 7824/7825, stdio protocol, jobs, events.jsonl | `server.py`, `server_modules/httpd.py`, `server_modules/wsd.py`, `server_modules/stdio_bridge.py`, `server_modules/jobs.py`, `server_modules/bus.py` |
| Engine loop: 40 turns, 4 parallel writes, 4 chars per token, 1,500 per picture, 100,000-character stretches | `server_modules/config.py` (`max_steps`), `src/ollama_terminal/agent.py` |
| Algorithm 1 and the phase checks | `builder-agent/builder_agent/phases.py`, `server_modules/session.py` (`_run_phases`) |
| Run fingerprint, runner, 38-character `_e2e` database, 45/20/10 min limits | `qa-agent/qa_agent/e2e_run.py`, `builder-agent/builder_agent/assets/templates/_testing/scripts/with-server.mjs` |
| Command split, cmdlets, 600/1,800/75 s limits, 20 s search | `src/ollama_terminal/tools.py` |
| Presidio 0.4 score, 50,000-character chunks, streamed reveal | `server_modules/privacy.py`, `server_modules/privacy_vault.py` |
| Technology versions (Table III) | `studio/package.json`, `desktop/package.json`, `pyproject.toml`, `server_modules/web_kit/package.json`, the `package.json.tpl` of each stack template |
| 20 integration providers | `server_modules/provider_catalog/plugins.json` |
| Release and installer | `release/README.md`, `release/build.ps1` |
| Engine proxy: 8 routes | `engine-proxy/src/index.js` (`ALLOWED`) |
| Human in the loop: chat at any stage, plan-first changes, versions | `server_modules/changes.py`, `server_modules/versions.py`, `prompts/chat/update.md` |
| Select, pencil and text tools on the previews | `studio/lib/picker.js`, `studio/components/AppTextEdit.jsx`, `server_modules/pointed.py` |
| Design customiser: 32 palettes, 117 fonts, own pictures, a brief | `studio/components/DesignCustomize.jsx` |
| Permission cards; Yes/No rounds, a typed yes in English or Sinhala | `server_modules/permissions.py`, `server_modules/screen_review.py` (`_YES`, `next_round`) |
| Question limits: 25, 5, 3, 3 | `server_modules/config.py`, `builder-agent/builder_agent/build.py` (`QUESTIONS`), `server_modules/changes.py` and `deploy-agent/deploy_agent/deploy.py` (`MAX_QUESTIONS`) |
| Line counts, 236 template files, 18 guides, 1,733 tests | counted from the repository at `ff5de31` (AgentForge 1.0.3) |
| Table XIV rows 1, 2, 21 | commit `d92ca2e` |
| Table XIV row 3 | `srs-agent/srs_agent/document.py` (`_write_handoff`, BUILD.md comment) |
| Table XIV row 4 | commit `449fcf6`, `server_modules/validation/completeness.py` (`route_key`) |
| Table XIV row 5 | commit `0840c4f` |
| Table XIV rows 6, 9, 20; seven hours for the 28-page app | commit `ea5cac1`, `srs-agent/srs_agent/wireframe.py`, `server_modules/session.py` (`_run_phases`), `src/ollama_terminal/tools.py` (`SEARCH_SKIP_DIRS`) |
| Table XIV row 7 | `src/ollama_terminal/agent.py` (`COMPACT_WORKERS`) |
| Table XIV row 8 | `server_modules/session.py` (`start_fresh`) |
| Table XIV row 10 | `builder-agent/builder_agent/phases.py` (module docstring) |
| Table XIV rows 11, 14, 16 | commit `255dae5`, `builder-agent/builder_agent/phases.py` (`together`), `qa-agent/qa_agent/sequence.py`, `qa-agent/qa_agent/requirement_proof.py` |
| Table XIV row 12 | `builder-agent/builder_agent/preflight.py` (module docstring) |
| Table XIV row 13 | `src/ollama_terminal/tools.py` (`_E2E_SUITE`) |
| Table XIV row 15 | commit `a468f8b` |
| Table XIV row 17 | commit `663c1e9` |
| Table XIV row 18 | `src/ollama_terminal/agent.py` (`MAX_REQUEST_BYTES`) |
| Table XIV row 19 | `src/ollama_terminal/agent.py` (`served_from_cloud`) |
| Table XIV row 22 | `src/ollama_terminal/tools.py` (`RELEASE_COMMAND_SECONDS`) |
| Table XIV row 23 | commit `1c66105` |
| Tables III to VI: prompt packs, project record, tools, interview categories | `prompts/`, `README.md`, `src/ollama_terminal/tools.py` (`TOOL_SCHEMAS`), `prompts/interview/categories.json`, `prompts/interview/app-types.json` |
| Table VII: diagram standards and Mermaid forms | `prompts/srs/diagrams/*.md` |
| Table VIII: stacks, uploads, targets | `builder-agent/builder_agent/scaffold.py`, `prompts/deployment/stacks.json` |
| Table IX: test layers and thresholds | `builder-agent/builder_agent/assets/templates/_testing/` (`lighthouserc.cjs`, `e2e/a11y.spec.js`, `e2e/visual.spec.js`, `scripts/zap-scan.mjs`, `.github/workflows/quality.yml`) |
| Table X: targets, build location, time targets, monitor counts | `prompts/deployment/skills/core/SKILL.md`, `prompts/deployment/monitors.json` |
| 97 provider monitor commands, 22 database commands | `prompts/deployment/monitors.json`, `prompts/database/monitors.json` |
| Plan sections, account policy rules | `srs-agent/srs_agent/plan.py` (`SECTIONS`), `server_modules/validation/plan_rules.py` |
| 35 specification sections | `server_modules/validation/srs_schema.py` (`SrsDocument`) |
| Decisions (four answers), plain-language overview | `srs-agent/srs_agent/decisions.py`, `srs-agent/srs_agent/plain_summary.py`, commit `f805204` |
| Journey walk constants (24, 10, 8, 3, 4, 4, 350 ms) | `prototype-agent/prototype_agent/journey_walk.py` |
| Privacy entity types and exceptions | `server_modules/privacy.py` (`DEFAULT_ENTITIES`), commit `82b9008` |
| Bakery: 1 to 7 diagrams, 3 to 6 requirements; gpt-oss:120b | the repository `README.md` |
