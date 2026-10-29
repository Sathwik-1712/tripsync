# TRIPSYNC Design Guide

This guide defines how TRIPSYNC looks and feels. It takes its mood from the olive-and-cream direction (Style A) but is our own system: use it as the rules for every screen, not as a copy of any reference shot.

---

## 1. Design idea

**"A calm field guide for trips."** TRIPSYNC does a lot of work behind the scenes (six agents, live data, replanning). The interface should feel quiet and trustworthy, like a well-made paper travel journal, so the plan is the hero and the AI is the helpful assistant.

Three principles guide every decision:

1. **The plan comes first.** The itinerary, budget, and bookings are the largest things on screen. Controls stay small and out of the way.
2. **Show the agents' work, briefly.** Users should see that the budget was checked and why something changed, in one sentence, never as logs.
3. **Soft, rounded, natural.** Earthy colors, generous curves, and plenty of breathing room. Nothing sharp, neon, or crowded.

---

## 2. Color

A warm, natural palette: a paper-like ground, deep forest ink for text and key actions, and one fresh lime accent used sparingly.

### Core palette

| Token | Hex | Use |
|---|---|---|
| `paper` | `#EFEDE2` | Page background |
| `surface` | `#F8F7F0` | Cards, sidebar, inputs |
| `surface-raised` | `#FFFFFF` | Cards that sit on top of other cards (tickets, popovers) |
| `ink` | `#1F2A1C` | Main text, primary dark buttons, active nav |
| `ink-muted` | `#545B4A` | Secondary text, labels, meta info |
| `line` | `#E3E0D2` | Dividers, track behind progress bars |
| `lime` | `#C2CB52` | Accent: the one main action per screen, selected day, highlights |
| `lime-soft` | `#E6EAC9` | Tags, agent panel background, subtle highlights |
| `sage` | `#D8E5D6` | Large feature panels (stay card body) |
| `butter` | `#F5F1B0` | Detail strips on tickets (seat, fare, operator) |

### Status colors

| Token | Hex | Use |
|---|---|---|
| `success` | `#2F5D20` | "Done", "Within budget", "Passed" |
| `warning` | `#8A5A00` on `#FBEFD3` | "Close to limit", weather changes |
| `danger` | `#9B2C1F` on `#F8DED8` | "Over budget", failed checks |
| `info` | `#2D4F6B` on `#DCE8F0` | Tips, neutral notices |

### Color rules

- **One lime element per area.** Lime is for the single most important action (Export, Confirm) or the current selection. If everything is lime, nothing stands out.
- **Text on lime is always `ink`**, never white (white fails contrast).
- **Dark `ink` panels** are reserved for agent messages (Critic notes, replanning). This makes AI explanations instantly recognizable.
- **Never rely on color alone.** Status always comes with a word ("Over budget") or an icon.
- All text must meet **4.5:1 contrast** (3:1 for text 24px and up). `ink-muted` on `surface` passes; don't go lighter.

---

## 3. Typography

**Font:** [Outfit](https://fonts.google.com/specimen/Outfit) (free, Google Fonts). Rounded geometric shapes match the soft UI. Fallback: `system-ui, sans-serif`.

For prices and times, use Outfit's tabular numbers (`font-variant-numeric: tabular-nums`) so columns of rupees line up.

| Style | Size / Line height | Weight | Use |
|---|---|---|---|
| Display | 40 / 44 | 600 | Trip title ("Coorg, 4 days") |
| H1 | 32 / 38 | 600 | Page titles |
| H2 | 24 / 30 | 600 | Card titles ("Day 1 · Arrive and settle in") |
| H3 | 18 / 24 | 500 | Item titles in lists |
| Body | 16 / 24 | 400 | Default text |
| Small | 14 / 20 | 400 | Meta info (duration, distance) |
| Label | 12 / 16 | 600, uppercase, +1px tracking | Section labels ("AGENTS", "SEATS") |
| Price | 28 / 32 | 600 | Key amounts |

Rules: sentence case for headings and buttons. Use the rupee sign with Indian digit grouping (₹1,50,000). Don't use more than three sizes in one card.

---

## 4. Shape, spacing, and depth

### Radius (the signature of the look)

| Token | Value | Use |
|---|---|---|
| `radius-pill` | `999px` | Buttons, chips, tags, day pills, nav items |
| `radius-xl` | `28px` | Main cards |
| `radius-lg` | `20px` | Nested cards, agent panel |
| `radius-md` | `14px` | Inputs, small thumbnails |
| `radius-full` | `50%` | Icon buttons, avatars |

Cards inside cards use a smaller radius than their parent.

### Spacing

Base unit **4px**. Common steps: 4, 8, 12, 16, 20, 24, 32, 48.

- Card padding: **24px** (28px for large feature cards)
- Gap between cards: **20–24px**
- Gap between chips: **8–10px**
- Page margin on laptop: **24px**

### Depth

Mostly **flat**: depth comes from layered background colors (`paper` → `surface` → `surface-raised`), not heavy shadows. If a shadow is needed (popovers, modals only):
`0 8px 24px rgba(31, 42, 28, 0.08)`

---

## 5. Layout

### Laptop (1280–1440px, the main target)

```
┌──────────┬────────────────────────────────────────────┐
│          │  Header: back · trip title · view toggle   │
│ Sidebar  ├───────────────────────────┬────────────────┤
│ (nav +   │  Main column (≈ 2/3)      │ Side column    │
│  agent   │  Stay feature card        │ (≈ 1/3)        │
│  status) │  Day picker               │ Ticket card    │
│          │  Day timeline             │ Budget card    │
│          │                           │ Critic note    │
│          │                           │ Primary action │
└──────────┴───────────────────────────┴────────────────┘
```

- Sidebar about **220px**, content max width **1392px**, centered.
- Main column holds what users read (itinerary). Side column holds what they check (cost, tickets, agent notes).

### Tablet and phone

- Below ~1000px: side column drops under the main column.
- Below ~700px: sidebar becomes a bottom tab bar (Plan, Trips, Saved, Profile); cards go full width; day picker scrolls sideways.
- Touch targets at least **44 × 44px** everywhere.

---

## 6. Components

### Buttons

| Type | Look | When |
|---|---|---|
| Primary | `lime` fill, `ink` text, pill, 56px tall | One per screen: Export itinerary, Confirm plan |
| Dark | `ink` fill, `surface` text, pill | Active state, strong secondary action |
| Soft | `surface` fill, `ink` text, pill | Edit trip, filters, secondary actions |
| Icon | 48–52px circle, `surface` fill | Back, save, share. Always has an `aria-label` |

States: hover darkens fill by ~6%; focus shows a 2px `ink` outline with 2px offset; disabled is 40% opacity with no pointer.

### Chips and tags

- **Info chip:** `surface` pill with icon + short text ("2 km to town", "2 guests").
- **Category tag:** `lime-soft` pill, 13px text ("Transport", "Stay", "Activity").
- **Filter chip:** soft pill; selected = `ink` fill.

### Day picker

Row of pills showing weekday (small) over "Day N" (bold). Selected day uses `lime`. Scrolls horizontally on small screens.

### Timeline item

Time on the left (fixed width, bold), title + meta in the middle, category tag on the right. Thin `line` divider between items. No icons needed; the tag carries the category.

### Ticket card (transport)

Our own take on a boarding pass:
- A narrow accent strip on the left with the mode written vertically (BUS / TRAIN / FLIGHT) and a mode icon.
- Main area: origin and destination codes large, times and dates below.
- A `butter` strip at the bottom for small details (seats, operator, fare).
- Sits on `surface-raised` (white) so it reads as a "document".

### Feature card (stay / destination)

Large image on top (about 260px tall on laptop) with name and short label overlaid bottom-left in white. A circular save button can overlap the image edge. Below, on `sage`, a row of info chips and the price.

### Budget card

- Total at top: spent large, limit small ("₹11,950 of ₹15,000").
- One row per category: label, "spent / allocated", and a 10px pill-shaped bar.
- Bar fill is `ink`; turns `warning` above 90% and `danger` above 100%, always with text.

### Agent panel (sidebar)

`lime-soft` box listing each agent with a one-word status (Waiting, Working, Done, Passed, Replanned). While planning, the active agent shows a small spinner and "Working".

### Critic note

`ink` card with a small icon, a bold one-line headline ("Critic replanned once") and one plain sentence explaining why. Max two lines. This is the only place AI reasoning is shown by default; a "Details" link can open the full trace.

### Inputs (trip form)

`surface` background, `radius-md`, 48px tall, visible label above (never placeholder-only). Budget input shows the ₹ prefix.

---

## 7. Imagery and icons

- **Photos:** natural landscapes and places, warm daylight, real locations only (free sources: Wikimedia Commons, Unsplash). Always crop to fill (`object-fit: cover`) with rounded corners.
- **Text on photos:** only at the bottom, white, with a subtle dark gradient behind it for contrast.
- **No photo available:** use a simple flat illustration of layered hills in palette greens, never a broken image.
- **Icons:** outline style, 2px stroke, rounded ends, 20–24px. Recommended free set: [Lucide](https://lucide.dev). No emoji in the UI.

---

## 8. Voice and microcopy

- Friendly, short, plain: "Your Coorg plan is ready." not "Itinerary generation completed successfully."
- Explain agent decisions in one sentence with a reason: "Rain is expected on Day 2, so Abbey Falls moved to Day 3."
- Label estimates honestly: "Estimated fare", "Typical price".
- Loading states describe progress: "Checking budget…", "Finding stays…", "Reviewing the plan…".
- Errors say what to do next: "We couldn't find stays under ₹1,500. Raise the stay budget or try a nearby town?"

---

## 9. Motion

- Subtle and quick: 150–200ms ease-out for hovers, 250ms for cards appearing.
- While agents work, fade in each result card as it arrives instead of showing one long spinner.
- Respect `prefers-reduced-motion`: turn off non-essential animation.

---

## 10. Accessibility checklist

- [ ] All text meets contrast targets (section 2)
- [ ] Every icon-only button has an `aria-label`
- [ ] Visible focus outline on everything clickable
- [ ] Real `<button>` and `<a>` elements, never clickable `<div>`s
- [ ] Inputs have visible labels
- [ ] Status shown with words, not just color
- [ ] Works with keyboard only (Tab through the whole trip page)

---

## 11. Implementation tokens

### CSS variables

```css
:root {
  --paper: #EFEDE2;
  --surface: #F8F7F0;
  --surface-raised: #FFFFFF;
  --ink: #1F2A1C;
  --ink-muted: #545B4A;
  --line: #E3E0D2;
  --lime: #C2CB52;
  --lime-soft: #E6EAC9;
  --sage: #D8E5D6;
  --butter: #F5F1B0;

  --success: #2F5D20;
  --warning: #8A5A00;
  --warning-bg: #FBEFD3;
  --danger: #9B2C1F;
  --danger-bg: #F8DED8;

  --radius-pill: 999px;
  --radius-xl: 28px;
  --radius-lg: 20px;
  --radius-md: 14px;

  --font: "Outfit", system-ui, sans-serif;
}
```

### Tailwind config (if using React + Tailwind)

```js
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        paper: "#EFEDE2",
        surface: { DEFAULT: "#F8F7F0", raised: "#FFFFFF" },
        ink: { DEFAULT: "#1F2A1C", muted: "#545B4A" },
        line: "#E3E0D2",
        lime: { DEFAULT: "#C2CB52", soft: "#E6EAC9" },
        sage: "#D8E5D6",
        butter: "#F5F1B0",
        success: "#2F5D20",
        warning: { DEFAULT: "#8A5A00", bg: "#FBEFD3" },
        danger: { DEFAULT: "#9B2C1F", bg: "#F8DED8" },
      },
      borderRadius: { xl2: "28px", lg2: "20px", md2: "14px" },
      fontFamily: { sans: ["Outfit", "system-ui", "sans-serif"] },
    },
  },
};
```

---

## 12. Do and don't

| Do | Don't |
|---|---|
| One lime action per area | Lime buttons everywhere |
| Rounded pills and 28px cards | Sharp corners or mixed radius styles |
| Short, reasoned agent notes | Raw agent logs or JSON on screen |
| Real place photos or hill illustrations | Generic stock images, emoji, gradients |
| Layered background colors for depth | Heavy drop shadows |
| Honest "estimated" labels on prices | Showing estimates as exact booking prices |
