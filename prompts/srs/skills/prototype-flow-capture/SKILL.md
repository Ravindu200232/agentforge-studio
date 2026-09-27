---
name: prototype-flow-capture
description: Inspects the generated prototype demo flow, verifies link and button navigation paths, captures visual screen snapshots, and runs parallel asynchronous extraction into the living SRS.
---

# Prototype Flow Verification & Visual Capture Skill

## Workflow Pipeline
1. **Demo Flow Verification**:
   - As soon as the prototype HTML files (`index.html` and related pages) are drawn:
   - Walk through the prototype structure:
     - Verify page anchors, navigation links, and action buttons.
     - Ensure there are no broken links (`404` or missing anchors).
     - Verify that primary user flows (e.g. browsing, opening details, opening modal, submitting form) function correctly.

2. **Visual Screenshot Capture**:
   - Connect to the running preview using headless Chrome via Chrome DevTools Protocol (CDP).
   - Render the prototype at desktop (`1280x800`) and mobile (`390x844`) viewports.
   - Capture clean PNG/JPEG snapshots of the primary screens and interactive states.
   - Store snapshots in `.agentforge/srs/prototype_shots/`.

3. **Parallel Asynchronous LLM Extraction**:
   - Dispatch an asynchronous background task to analyze the prototype markup and screenshots.
   - Extract:
     - Screen inventory (screen title, purpose, key UI controls).
     - Component visual layout (header, main hero, cards, sidebars, modals).
     - Verified user flow steps demonstrated in the prototype.
   - Format and merge this information into the living SRS schema under `prototype_screens` and `prototype_flows`.
   - Update the SRS preview UI so clients can immediately see the real visual prototype screens embedded alongside the requirements.
