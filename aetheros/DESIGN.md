# AetherOS web design system

Built from the existing Aether identity in `DESIGN_TOKENS.md` (carried over
from the project's wallpaper/art generator) plus the component and layout
decisions needed to build the marketing site. Not based on a UXKIN
comparison — UXKIN wasn't connected in this session — so this direction
comes from the existing brand tokens, the "obsidian / navy / blue, no
generic AI-cyberpunk neon" note already in `DESIGN_TOKENS.md`, and the
product itself (a serious, privacy-first gaming OS — the site should read
as confident and technical, not like a hype landing page).

## Color

| Token | Value | Role |
|---|---|---|
| `--bg` | `#08090C` | Page background (Deep Void) |
| `--bg-raised` | `#0F131A` | Cards, panels, header (Cyber Obsidian) |
| `--bg-raised-2` | `#151A22` | Nested surfaces (code blocks, inputs) |
| `--line` | `#232330` | Default border |
| `--line-soft` | `#1A1E27` | Faint separators inside cards |
| `--text` | `#EBEEF2` | Headings, primary text |
| `--text-dim` | `#9AA3AD` | Body copy, secondary text |
| `--text-faint` | `#636B78` | Captions, meta |
| `--accent` | `#00A3FF` | Primary action, links, focus ring (Aether Blue) |
| `--accent-2` | `#2B56FF` | Secondary glow / gradients only, never solid text (Indigo) |
| `--success` | `#2ED99B` | Verified / online states |
| `--warning` | `#F5B544` | Caution notes (e.g. "not run directly") |

Dark only — there is no light mode. Body text on `--bg` is `#EBEEF2` on
`#08090C`, well over 4.5:1. `--accent` on `--bg` is used for text only at
18px+/bold (large-text contrast); for body-size links it's always
underlined, not color-alone.

## Typography

System font stack — matches the OS itself (GNOME/Segoe-adjacent), loads
instantly, no webfont layout shift:

```
font-family: "Inter", "Segoe UI Variable", "Segoe UI", system-ui,
  -apple-system, Roboto, sans-serif;
```

Inter is loaded (self-hostable, OFL) for weight range 400–800; falls back
to the OS font stack immediately if it fails to load.

| Token | Size / line | Weight | Use |
|---|---|---|---|
| `display` | 56px / 1.08, -0.02em | 800 | Hero H1 |
| `h1` | 40px / 1.15, -0.01em | 800 | Section H1 (rare) |
| `h2` | 30px / 1.2, -0.01em | 700 | Section headings |
| `h3` | 19px / 1.3 | 700 | Card / subsection headings |
| `body-lg` | 18px / 1.6 | 400 | Hero lead, intro paragraphs |
| `body` | 16px / 1.65 | 400 | Default body |
| `small` | 14px / 1.5 | 500 | Meta, pills, nav |
| `mono` | 14px / 1.5 | 500 | Code, checksums — `ui-monospace, "SF Mono", Consolas, monospace` |

Measure capped at ~68ch on body copy.

## Spacing

8px base scale: `4 8 12 16 24 32 48 64 96 128`. Section vertical padding is
`96px` desktop / `56px` mobile. Content max-width `1120px`, with a `20px`
side gutter under 1160px viewport.

## Shape & depth

- Radius: `10px` (buttons, inputs, pills use `999px`), `16px` (cards),
  `20px` (large panels/hero art).
- Shadow: one, used sparingly — `0 20px 60px -20px rgba(0,163,255,.25)` for
  the primary CTA and hero art only. Flat elsewhere; depth comes from the
  `--line` border + background-tint steps, not shadows.
- One hairline border (`1px solid var(--line)`) is the default separator,
  not drop shadows between every section.

## Components

- **Button / primary**: `--accent` background, `#06121F` text (near-black,
  not pure white, for contrast on bright blue), `10px` radius, 12/20px
  padding, 700 weight. Hover: brightens to `#2BB4FF` + the glow shadow.
  Focus: 2px `--accent` outline, 2px offset. Disabled: 40% opacity, no
  hover.
- **Button / secondary**: transparent, `1px solid var(--line)`, `--text`.
  Hover: border → `--accent`, background → `--bg-raised`.
- **Pill / tag**: `999px` radius, `1px solid var(--line)`, `--text-dim`,
  13px, used for spec badges ("Debian Bookworm", "GNOME Wayland").
- **Card**: `--bg-raised` background, `1px solid var(--line)`, `16px`
  radius, `28px` padding. No shadow by default.
- **Nav**: sticky, `--bg` at 88% opacity + `backdrop-filter: blur(10px)`,
  bottom hairline. Active section link gets `--accent` underline, not a
  pill/background (keeps it quiet).
- **Code/checksum block**: `--bg-raised-2`, `mono` token, `1px solid
  --line-soft`, copy-to-clipboard button inline.
- **Footer**: `--bg`, `--text-faint` body, single hairline top border, no
  second dark band.

## Imagery

One real asset family: the ten Aether wallpapers (`cosmos-*`, `prism-*`)
and the `aether-logo.svg` mark — no stock photography, no AI-generated
hero art, no generic "person at laptop" imagery. The hero uses a cropped,
darkened wallpaper (`cosmos-nebula.jpg`) as an ambient background behind a
glass panel, never as a literal screenshot claim. Feature icons are small
inline SVGs in `--accent`/`--text-dim` (two-tone, 20–24px), not emoji and
not a mismatched third-party icon pack.

## What to avoid

Purple→blue gradient text, glassmorphism on every card, three identical
feature cards with no visual hierarchy, emoji bullets, a hero that's just
centered text on a flat color with no product presence, badge/pill clutter,
and claiming OS-native app screenshots that don't exist yet (use honest
descriptions instead, per `RELEASING.md`'s "what the bundles are/aren't").
