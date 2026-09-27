---
name: functional-requirements
description: Comprehensive functional requirements discovery, role permissions, domain workflows, business logic constraints, and 100% requirements coverage with [REQ-XX] identifiers.
---

# Functional Requirements & Domain Modeling Skill

## Core Responsibilities
1. **Requirements Coverage & Traceability Matrix**:
   - Every identified user need is assigned an immutable, explicit identifier (e.g. `[REQ-01]`, `[REQ-02]`).
   - Each requirement specifies:
     - Target user role (`who`).
     - Observable system action (`what`).
     - Business rationale (`why`).
     - Acceptance criteria with verifiable expected outcome.
     - Priority level: `high`, `medium`, or `low`.

2. **Role & Permission Boundary Scoping**:
   - Define exact boundaries for every actor in the system (e.g., Guest, Authenticated Member, Admin, Manager).
   - If authentication is required, specify both authenticated permissions and guest restrictions.
   - For every protected resource, enforce explicit access rules (e.g., "Only the owner of a booking or an Admin can cancel it").

3. **Workflow & Life-cycle State Transitions**:
   - Trace end-to-end workflows from initiation to terminal state (e.g., Booking: `Draft` -> `Pending` -> `Confirmed` -> `Completed` / `Cancelled`).
   - Enumerate all valid state transitions and explicitly prohibit illegal jumps.
   - For every action, capture both the happy path and non-happy paths (validation error, resource locked, quota exceeded).

4. **Data Entity Attributes & Validations**:
   - Plain plural collection names (`users`, `bookings`, `products`).
   - Strict field types, nullability, uniqueness, and relational foreign keys (`references: "collection.id"`).
   - Field-level validation rules (length bounds, regex patterns, numeric ranges).
