# System Context diagram

**What is a System Context Diagram?**

A system context diagram defines the software boundary and its externally visible relationships with people, external systems, and persistent data.

## Standard

- ISO/IEC/IEEE 29148:2018
- Mermaid form: `flowchart TB`

## How to draw it

- Start with one central system boundary and keep implementation detail inside it minimal.
- Place human actors and external systems outside the boundary.
- Label every supported interaction or data relationship and omit unsupported integrations.
