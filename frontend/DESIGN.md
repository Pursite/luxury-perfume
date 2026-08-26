---
version: alpha
ownership: "This document owns visual intent; src/styles/tokens.css is the runtime token source."
colors:
  ink: "#080808"
  inkRaised: "#0e0e0d"
  surface: "#151412"
  media: "#12110f"
  ivory: "#f4f1e8"
  ivoryMuted: "#b8b1a3"
  ivorySubtle: "#8f897f"
  gold: "#c6a15b"
  goldMuted: "#9a7b44"
  danger: "#d48072"
  success: "#9dad96"
typography:
  display:
    fontFamily: "Bodoni Moda, Georgia, serif"
    lineHeight: "0.96"
  interface:
    fontFamily: "Manrope, system-ui, sans-serif"
    lineHeight: "1.55"
rounded:
  DEFAULT: "1px"
spacing:
  page: "clamp(1.25rem, 4vw, 4.5rem)"
  rhythm: "0.35rem, 0.6rem, 0.9rem, 1.25rem, 1.75rem, 2.5rem, 3.5rem, 5rem"
components:
  buttons:
    radius: "1px"
    minHeight: "2.85rem"
  productMedia:
    treatment: "unframed"
    aspectRatio: "1 / 1.12"

---

# Luxury Perfume visual context

## Overview

Luxury Perfume is a hybrid storefront: the catalogue and product detail are
editorial brand surfaces, while account and cart are practical product flows.
The north star is a private fragrance ledger: an ink-dark boutique catalogue
with warm paper-like type, deliberate whitespace, and imagery doing most of
the selling. It must never resemble a SaaS dashboard, marketplace grid, or
black-and-gold casino interface.

The memorable signature is a single fine “sillage rule”: a neutral-to-muted
gold hairline used only in the catalogue masthead and fragrance pyramid. The
rest of the interface earns its premium feeling through composition, not
decoration.

## Colors

`#080808` is the document ink. `#0e0e0d` is a quiet raised layer for shell
controls and loading geometry. `#151412` is the readable surface for forms,
states, menus, and the cart summary. `#12110f` is reserved for image media so
photography remains the visual protagonist.

Warm ivory is hierarchical: `#f4f1e8` is primary reading text,
`#b8b1a3` is supporting copy, and `#8f897f` is metadata/helper text. Gold
(`#c6a15b`) is a high-value accent only: active navigation,
focused controls, editorial eyebrows, meaningful primary actions, and the two
sillage rules. Muted gold is used for quiet composition labels. It is not a
default border color.

Danger is `#d48072` with `#efc2ba` for readable copy; success is the quiet sage
`#9dad96`. Neither status is communicated by color alone: the existing text,
role, and icon/structure remain authoritative.

## Typography

Bodoni Moda is the display voice, used for the wordmark, page titles, product
names, section titles, and fragrance-note names. It is editorial but never
allowed to become oversized for its own sake. Manrope handles navigation,
labels, metadata, body copy, prices, controls, and errors. Labels use modest
tracking; body copy stays normally spaced and readable at 200% zoom.

The runtime type path is `DESIGN.md → src/styles/tokens.css → global.css,
components.css, pages.css`. No additional font or icon dependency is allowed.

## Layout

The page frame remains a centered, fluid column with `--space-page` gutters.
The main rhythm uses the shared `--space-*` scale rather than local arbitrary
values. Desktop can breathe, but the catalogue keeps the first product row
within a useful browse distance. Mobile reflows to one readable column and
retains practical touch targets; it is not a hidden desktop layout.

The header remains in normal document flow at its existing height and is
organized as brand, navigation, and client-access zones. There is no
blurred sticky shell, scroll listener, parallax, or decorative layer that can
intercept pointer events.

## Elevation & Depth

Static content is nearly flat. Depth comes from a surface step and a restrained
shadow only where a menu or confirmation dialog needs separation. Product media
is unframed and image-led. Avoid glass, blur, large shadows, and stacked
cards.

## Shapes

Corners are effectively square (`1px`). Buttons, fields, menu rows, media, and
badges share this shape language. Nothing is pill-shaped; the cart count is a
small square editorial marker rather than a floating bubble.

## Components

- Primary buttons are rare gold-filled actions: sign in, create account, add to
  cart, and confirmed destructive actions.
- Secondary buttons are ivory-outline. Quiet actions are text or hairline
  links. Future/unavailable controls stay visibly disabled and preserve the
  existing focusable tooltip wrapper.
- Inputs are dark surface fields with a neutral hairline, a clear label, and a
  gold focus ring. Error copy and `aria-invalid` remain visible.
- Product cards have no application-card frame: image-led media transitions to
  a brand/name identity block and a small commerce ledger pairing facts,
  price, and availability. Hover only adds a tiny image refinement and never
  carries essential information.
- Product detail uses an intentional image stage, a separate identity and
  commerce decision area, then an editorial story/specification rhythm. The
  fragrance pyramid is the one signature rule and uses widening, aligned note
  tiers instead of decorative diagrams.
- Login and Signup use an open private-client composition: editorial
  introduction beside a precise credential column. Account remains a dossier-
  like ledger, and Cart is a two-column shopping bag with a statically placed
  summary that stays in normal document flow.
- Loading, error, and empty states reserve geometry and use the same surface,
  type, and hairline language as successful content.

## Do's and Don'ts

Do use hierarchy, image scale, line length, and rhythm to signal value. Do keep
focus-visible, labels, live status, reduced motion, keyboard menus, and touch
targets intact. Do let long names wrap naturally.

Do not add decorative gradients, glow, giant rounded cards, pill controls, generic
dashboard panels, hover-only actions, or motion that delays a task. Do not use
gold for every border, label, or state. Do not replace real API data with
visual placeholders.

## Runtime mapping

`src/styles/tokens.css` is the canonical runtime implementation of the values
above. `--line-subtle`, `--line-default`, and `--line-accent` derive borders
from the ivory/gold hierarchy; `--line-soft` remains a compatibility alias for
existing component selectors. `src/styles/global.css` owns document rhythm,
focus, scrollbar, and reduced-motion behavior. Component and page styles own
only their visual variants; API, routing, context, and domain behavior remain
unchanged.
