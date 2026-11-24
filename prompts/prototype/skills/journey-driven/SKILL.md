---
name: journey-driven
description: Build and verify each prototype screen against the approved product journeys.
---

# Journey-driven prototype screens

Read `journeys.md` as the approved workflow reference. Keep the IDs, roles, routes and operations aligned with the specification. Use the matching wireframe for layout and the approved design for the visual system.

- Plan one shared sample dataset and one state model. Choose stable sample identities and URLs. Dynamic routes recognize `1` as the first sample record for Studio's screenshot check. Keep values consistent when an action changes them on another screen. Include realistic empty and validation states where the workflow calls for them.
- Before writing a screen, identify the entry conditions, visible controls, state transitions and visible outcomes of its journey steps. Preserve the role's allowed actions. A button that claims to do something must perform the corresponding browser interaction and show its result.
- Render the default screen as well as applicable pending, success and error states. Use semantic elements, accessible names and labels, keyboard operation, wrapping text, and layouts that fit mobile. Use responsive tables or cards where necessary. Preserve reduced-motion behavior and DOM focus.
- Keep state-changing controls and route links testable through the visible interface. Reuse shared behavior and prefer delegated events when the preview swaps route fragments. Guard optional DOM elements on unrelated screens.
- Write the assigned page, then let Studio render it at both widths. Fix confirmed defects before moving on. After the screens are present, walk each journey in order and look for the specified outcome after interacting with the UI. Use the same role and sample records. Record unverified steps and remaining defects honestly.
