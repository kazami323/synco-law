---
name: LexOS Uzbekistan
colors:
  surface: '#f8f9ff'
  surface-dim: '#d8dae1'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f1f3fb'
  surface-container: '#eceef5'
  surface-container-high: '#e6e8ef'
  surface-container-highest: '#e0e2ea'
  on-surface: '#181c21'
  on-surface-variant: '#414751'
  inverse-surface: '#2d3136'
  inverse-on-surface: '#eff0f8'
  outline: '#717783'
  outline-variant: '#c0c7d3'
  surface-tint: '#0060a8'
  primary: '#005ea4'
  on-primary: '#ffffff'
  primary-container: '#1777c9'
  on-primary-container: '#fdfcff'
  inverse-primary: '#a1c9ff'
  secondary: '#5f5f58'
  on-secondary: '#ffffff'
  secondary-container: '#e2e0d7'
  on-secondary-container: '#63635c'
  tertiary: '#874f00'
  on-tertiary: '#ffffff'
  tertiary-container: '#a96400'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d2e4ff'
  primary-fixed-dim: '#a1c9ff'
  on-primary-fixed: '#001c38'
  on-primary-fixed-variant: '#004880'
  secondary-fixed: '#e5e2da'
  secondary-fixed-dim: '#c8c6bf'
  on-secondary-fixed: '#1c1c17'
  on-secondary-fixed-variant: '#474741'
  tertiary-fixed: '#ffdcbd'
  tertiary-fixed-dim: '#ffb86f'
  on-tertiary-fixed: '#2c1600'
  on-tertiary-fixed-variant: '#693c00'
  background: '#f8f9ff'
  on-background: '#181c21'
  surface-variant: '#e0e2ea'
typography:
  headline-h1:
    fontFamily: Manrope
    fontSize: 22px
    fontWeight: '500'
    lineHeight: 32px
  headline-h2:
    fontFamily: Manrope
    fontSize: 18px
    fontWeight: '500'
    lineHeight: 28px
  headline-h3:
    fontFamily: Manrope
    fontSize: 16px
    fontWeight: '500'
    lineHeight: 24px
  body-md:
    fontFamily: Work Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Work Sans
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
  caption:
    fontFamily: Work Sans
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.02em
  headline-h1-mobile:
    fontFamily: Manrope
    fontSize: 20px
    fontWeight: '500'
    lineHeight: 28px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  2xl: 32px
  gutter: 16px
  margin-mobile: 16px
  margin-desktop: 32px
---

## Brand & Style

This design system is built for a professional, reliable, and high-stakes legal operating environment. The aesthetic prioritizes clarity and institutional trust, blending **Modern Corporate** sensibilities with **Minimalist** precision to ensure that complex legal data remains the focus.

The target audience consists of legal professionals in Uzbekistan who require a system that feels authoritative yet technologically advanced. The UI evokes a sense of "digital parchment"—stable, readable, and grounded—utilizing a warm-neutral backdrop to reduce eye strain during long hours of document review. High-contrast elements and crisp borders are used to provide clear affordances and unmistakable status signaling.

## Colors

The palette is anchored by a warm, paper-like background (`#F1EFE8`) to differentiate the workspace from generic SaaS tools. 

- **Primary Accent:** A confident blue used for primary actions and active states.
- **Semantic Colors:** Rigorous adherence to Success, Warning, and Danger colors ensures legal status (e.g., "Filed," "Pending," "Overdue") is immediately recognizable.
- **Neutrals:** The text and border colors utilize a "Warm Charcoal" spectrum rather than pure blacks or grays, maintaining a sophisticated and academic tone suitable for legal discourse.

## Typography

This design system utilizes a dual-font strategy. **Manrope** is used for headlines to provide a modern, refined, and balanced appearance for navigation and section titles. **Work Sans** is used for all body text, labels, and data, chosen for its exceptional legibility in dense legal documents and financial tables.

Maintain a strict vertical rhythm. For legal citations or small-print disclosures, use the `caption` style with its slight letter spacing to ensure readability at small scales.

## Layout & Spacing

The layout utilizes a **Fixed Grid** model for desktop dashboards to maintain the density required for legal work, while transitioning to a **Fluid** model for mobile document viewing.

- **Desktop:** 12-column grid with 16px gutters.
- **Sidebar:** A fixed-width left navigation (240px) is standard for workspace efficiency.
- **Spacing Rhythm:** Use `lg` (16px) as the standard padding for containers. Use `xs` (4px) and `sm` (8px) for tight internal component groupings like label-to-input relationships.

## Elevation & Depth

To maintain a "reliable" and "grounded" feel, the design system avoids heavy shadows. Instead, it uses **Tonal Layers** and **Low-Contrast Outlines**.

- **Level 0 (Background):** `#F1EFE8`.
- **Level 1 (Cards/Surface):** `#FFFFFF` with a 1px solid border of `#D3D1C7`.
- **Level 2 (Popovers/Modals):** `#FFFFFF` with a subtle, highly-diffused shadow (Blur: 12px, Opacity: 5%, Color: #2C2C2A) to indicate temporary overlay without breaking the flat, professional aesthetic.
- **Interactive States:** Hovering over interactive cards should not lift the element; instead, the border color should shift to the Primary Accent blue.

## Shapes

The shape language is "Rounded" to soften the dense, text-heavy nature of legal data, making the workspace feel approachable.

- **Standard Components:** Buttons, Input fields, and Tags use an 8px radius.
- **Containment:** Main content cards and workspace modules use a 12px radius (`rounded-lg`) to create clear visual separation from the background.
- **Strictness:** Do not use pill-shaped elements (except for specific status chips) to maintain a professional, architectural structure.

## Components

### Buttons
- **Primary:** Solid `#378ADD` with white text. 8px radius.
- **Secondary:** Transparent with `#D3D1C7` border and Primary Accent text.
- **Actionable Height:** 40px standard for desktop; 44px for mobile accessibility.

### Input Fields
- White background with a 1px border. On focus, the border transitions to Primary Accent with a 2px outer glow. Labels must always be visible (never placeholder-only) using `body-sm` bold.

### Chips & Status Indicators
- Use a "Soft Fill" approach: Background color at 10% opacity of the semantic color (Success, Warning, Danger) with 100% opacity text of the same color. This ensures high contrast while remaining professional.

### Cards
- White surface, 12px radius, 1px border. No shadow for standard cards. Use `xl` (24px) padding for document cards and `lg` (16px) for utility widgets.

### Lists & Data Tables
- Use alternating row tints or subtle `#D3D1C7` bottom borders. Header cells should use `caption` style in all-caps for distinct hierarchy.