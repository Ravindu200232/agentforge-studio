---
name: diagram-crafting
description: Semantic visual Mermaid architecture and flow diagrams paired with detailed, non-technical plain-English narrative walkthroughs and system flow explanations.
---

# Diagram Crafting & Visual Flow Modeling Skill

## Core Principles
1. **Multi-View Architectural Diagrams**:
   - **System Context Diagram**: High-level view showing the application boundary, external user roles, external third-party services (payment gateways, notification services), and data storage.
   - **Component Diagram**: Shows how UI screens communicate with API endpoints, domain controllers, and persistent database collections.
   - **Sequence Diagram**: Temporal message exchange between user, frontend, API, database, and external providers for critical operations.
   - **Entity-Relationship (ERD) Diagram**: Data entities, primary keys, foreign key references, and cardinality relationships.
   - **User Workflow / Activity Diagram**: Step-by-step user interaction flow from landing to action completion.

2. **Plain-English Flow Explanation (Non-Technical Reader Requirement)**:
   - For every diagram generated, an accompanying **Natural Language Flow Walkthrough** must be provided directly beneath the diagram.
   - **Structure of the Flow Explanation**:
     - **Summary**: What the diagram represents in everyday business terms without software engineering jargon.
     - **Step-by-Step Flow**:
       - *Step 1*: How the interaction starts (e.g. "The customer opens the website and views available items").
       - *Step 2*: What the system does in response (e.g. "The system verifies availability in the database and loads pricing").
       - *Step 3*: User decision or action (e.g. "The customer enters their details and submits the booking").
       - *Step 4*: Backend processing & outcome (e.g. "The payment is processed, the reservation is saved, and a confirmation is shown").
     - **Business & Security Guardrails**: What safeguards protect the user and data at each step of this flow.

3. **Mermaid Syntax Clarity**:
   - Use standard Mermaid syntax (`flowchart TB`, `flowchart LR`, `sequenceDiagram`, `erDiagram`).
   - Clean, descriptive node labels without syntax errors or unescaped characters.
   - Consistent, modern color palette matching dark theme aesthetic.
