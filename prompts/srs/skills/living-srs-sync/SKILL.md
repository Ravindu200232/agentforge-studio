---
name: living-srs-sync
description: Operates the SRS as the living parent document and single source of truth across all build phases, synchronizing planner, design, prototype, builder code, and QA test results for 100% parity.
---

# Living SRS Synchronization & Traceability Skill

## The Living Parent Document Concept
The SRS is not a static document archived after an interview; it is the **Living Parent Contract** of the entire application lifecycle:
1. **Parent-to-Child Propagation**:
   - Initial user requirements shape the Builder Planner, Design System, HTML Prototype, Code Architecture, and QA Test Journeys.
2. **Child-to-Parent Continuous Feedback Loop**:
   - When the **Planner** breaks down tasks and decides API routes/components $\rightarrow$ The SRS is updated with the concrete route signatures and module boundaries.
   - When **Design** establishes styling, color palettes, and typographic scales $\rightarrow$ The SRS records the design tokens and layout system.
   - When the **HTML Prototype** is built or modified $\rightarrow$ The SRS is enriched with screen layouts, interactive controls, and visual evidence.
   - When the **Builder** implements features $\rightarrow$ Implemented code files and endpoints are mapped against functional requirements `[REQ-XX]`, updating their status to `IMPLEMENTED`.
   - When **Testing / QA** runs verification $\rightarrow$ Unit test results, E2E browser journeys, and console evidence are linked to each requirement, updating status to `TESTED & VERIFIED`.

## 100% Traceability & Parity Rule
- Every implemented route, schema, and page component must trace back to an explicit requirement in the SRS.
- The final delivered application must be **100% equal and compliant** with the living SRS document.
- The synchronization engine maintains a live ledger showing:
  - Total Requirements vs. Implemented vs. Verified.
  - Active links between requirements, prototype screens, code files, and test cases.
