---
name: non-functional-quality
description: Quantifiable non-functional specifications, performance thresholds, mobile & laptop responsive requirements, WCAG 2.1 AA accessibility, and fault-tolerance SLOs.
---

# Non-Functional Requirements & Quality Engineering Skill

## Performance Benchmarks & SLOs
1. **API Response Latency**:
   - `p95` response latency under ordinary load must be `< 200ms` for read queries and `< 400ms` for transactional mutations.
   - Initial page loads (DOMContentLoaded) must complete in `< 1.2s` on 4G mobile and broadband connections.
2. **Concurrency & Throughput**:
   - The system architecture must sustain target concurrent active sessions with zero memory leaks and automatic connection pooling.

## Multi-Device Responsiveness (Mobile & Laptop)
1. **Viewport Fluidity**:
   - The UI must adapt seamlessly across screen widths:
     - Mobile Phones: 360px – 480px (single column stack, touch-friendly touch targets >= 44x44px).
     - Tablets: 640px – 768px (adaptive grid, slide-over navigation).
     - Laptops & Desktops: 1024px – 1920px (multi-pane layout, persistent sidebars).
2. **Touch & Keyboard Ergonomics**:
   - Zero horizontal overflow on mobile viewports.
   - Interactive elements must support both click and touch interactions, with clear active states (`active:scale-95`).

## Accessibility & Standards (WCAG 2.1 AA)
1. **Contrast & Color Semantics**:
   - Foreground text to background contrast ratio must be at least `4.5:1` for normal text and `3:1` for large headings.
   - Information must never be conveyed solely through color (pair colors with icons, labels, or badges).
2. **Keyboard Navigation & Screen Reader Support**:
   - Full keyboard focus navigation (`Tab`, `Shift+Tab`, `Enter`, `Escape`).
   - Visible, high-contrast focus rings (`focus-visible:ring-2`).
   - Semantic ARIA attributes on modals, popovers, and accordions.

## Resilience, Recovery & Error Handling
1. **Graceful Degradation**:
   - Network failure or server errors must display human-readable error banners with retry buttons, never blank screens or unhandled exceptions.
2. **Data Durability**:
   - Atomic database writes with transactional rollback on multi-document operations.
