# Universal Enterprise UI Standard (UEUIS)

**Version:** 1.8  
**Updated:** 5 November 2026  
**Status:** Project-defined UI engineering playbook, **derived from and mapped to** international standards (ISO 9241 series, ISO/IEC 25010, ISO/IEC 40500 / W3C WCAG, ISO/IEC 30071-1, ISO 24495-1, EN 301 549). It is **not itself** an ISO standard. Claim conformance against the cited standards, never against this document alone.  
**Companion to:** `UNIVERSAL_AI_SOFTWARE_ENGINEERING_STANDARD.md` (UAISES). UAISES §10 says *what* good UI needs. This document says *how much*, *how to prove it*, and *which standard requires it*.  
**Purpose:** A reusable, framework-agnostic standard for Claude Code and other coding agents to design, build, audit and release enterprise-grade user interfaces (web, desktop, mobile, embedded web views) that pass accessibility audits, procurement reviews and usability evaluation.

> **Instruction to coding agent:** Treat this document as the UI playbook for the project. Apply the **Core** level to every UI. Apply **Enterprise** to any UI used by customers, staff or the public. Apply **Regulated** only when the domain requires it (health, finance, government, safety). Higher-priority instructions and existing design systems win where they conflict. Do not claim a check was run when it was not: mark it **UNVERIFIED**. ISO texts are copyrighted and paid; clause references here are paraphrased summaries, so read the official text before making a formal conformance claim.

### Conformance levels

| Level | Who needs it | Meets |
|---|---|---|
| **Core** | Every UI, including internal tools and prototypes that will ship | WCAG 2.2 Level A, the ISO 9241-110 interaction principles, every state in §6 |
| **Enterprise** | Customer, staff or public-facing products; anything sold or procured | Core + WCAG 2.2 Level AA (covers ISO/IEC 40500 and EN 301 549 web clauses), §§7–15 fully, a usability evaluation (§16) |
| **Regulated** | Medical, financial, government, safety-critical | Enterprise + domain law and standards (e.g. IEC 62366-1 usability engineering for medical devices, Section 508, the European Accessibility Act), formal evaluation reports in ISO/IEC 25066 format |

**Keyword convention:** **MUST** = required at that level; **SHOULD** = required unless a recorded reason says otherwise (§19 `DECISIONS.md`); **MAY** = optional.

## 0. Start Here: Working Contract

1. Identify the users, their tasks, their environment and their abilities before choosing visuals (ISO 9241-210 §6–7, ISO 9241-11). "Users" includes people using screen readers, keyboards only, magnification, voice control, high contrast and reduced motion.
2. Use the project's existing design system if there is one. Do not invent a parallel set of colours, spacing or components.
3. Define observable UI acceptance criteria per journey: **Given** state, **when** the user acts, **then** a visible and announced result follows.
4. Build every screen in all of its states (§6), in both themes (§8), at every target size (§9), by keyboard (§10.2), before calling it done.
5. Verify with tools **and** with real interaction: automated accessibility checks find roughly a third of WCAG problems at best; the rest needs manual keyboard, screen-reader and zoom passes.
6. Never ship a control that does nothing, a number that is not real, or a status that is not true (UAISES §4).
7. Report what was verified, how, and what remains UNVERIFIED (§22).

## 1. Interaction Principles (ISO 9241-110:2020)

**Goal:** The UI behaves the way users need, not the way the code happens to be structured. Every screen MUST satisfy all seven principles:

| Principle | Requirement | Typical failure |
|---|---|---|
| **Suitability for the user's tasks** | The UI presents what the task needs and nothing that gets in its way. Defaults are the most common correct choice. | Making users re-enter data the system already has |
| **Self-descriptiveness** | At every moment the user can tell where they are, what they can do and what just happened. | A spinner with no label; a button whose effect is unclear |
| **Conformity with user expectations** | It follows platform conventions and stays consistent within itself: same word, same icon, same place, same behaviour. | "Save" in one form, "Submit" in another, for the same action |
| **Learnability** | First use is guided; patterns repeat so that learning one screen teaches the next. | Hidden gestures with no visible affordance |
| **Controllability** | The user sets the pace and order, can pause, cancel, go back and undo. | A process with no cancel; auto-advancing carousels |
| **Use error robustness** | It prevents errors, makes them easy to see and easy to recover from, without losing work. | Clearing a whole form on one validation error |
| **User engagement** | It is trustworthy and pleasant to use: honest, respectful and motivating, never manipulative. | Dark patterns (§12.3) |

**Measure:** a principle-by-principle review of each primary journey, with findings recorded by principle.

## 2. Presentation of Information (ISO 9241-112:2017, ISO 9241-125:2017)

Information MUST be:

- **Detectable**: what matters is noticed. Use position, size and contrast before colour or motion.
- **Free from distraction**: no competing animation, decoration or redundant text near the task.
- **Discriminable**: things that differ look different; things that are the same look the same.
- **Interpretable**: plain words, units always shown, abbreviations explained once, numbers formatted for the locale.
- **Concise**: the shortest wording and display that stays accurate.
- **Consistent**: one term per concept across the product, help text and documentation.

Additional rules:

- Visual hierarchy: one primary action per view, and it is visually primary. Destructive actions are never the default.
- Group related items by proximity and alignment before adding borders or boxes.
- Tables: header row and column semantics, units in headers, right-aligned numbers, consistent decimals, sortable where users compare.
- Data visualisation: every chart has a title, axes with units, a legend or direct labels, a text or table alternative, and never relies on colour alone (WCAG 1.4.1).
- Truthful display: stale data is labelled with its age; estimates are labelled as estimates; empty means "none", not "unknown".

## 3. Content and Language (ISO 24495-1:2023 Plain language)

- Write for the reader's goal: they find what they need, understand it and can act on it.
- Use active voice, short sentences, common words; define unavoidable jargon on first use.
- Button labels are verbs that say the outcome ("Delete 3 files", not "OK").
- Error messages say what happened, why, and how to fix it, in that order, without blaming the user (WCAG 3.3.1, 3.3.3).
- Confirmation dialogs name the object and the consequence ("Delete project *Atlas*? This removes 42 files and cannot be undone.").
- Dates use ISO 8601 for storage and exchange, and locale format for display. Show the time zone whenever times cross zones.
- Never truncate meaning: if text is truncated, the full text is available (tooltip that is also keyboard and screen-reader reachable, or expandable).
- Tone is consistent and documented in a content guide (§19).

## 4. Forms and Data Entry (ISO 9241-143:2012, WCAG 2.2 §3.3)

- Every field has a visible, persistent label (placeholders are not labels) programmatically tied to the input (WCAG 1.3.1, 3.3.2, 4.1.2).
- Mark required **or** optional fields consistently, in text, not only with colour or an asterisk without a legend.
- Use the correct input type and `autocomplete` tokens for personal data (WCAG 1.3.5).
- Validate as the user leaves a field or on submit, not on every keystroke; never block typing.
- On submit with errors: keep all entered data, show an error summary linked to each field, move focus to the summary, and mark each field (`aria-invalid`, `aria-describedby`).
- Do not ask for the same information twice in one process (WCAG 3.3.7 Redundant Entry).
- Legal, financial or data-deleting submissions are reversible, checked, or confirmed (WCAG 3.3.4).
- Authentication does not require a cognitive function test such as remembering or transcribing; allow paste and password managers (WCAG 3.3.8).
- Long forms are split into steps with a visible progress indicator and the ability to go back without losing data.
- Format hints ("DD/MM/YYYY") are shown before input, and inputs accept common variants.

## 5. Visual User-Interface Elements (ISO 9241-161:2016)

- Each control type has one look and one behaviour across the product: buttons, links, toggles, checkboxes, radios, selects, tabs, menus, dialogs, toasts, tooltips.
- **Links navigate; buttons act.** Never style one as the other without the correct semantics.
- Toggles take effect immediately; checkboxes take effect on submit. Do not mix the two meanings.
- Disabled controls explain why they are disabled, or are replaced by an enabled control that explains the requirement when used.
- Icons have text labels, or an accessible name plus a visible tooltip; icon meaning is consistent (ISO/IEC 11581-10 for icon design processes).
- Modal dialogs: trap focus inside, return focus to the opener on close, close with Esc, have a visible title.
- Toasts and notifications: do not hold critical information or the only copy of an action; long enough to read (or user-dismissed); announced via a live region (WCAG 4.1.3).
- Tooltips are supplementary, dismissible with Esc, hoverable, and persistent while hovered (WCAG 1.4.13).

## 6. Complete UI States

Every view and component MUST define, build and test each state that can occur:

| State | Requirement |
|---|---|
| **Loading** | Skeleton or labelled progress; announced to assistive tech; long operations show progress and allow cancel |
| **Empty** | Says why it is empty and what to do next ("No invoices yet. Create one.") |
| **Partial** | Shows what loaded and clearly marks what did not |
| **Error** | Plain-language cause and recovery action; retry where retrying can work; no raw stack traces |
| **Offline / disconnected** | Says so; keeps user work; retries or queues where safe |
| **Stale** | Shows the data's age when freshness matters |
| **Permission denied** | Says who can grant access and how; never a blank page |
| **Success** | Confirms what happened, with undo where feasible |
| **In progress / busy** | Prevents double submission without freezing the whole UI |
| **Overflow** | Long names, many items, large numbers, RTL and long translations do not break layout |
| **First run** | Guidance that can be skipped and found again |

**Measure:** a state inventory per screen in `docs/UI_STATES.md`, each state reachable in a test or story.

## 7. Accessibility (ISO/IEC 40500, WCAG 2.2, ISO 9241-171, ISO 9241-20, EN 301 549)

**Goal:** Everyone can perceive, operate, understand and use the product with their own tools. Enterprise level = **WCAG 2.2 AA**, which meets ISO/IEC 40500:2012 (WCAG 2.0 AA) and the web clauses of EN 301 549, and is the usual procurement requirement (US Section 508, EU European Accessibility Act, UK and Indian public-sector rules).

### 7.1 Perceivable
- Text alternatives for meaningful images, icons and charts; decorative images hidden from assistive tech (1.1.1).
- Captions and transcripts for media (1.2.x).
- Semantic structure: headings in order, landmarks, lists, tables with headers, reading order equals visual order (1.3.1, 1.3.2).
- No information by colour alone (1.4.1).
- Contrast: **4.5:1** normal text, **3:1** large text (≥24 px, or ≥18.66 px bold), **3:1** for UI component boundaries, focus indicators and meaningful graphics (1.4.3, 1.4.11).
- Text resizes to 200% without loss (1.4.4); content reflows at **320 CSS px** width with no two-direction scrolling (1.4.10).
- User text-spacing overrides do not break content (1.4.12).

### 7.2 Operable
- Everything works by keyboard, with no keyboard trap (2.1.1, 2.1.2). Single-key shortcuts can be turned off or remapped (2.1.4).
- Users can extend or turn off time limits (2.2.1); moving or auto-updating content can be paused (2.2.2).
- Nothing flashes more than three times per second (2.3.1; ISO 9241-391 for photosensitive seizure risk).
- Skip links, descriptive page titles, logical focus order, link purpose clear from text (2.4.1–2.4.4).
- Focus is always visible (2.4.7) and not hidden behind sticky headers or overlays (2.4.11).
- Pointer: no path-based gestures without a single-pointer alternative (2.5.1); actions fire on up-event (2.5.2); visible label is part of the accessible name (2.5.3); dragging has a non-drag alternative (2.5.7).
- Target size at least **24×24 CSS px** (2.5.8); SHOULD be **44×44** for touch-first UIs.

### 7.3 Understandable
- Page language set, and changes of language marked (3.1.1, 3.1.2).
- Focus or input never causes an unexpected change of context (3.2.1, 3.2.2).
- Navigation and identification are consistent (3.2.3, 3.2.4); help is in the same place on every page (3.2.6).
- Form rules in §4.

### 7.4 Robust
- Valid, semantic markup; native elements before ARIA; ARIA only following the WAI-ARIA Authoring Practices.
- Every control exposes name, role, value and state (4.1.2).
- Status messages announced without moving focus (4.1.3).

### 7.5 Beyond the web (ISO 9241-171, ISO 9241-20)
- Desktop and mobile apps expose the platform accessibility API (UI Automation on Windows, NSAccessibility/UIAccessibility on Apple, AccessibilityNodeInfo on Android).
- Respect system settings: text size, high contrast / forced colours, reduced motion, reduced transparency, dark mode, caption preferences.
- Do not override user-chosen fonts, colours or cursor size without a way back.

### 7.6 Process (ISO/IEC 30071-1:2019)
- Accessibility requirements are written at the start, owned by named roles, tested in every release and recorded in an **accessibility conformance report** (e.g. VPAT® / ACR in the EN 301 549 or WCAG edition) for Enterprise products.
- Publish an accessibility statement with known limitations and a contact route.

**Measure:** automated scan with zero serious/critical violations; a manual keyboard pass; a screen-reader pass (NVDA or JAWS on Windows, VoiceOver on Apple, TalkBack on Android) of each primary journey; zoom 200% and 320 px reflow checks; forced-colours check.

## 8. Visual Design System: Colour, Typography, Formats and Theming

**Goal:** A product that looks deliberate, branded and easy to scan, not plain, and stays accessible. Colour, type and shape carry meaning (hierarchy, status, grouping), so a user can tell at a glance what matters, what is good and what needs attention. Decoration that carries no meaning is kept to the brand areas. (ISO 9241-112 detectability and discriminability, ISO 9241-125 visual presentation, ISO 9241-161 UI elements, WCAG 1.4.1, 1.4.3, 1.4.11.)

### 8.1 Design tokens (MUST)
- Every colour, font, size, spacing, radius, shadow, motion and z-index value is a named **token**. Components use tokens only, never literals.
- Three token tiers: **primitive** (`indigo-600 = #4338ca`), **semantic** (`--accent`, `--success-text`), **component** (`--button-bg`). Themes change only the semantic tier.
- Tokens live in one file and are checked automatically for contrast (§8.10).

### 8.2 Colour roles (MUST)
Each product defines these roles, for **every** theme:

| Role | Tokens | Used for | Contrast rule |
|---|---|---|---|
| **Brand** | `brand` (solid), `on-brand` | Logo mark, primary emphasis | `on-brand` ≥ 4.5:1 on `brand` |
| **Accent / primary** | `accent`, `accent-text` (text on accent), `accent-subtle` | Primary buttons, links, selected tabs, focus ring | `accent` ≥ 4.5:1 as text on surfaces; `accent-text` ≥ 4.5:1 on `accent` |
| **Success** | `success`, `success-subtle` | Met, passed, done, high match | text ≥ 4.5:1 on its subtle tint and on surfaces |
| **Warning** | `warning`, `warning-subtle` | Partial, at risk, medium match | same |
| **Danger** | `danger`, `danger-subtle` | Failed, destructive actions, errors | same |
| **Info** | `info`, `info-subtle` | Neutral notices, in progress | same |
| **Neutral** | `text`, `muted`, `border`, `ctl` | Body text, secondary text, dividers, control outlines | `text`, `muted` ≥ 4.5:1; `ctl` ≥ 3:1 |
| **Surfaces** | `bg` (page), `panel` (raised), `sunken` (inputs, code, logs), `overlay` | Layering | Each step visibly different from the next; text rules hold on all |

- **Status colour is never alone**: pair it with an icon and a word (✓ Passed, ⚠ At risk, ✕ Failed) (WCAG 1.4.1).
- One meaning per colour across the product: green is never used for a destructive action, red never for success.
- Limit the palette in a view: neutrals + one accent + the semantic colours in use.
- No decorative gradients (§8.17); solid colours only.

### 8.3 Data-visualisation colour (MUST for charts and scores)
- **Categorical**: up to 8 colour-blind-safe hues in a fixed order (e.g. the Okabe–Ito set); beyond 8, group into "Other".
- **Sequential** (one hue, light → dark) for magnitude; **diverging** (two hues around a neutral midpoint) for above/below a target.
- **Score bands**: a fixed mapping used everywhere, e.g. ≥ 70 % success, 40–69 % warning, < 40 % neutral or danger, always with the number shown.
- Each chart's colours meet 3:1 against its background (WCAG 1.4.11) and keep their meaning in both themes.

### 8.4 Typography (MUST)
- One UI type family (system stack by default: `"Segoe UI Variable", "Segoe UI", system-ui, -apple-system, Roboto, sans-serif`), one monospace family for code, IDs, paths and logs.
- A modular scale, e.g. **12 · 13 · 14 · 15 · 16 · 20 · 24 · 30 px**; body 16 px for reading-heavy services, 14–15 px for dense enterprise tools; line height 1.5 for body, 1.2–1.3 for headings.
- Weights: 400 body, 600 labels and emphasis, 700 headings. No more than three sizes in one card.
- Numbers in tables, scores and meters use **tabular figures** (`font-variant-numeric: tabular-nums`) so columns align.
- Line length 45–90 characters for reading text; headings in sentence case; no all-caps paragraphs (short all-caps eyebrow labels with letter-spacing are fine).

### 8.5 Spacing, shape and elevation (MUST)
- Spacing scale on a 4 px grid: **4 · 8 · 12 · 16 · 24 · 32 · 48 · 64**. Related items close, unrelated items far (proximity before borders).
- Radius scale: **4** (chips, inputs inner), **8** (buttons, inputs), **12–16** (cards, panels), **pill** (badges, segmented controls). One radius per component type.
- Elevation: **0** flat (page), **1** cards, **2** sticky bars and menus, **3** dialogs. Dark themes express elevation with lighter surfaces, not stronger shadows.
- Borders 1 px for dividers; 2–3 px only for focus and selected states.

### 8.6 Iconography (MUST)
- One icon set (e.g. Fluent, Lucide, Material Symbols), one stroke weight, sizes **16 / 20 / 24 px**, drawn in `currentColor` so they follow theme and status colour.
- Icons support text, they do not replace it: every icon-only control has an accessible name and a tooltip; decorative icons are hidden from assistive tech (`aria-hidden="true"`).
- Use icons where they speed up scanning: section headings, status, primary actions, empty states.

### 8.7 Standard formats (component patterns) (SHOULD; MUST at Enterprise)

| Format | Specification |
|---|---|
| **App bar / page header** | Solid header (48–64 px), logo mark + product name (+ optional one-line purpose, hideable §8.18); global controls (status, descriptions, theme, account, help) at the right |
| **Section heading** | Icon + title + optional count chip + optional action at the right |
| **KPI / stat tile** | Eyebrow label (12–14 px, muted), big value (24–36 px, tabular), unit, optional trend or status chip; 3–5 tiles per row, stacking on small screens |
| **Card** | `panel` surface, radius 12–16, elevation 1, 16–24 px padding; status cards carry a 4–6 px coloured left stripe in the status colour |
| **Badge / chip** | Pill; subtle tint background + strong text of the same role; icon or dot + word; never colour alone |
| **Alert / banner** | Icon + bold title + one-sentence body + action; `info`, `success`, `warning`, `danger` variants |
| **Button hierarchy** | One **primary** (filled accent) per view; **secondary** (outlined); **tertiary** (text); **danger** (outlined or filled danger); sizes S 32 px, M 40–44 px, L 48 px; icon left of label |
| **Tabs / segmented control** | Underline tabs for page sections or a pill segmented control for 2–4 options; selected state uses accent + weight, not colour alone |
| **Data table** | Sticky tinted header, row hover, optional zebra, numbers right-aligned in tabular figures, status as chips, a meter for percentages, actions in the last column |
| **Meter / progress** | Track + filled bar in the score-band colour, the value as text next to it |
| **Empty state** | Icon or small illustration, a title ("No builds yet"), one sentence, the next action as a button |
| **Log / console** | `sunken` surface, monospace 13–14 px, timestamps muted, errors in danger colour with an icon |
| **Form** | Labels above fields; fields grouped in titled cards; help text under the field; required marker explained once |

### 8.8 Data formats (MUST)

| Data | Display format |
|---|---|
| Numbers | Locale thousands separators (`12,480` / `12.480`); tabular figures in columns |
| Percentages | Integer unless precision matters (`91%`); same decimals within a column |
| Currency | ISO 4217 code or locale symbol, 2 decimals (`$2.41`, `₹199.00`) |
| Dates and times | Locale format for display, ISO 8601 for data and export; relative ("5 min ago") with the absolute time available |
| Durations | `2m 05s`, `1h 12m`; never raw seconds above 90 s |
| Sizes | Binary units with one decimal (`3.4 GB`) |
| Identifiers, paths, code | Monospace; long values wrap or truncate with full value available (§3) |
| Empty values | An em dash `—` with an accessible meaning ("not available"), never blank |

### 8.9 Themes (MUST)
- Light, dark and high-contrast / forced-colours are each **designed**: every theme gets the same visual quality and passes §8.10 on its own. A dark theme is not an inverted light theme.
- **Themes must be visibly different everywhere, including the chrome.** A brand-coloured header that stays the same in both themes makes light and dark look identical at a glance (the most common theming defect). Give the header, navigation and toolbars their own tokens per theme (e.g. a light tinted band in light, a deep band in dark) and keep the brand as an accent strip or logo.
- Follow the system theme by default; offer a visible override (System / Light / Dark) that is remembered and applied before first paint (no flash).
- Forced-colours mode: the UI stays usable with system colours; borders, focus and selected states remain visible.
- Motion tokens: 120 ms (micro), 200 ms (standard), 300 ms (panels), ease-out; all reduced or removed under `prefers-reduced-motion`.

### 8.10 Verification (MUST)
- An automated test computes contrast for every semantic token pair in every theme: text roles ≥ 4.5:1 on `bg`, `panel` and their subtle tints; `on-brand` on `brand`; `ctl`, focus and chart colours ≥ 3:1.
- Screenshots of key screens in every theme, at desktop and 320 px, are reviewed before release.
- A UI that is technically accessible but visually flat (no hierarchy, no status colour, no focal point) **fails** the Visual design gate (§20).

### 8.11 Rich and data-dense interfaces: dashboards, monitoring and workflow tools (MUST when the UI shows live data, scores or multi-step work)

These patterns are what make an interface feel "rich" without becoming noisy. Each one comes from a published, widely adopted standard or design system; follow the source for detail.

| Pattern | Requirement | Source standards |
|---|---|---|
| **System status strip** | A slim bar under the app bar that states what the product can do right now (services up, connections, authentication, background jobs) using icon + word + colour; each item links to where it is fixed | Nielsen heuristic 1 "visibility of system status"; ISO 9241-110 self-descriptiveness; Fluent 2 *MessageBar*; Carbon *Status indicator* pattern |
| **Live / freshness indicator** | Any value that updates shows its age ("updated 12 s ago") and, if polling, the next refresh; stale data turns amber with the word "stale" | ISO 9241-112 interpretability; ANSI/ISA-101.01 (HMI) data quality indication |
| **Score as a bullet graph or ring** | A single score shows the value, the target and the qualitative bands (e.g. build / borrow / fork / reuse), with the number in text. Prefer the **bullet graph** where space is tight or several scores are compared; a ring or gauge only for one headline score | Stephen Few, *Bullet Graph Design Specification* (2006/2013); IBCS (International Business Communication Standards); Material 3 *Progress indicators* |
| **KPI count tiles** | Counts by status (on target / partial / below / unknown) as tiles; the colour matches the status everywhere; each tile filters or links to its items | Carbon *Dashboard* and *Data visualization* guidance; Atlassian *Lozenge* colour semantics |
| **Distribution summary** | When a list is scored, show how many items fall in each band (a stacked bar or small histogram) with counts in text | IBCS notation (SUCCESS: "Express"/"Simplify"); Carbon *Simple bar / meter chart* |
| **Stepper / progress through a process** | Multi-step work shows its steps, the current step and completed steps, each with a label (not only numbers) | Material Design 2 *Steppers*; Carbon *Progress indicator*; Atlassian *Progress tracker*; GOV.UK *Task list* |
| **Skeleton loading** | While content loads, show grey placeholder shapes of the final layout (not a lone spinner); announce "Loading" once to assistive tech | Carbon *Skeleton states*; Fluent 2 *Skeleton*; Atlassian *Skeleton* |
| **Toast / snackbar** | Brief, non-blocking confirmation of a completed action ("Analysis saved"), auto-dismiss ≥ 5 s, pausable on hover/focus, never the only place critical information appears | Material 3 *Snackbar*; Fluent 2 *Toast*; WCAG 2.2.1, 4.1.3 |
| **Notification centre with count badge** | Repeated alerts are grouped with a count (×14), not repeated; severity drives order and colour; read/unread is visible | ANSI/ISA-18.2 and IEC 62682 (alarm management: prioritisation, flood suppression); Material 3 *Badges* |
| **Progressive disclosure / view modes** | Beginner / Advanced / Expert or "Show details" toggles reveal depth on demand; the choice is remembered | ISO 9241-110 suitability for the task and learnability; ISO 9241-129 individualisation; NN/g progressive disclosure |
| **Copy affordance** | IDs, paths, commands and URLs have a copy button that confirms "Copied" | Carbon *Code snippet*; GitHub Primer *Clipboard copy* |
| **Relative time with absolute on demand** | "5 min ago" in lists, the full local date-time on hover/focus and in exports | §8.8; Primer *Relative time*; Atlassian date guidelines |
| **Materials (glass / acrylic / mica)** | Translucent surfaces only for chrome (app bar, menus), never under body text unless contrast holds at every point; disabled under `prefers-reduced-transparency` and forced colours | Fluent 2 *Materials* (Acrylic, Mica); Apple HIG *Materials* |
| **Monitoring colour discipline** | In monitoring views, normal state is calm (neutral or green); strong colour is reserved for abnormal states, so problems stand out | ANSI/ISA-101.01 *High-Performance HMI*; ISO 11064-5 (control-centre displays) |
| **Charts** | Title, labelled axes with units, accessible name and a text/table alternative; tooltips reachable by keyboard; ≤ 8 categorical colours | WAI-ARIA Graphics module; Carbon and Material data-visualisation guidance; §8.3 |

### 8.12 Reference design systems (crosswalk)

UEUIS sets the rules; these public design systems show proven implementations. Use the one that matches the platform; for platform-neutral web tools, borrow patterns (not looks) from any of them.

| UEUIS format | Microsoft Fluent 2 | Google Material 3 | IBM Carbon | Apple HIG | Atlassian | GOV.UK |
|---|---|---|---|---|---|---|
| App bar / header | Nav, Toolbar | Top app bar | UI shell header | Toolbar | Top navigation | Header |
| Status strip / banner | MessageBar | (M2 Banner) | Notification (inline) | — | Section message | Notification banner |
| Badge / chip / status | Badge, Tag | Chips, Badges | Tag, Status indicator | — | Lozenge, Badge | Tag |
| KPI tile / card | Card | Cards | Tile | — | — | Summary card |
| Score / meter | ProgressBar | Progress indicators | Meter chart, Gauge | Gauges | Progress bar | — |
| Stepper | — | (M2 Steppers) | Progress indicator | — | Progress tracker | Task list |
| Skeleton | Skeleton | — | Skeleton states | — | Skeleton | — |
| Toast | Toast | Snackbar | Toast notification | — | Flag | — |
| Tabs / segmented | TabList | Tabs, Segmented buttons | Tabs, Content switcher | Segmented control | Tabs | Tabs |
| Data table | DataGrid | (M2 Data tables) | Data table | Lists and tables | Dynamic table | Table |
| Empty state | — | — | Empty states pattern | — | Empty state | — |
| Tokens | Fluent tokens | Material tokens | Carbon tokens | — | Design tokens | — |

Design tokens SHOULD be stored in the **W3C Design Tokens Community Group format** (`.tokens.json`) when they are shared across tools.

### 8.13 Product identity (MUST)

- Every product has **its own visual identity**: name, logo mark, brand colours, header layout and signature components. Reuse *patterns and rules* from this standard and from §8.12, never another product's look.
- Two products from the same owner MAY share tokens for spacing, type and semantic status colours, but MUST differ in brand colours, header and layout so users can tell at a glance which product they are in.
- Do not copy third-party brand assets, logos or trade dress (also §8 brand rules and trademark law).
- Record the identity in `docs/DESIGN_SYSTEM.md`: brand colours, logo, signature components, and which §8.11 patterns the product uses and why.

### 8.14 Professional polish checklist: the top 20 (MUST at Enterprise)

A UI can pass accessibility and still look unfinished. These 20 items are what reviewers, buyers and users notice first. Check every one before release; record any that do not apply in `docs/DECISIONS.md`.

| # | Item | Requirement | Source |
|---|---|---|---|
| 1 | **Themes look different, both look finished** | Light and dark differ in the *chrome* (header, navigation, toolbars), not only in content areas. A user glancing at a screenshot can tell which theme it is. Automated test: header luminance differs by ≥ 0.6 between themes. Both themes get equal care through structure, spacing, type and a restrained palette (§8.16–§8.17), never through gradients or glows | §8.9; Fluent 2 and Material 3 theming |
| 2 | **Theme switcher** | A visible System / Light / Dark segmented control (radio group with icons + text), remembered, applied before first paint | WAI-ARIA radio group pattern; Fluent, Material |
| 3 | **Calm status** | When everything is normal, show one summary ("All systems ready") with details on demand; problems are always shown expanded, in the danger colour | ANSI/ISA-101 high-performance HMI; Nielsen heuristic 1 |
| 4 | **Uncluttered header** | Header holds only identity, global navigation and global controls. Compliance badges, versions and legal text go to the footer | Material top app bar; Fluent header guidance |
| 5 | **Sticky navigation** | Primary tabs (and the stepper, if any) stay reachable while scrolling, gaining a divider/shadow once stuck; content anchors respect it (`scroll-padding-top`) | Carbon UI shell; Material |
| 6 | **Type hierarchy** | A display face for headings and big numbers, a text face for body, tight letter-spacing on large headings, tabular figures for numbers | §8.4; Apple HIG typography |
| 7 | **First-run state** | An empty screen explains what the product does and offers 2–3 one-click examples or a sample | Carbon empty states; Atlassian empty state |
| 8 | **Input guidance** | Long inputs show a live character counter (warning near the limit) and the keyboard shortcut to submit | ISO 9241-143; GOV.UK character count |
| 9 | **Busy buttons** | A button that starts work shows a spinner and a new label ("Analyzing…"), is disabled until done, and sets `aria-busy` | Fluent Spinner; Material; WCAG 4.1.3 |
| 10 | **Filter results** | Lists over ~10 items get a filter box with a live "Showing x of y" count and a keyboard shortcut (`/`) | Carbon data table toolbar; Primer |
| 11 | **Readable rows** | Long text clamps to 2–3 lines with a "Show more / Show less" button (`aria-expanded`), so rows stay scannable and nothing is lost | §3; Atlassian, Material |
| 12 | **Recognisable items** | Each row starts with a source icon or avatar; compound names show the secondary part muted (owner / **name**) | Material lists; Primer |
| 13 | **Human numbers and dates** | Compact numbers (1.4k), relative dates (3 d ago) with the exact value on hover/focus, licences/statuses as chips, accurate wording (e.g. "other license", not "no license", for an unrecognised licence) | §8.8; Primer relative time |
| 14 | **Lists as chips** | Short lists (tags, gaps, labels) render as chips, not comma-separated text; an empty list says something positive ("covers all") | Material chips; Carbon tags |
| 15 | **Next step on the result** | A verdict, score or summary offers its obvious next actions right there (Open, Build, Fix) — links for navigation, buttons for actions, never nested | ISO 9241-110 suitability for the task; WCAG 4.1.2 |
| 16 | **Mobile layout** | Below ~640 px, tables become stacked cards with each value labelled; secondary chrome (stepper, long labels) collapses | §9; Carbon, Material responsive tables |
| 17 | **Window identity** | A favicon in the brand colours, and a document title that reflects state ("Analyzing…", "Reuse: 91% Invoicer") | Platform conventions; WCAG 2.4.2 |
| 18 | **Print / export** | `@media print` produces a clean report: chrome hidden, cards unbroken, link URLs printed | ISO 9241-112; common enterprise requirement |
| 19 | **Footer** | Version, uptime or build info, keyboard shortcuts, compliance badges and support links live in the footer | Carbon UI shell footer; GOV.UK footer |
| 20 | **Depth and finish** | Hairline borders, one shadow scale, hover lift on interactive cards, consistent radii, the `hidden` attribute always wins (`[hidden] { display: none !important }`) | §8.5; Fluent elevation; Material elevation |

**Verification:** an automated test asserts items 1, 2, 9, 10, 11, 15 and 20 (token comparisons, element presence, no interactive nesting), and the release screenshots (§8.10) show each theme at desktop and phone width.

### 8.15 Button restraint (MUST)

Too many buttons is the second most common reason a UI looks amateur (after flat theming). Every visible button competes for attention.

- **One primary (filled) action per view.** Everything else is visibly quieter.
- **Action weight ladder:** primary (solid fill) → secondary (outlined) → tertiary (text button) → icon-only ghost button (with `aria-label` and tooltip). Choose the lightest weight that is still discoverable.
- **Make the content the control.** A row's title opens it (no separate "Open" button); a status summary toggles its own details (no separate "Details" button); an example is a text link, not a chip.
- **No duplicate actions** in one view: if the verdict offers "Build reusing it", the toolbar does not also offer "Build this app".
- **Per-row actions are icons** (copy, delete), shown with `aria-label`; destructive ones turn danger-coloured only on hover/focus and still confirm (§11).
- **Settings-like controls are compact**: a theme switcher is an icon segmented control, not three labelled buttons.
- **Verification:** an automated count of full-weight buttons on the start screen stays within a stated budget (e.g. ≤ 7), and a test forbids known duplicates.

| Before | After |
|---|---|
| "Open" + "Delete" buttons on every history row | Requirement text opens the row; trash icon deletes |
| "All systems ready" + "Details" button | The summary pill is the toggle (chevron) |
| Three outlined example chips | "Try: A · B · C" text links |
| "Build this app" in toolbar and "Build reusing it" on verdict | Only on the verdict |
| Labelled System / Light / Dark buttons | Icon segmented control with tooltips |
| "Copy" outlined buttons | Copy icon |


### 8.16 Theme palettes: one primary, restrained categorical colour (MUST at Enterprise)

Each theme gets its **own named palette**, built from solid colours. A palette is not a rainbow: it is neutrals, **one primary colour**, a small set of categorical colours used sparingly, and the status colours.

**Palette anatomy (per theme):**

| Token group | Count | Use |
|---|---|---|
| Neutrals: `bg`, `panel`, `sunken`, `border`, `text`, `muted`, `ctl` | 7 | 90 % of every screen. Light: near-white panels on a light grey page. Dark: graphite panels on a near-black page |
| Header: `header-bg`, `header-line`, `on-header` | 3 | A solid header that differs clearly between themes (luminance difference ≥ 0.6) |
| Primary: `accent`, `accent-hover`, `accent-text`, `accent-subtle` | 4 | The one primary action per view, selection, links and focus. Choose a distinctive hue; avoid the default blue band (200–260°) unless it is the brand colour |
| Categorical `c1..c5` | 5 + subtle each | Identity only (section icons, a 3 px tile marker, avatars, form-group icons). Never a status colour, never a large fill |
| Status: success, warning, danger, info | 4 + subtle each | Meaning only, the same roles in both themes |

**Rules:**
- **Different palettes per theme, same roles.** Example: light *Slate & Teal* (grey neutrals, teal primary, rust/raspberry/violet/teal/olive categories); dark *Graphite & Mint* (graphite neutrals, mint primary, orange/pink/lavender/aqua/lime categories).
- **Role split:** primary = "do / where"; categorical = "which thing"; status = "how is it". Never swap roles.
- **Contrast:** every text role ≥ 4.5:1 on `bg`, `panel`, `sunken` and its own subtle tint; `accent-text` ≥ 4.5:1 on `accent` and `accent-hover`; controls and data marks ≥ 3:1.
- **Name the palettes** in the token file and `docs/DESIGN_SYSTEM.md`.
- **Verification:** a test asserts the anatomy above, the hue rule, that categorical colours never equal status colours, and every contrast pair.

### 8.17 Enterprise visual restraint (MUST at Enterprise)

Enterprise software (Microsoft 365 and Azure portals, IBM Carbon, SAP Fiori, Atlassian, GitHub) looks trustworthy because it is **calm, solid and consistent**. Decoration that marketing sites use reads as unprofessional in a work tool.

| Do | Do not |
|---|---|
| Solid colours for every surface, header, button and badge | Gradients of any kind on surfaces, headers, buttons, text or borders |
| Text in `text` / `muted`; the product name in solid text | Gradient or multi-colour text, text shadows |
| Neutral, low shadows (one or two levels); borders do most of the separation | Coloured or glowing shadows, "glow" backgrounds, blobs, mesh gradients |
| A compact header (48–64 px): logo mark, product name, global controls | Hero bands, oversized headers, overlapping cards for effect |
| Underline tabs or a quiet segmented control; one filled primary button | Pill-shaped filled tabs, several filled buttons, gradient buttons |
| Colour in small meaningful places: status chips, a 3–4 px marker on tiles/banners, icons, charts | Tinted full-card backgrounds, coloured tiles, rainbow headings |
| Radii 4–8 px; 1 px borders; 13–15 px UI text in dense views | Large radii (≥ 14 px) everywhere, heavy borders, playful motion |
| Motion only for state changes (≤ 150 ms) | Hover lifts, bounces, parallax, shimmer effects |
| Glass / acrylic only where the platform does it natively (Windows Mica window chrome) | Glass or blur panels inside a web page |

**The one allowed exception:** gradients that *encode data* with hard stops, such as the qualitative bands of a bullet graph (§8.11). A test must allow only those.

**Verification:** an automated test fails the build if the stylesheet contains a `gradient(` outside data-visualisation rules, `background-clip: text`, `backdrop-filter`, glow tokens, or non-neutral shadow colours.

### 8.18 Descriptions switch (SHOULD; MUST for dense or expert tools)

Explanatory text helps first-time users and slows down experienced ones. Give users a switch.

- A labelled **switch** in the header ("Descriptions", `role="switch"`, `aria-checked`), remembered per user and applied before first paint (no flash).
- It hides **explanatory** text only: subtitles, hints, field help, method notes, first-run paragraphs and statement-style footers. It never hides data, values, labels, errors, warnings, status or required-field markers.
- Default: **hidden** for expert or repeat-use tools; **shown** for public or first-time-use services. Record the choice in `docs/DECISIONS.md`.
- Mark hideable text with one class (e.g. `.desc-only`, `.help`, `.hint`) so the rule is one selector; errors that reuse a hint class are excluded (`.hint:not(.err)`).
- **Verification:** a browser test toggles the switch, checks a description hides and shows, reloads, and checks the choice persisted.

### 8.19 Focused pages: room for the main input, secondary records on their own page (MUST)

- **The primary input gets the space.** If the product's job starts with free text (a requirement, a query, a message), that field is the largest element above the fold: about 8 rows / 160–200 px tall on a laptop, full content width.
- **Ask only for what is needed.** Remove optional inputs that most users leave empty (e.g. "extra keywords"); derive them from the main input instead. Every optional field must justify itself in `docs/DECISIONS.md`.
- **Secondary records live on their own page or tab** (history, saved items, logs, settings), not stacked under the primary task. Opening a record returns the user to the task page with that record loaded.
- **Page tabs sit at the top**, directly under the header and above every page's content, so every page (including secondary ones such as *Past requirements*) is visible from the first glance. Name tabs in the user's words ("Past requirements", not "History" if users think in requirements) and show a count badge where useful.
- **Do not duplicate navigation.** Numbered tabs already show the order of steps; a separate stepper is only needed when steps are not tabs.
- **Hide what the current page does not use** (e.g. the requirement editor on the History page).
- **Verification:** a browser test checks that the primary input is above the fold at 1366 × 768, that history is a separate tab or page, and counts the controls on the start screen against the button budget (§8.15).

## 9. Responsive and Multi-Device Layout

- Design for content breakpoints, not device names. Verify at least: 320, 375, 768, 1024, 1440 and 1920+ CSS px, and at 200% and 400% zoom.
- No horizontal page scroll except for content that is inherently two-dimensional (data tables, maps), which scrolls in its own region.
- Touch, mouse, pen, keyboard and voice all work; hover is never the only way to reveal an action.
- Respect safe areas, on-screen keyboards and orientation changes without losing state.
- High-DPI: vector icons or multiple raster densities; no blurry assets at 150–200% scaling.

### 9.1 Laptop density (MUST)

Most office users work on 13–15″ laptops: about **1280–1536 CSS px wide and 650–800 px tall** after browser chrome and 125–150 % scaling. Design for that first, then scale up.

- **Content width:** use the screen. Max content width **1440–1480 px**, side gutters **24 px** (16 px below 1024 px). A 1200 px cap wastes a fifth of a 1536 px laptop screen.
- **Above the fold at 1366 × 768:** the primary input and primary action, plus the first meaningful result, are visible without scrolling.
- **Vertical rhythm:** header ≤ 140 px (≤ 120 px when the viewport is under 900 px tall); card padding 16 × 24 px; gaps between sections 12–24 px, not 32–48; table cells 8 × 12 px.
- **Inputs:** multi-line inputs start at 3 rows and grow; long forms use two columns from 1280 px where the fields are short.
- **Empty live regions take no space** (`:empty { min-height: 0; margin: 0 }`) so status lines don't leave gaps.
- **The main input is frameless and full width.** Do not wrap the primary text field in a card with its own border and padding: the field is the surface. Side gutters 16 px at laptop widths (≤ 1600 px), and the field's height fills the free viewport height on the start screen (e.g. `height: max(200px, calc(100vh - <fixed chrome>))`), shrinking once results appear.
- **Watch for shrink-wrapped layouts.** When the page body is a flex column (for a sticky footer), centred wrappers with `margin: 0 auto` shrink to their content; give them `width: 100%` with a `max-width`. A browser test must assert the main input spans the viewport minus the gutters.
- **Verification:** screenshots at **1366 × 768** and **1536 × 864** in both themes are part of the release evidence (§8.10).

## 10. Navigation and Interaction Patterns

### 10.1 Information architecture
- Navigation depth and labels come from user tasks (card sort / tree test for Enterprise), not the org chart or the code modules.
- The current location is always visible (selected nav item, breadcrumbs, page title).
- Every state that can be shared or reloaded has a URL (web) or is restored on relaunch (desktop/mobile).
- Browser back button and platform back gesture behave as users expect.

### 10.2 Keyboard and focus
- Logical tab order; roving tabindex inside composite widgets (menus, tabs, grids) per WAI-ARIA Authoring Practices.
- Documented shortcuts for frequent actions in productivity apps; a shortcut help panel.
- Focus is moved deliberately on route change, dialog open/close and error summary, and never lost to `<body>`.

### 10.3 Search, filter and tables
- Search tolerates typos and partial matches where users expect it, and states its scope.
- Filters show what is applied, the result count, and a one-click clear.
- Large tables: pagination or virtualisation with an accessible row count, sticky headers, column visibility, export where users need it.

## 11. Feedback, Errors and Recovery (ISO 9241-110 use error robustness)

- Every user action gets feedback within **100 ms** (visual change), and long operations show progress within **1 s**.
- Prefer **undo** over confirmation for reversible actions; use confirmation only for irreversible or costly ones.
- Autosave or draft-preserve user input on navigation, timeout, crash and session expiry.
- Errors are specific, located at the cause, and include the recovery step; global errors include a reference ID for support.
- Never show raw exceptions, stack traces, SQL or internal paths to users (also UAISES §7).
- System-initiated changes (background sync, auto-fix, policy changes) are visible in an activity log with undo where possible.

## 12. Trust, Privacy and Ethical Design

### 12.1 Privacy (ISO/IEC 29100, GDPR / DPDP Act and local law)
- Consent is specific, informed, unbundled and as easy to withdraw as to give.
- Show what data is collected and why at the point of collection.
- Sensitive values (passwords, keys, IDs) are masked with an explicit reveal control.

### 12.2 Security UX
- Sign-in supports password managers, passkeys and MFA; session expiry warns before it happens and preserves work (WCAG 2.2.1, 2.2.5).
- Permissions and dangerous actions show *who* is acting, on *what*, with *what effect*.
- Clear indicators for environment (production vs test) in admin tools.

### 12.3 No dark patterns
The UI MUST NOT use: disguised ads, pre-checked consent, confirm-shaming, roach-motel cancellation, hidden costs, forced continuity, nagging, fake urgency or scarcity, trick questions, or visual interference that hides the user-preferred option. (Regulated in the EU Digital Services Act Art. 25, EU consumer law, US FTC guidance and India's CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023.)

### 12.4 Honest AI features
- Label AI-generated content and AI-taken actions as such.
- Show confidence or evidence where decisions depend on it; let users verify, correct and override.
- Keep a human-approval step for consequential AI actions, and log them (UAISES §11).

## 13. Internationalisation and Localisation

- All user-visible strings are externalised; no concatenated sentences; use ICU MessageFormat or equivalent for plurals and gender.
- Unicode (ISO/IEC 10646) end to end; language tags per BCP 47 / ISO 639; countries ISO 3166; currencies ISO 4217.
- Locale-aware dates, times, numbers, currency, sorting and names; time zones shown when relevant.
- Layout survives **+40%** text expansion and **right-to-left** mirroring (logical CSS properties).
- Icons, colours and images reviewed for cultural meaning in target markets.

## 14. Performance as User Experience

| Metric | Target (75th percentile, real users) | Source |
|---|---|---|
| Largest Contentful Paint | ≤ 2.5 s | Google Core Web Vitals (industry, not ISO) |
| Interaction to Next Paint | ≤ 200 ms | Google Core Web Vitals |
| Cumulative Layout Shift | ≤ 0.1 | Google Core Web Vitals |
| Desktop app cold start to usable | ≤ 2 s typical hardware | Project target; record actual |
| Input response | visual feedback ≤ 100 ms | Human response limits (Miller 1968; Nielsen) |

- Measure on the slowest supported hardware and network, not the developer's machine.
- No layout shift from late-loading fonts, images or ads; reserve space.
- Bundle budgets per route are enforced in CI.

## 15. Personalisation and Settings (ISO 9241-129:2010)

- Users can adjust what matters to them (density, theme, language, default views, notification level) without it breaking accessibility.
- Settings take effect visibly, are saved, can be reset to defaults and are exportable where enterprise admins need it.
- Admin-enforced policies are shown as such ("Set by your organisation"), not silently hidden.

## 16. Human-Centred Design Process and Usability Evaluation (ISO 9241-210:2019, ISO 9241-11:2018, ISO 9241-220:2019, ISO/IEC 25066:2016)

**Goal:** Usability is measured, not assumed. ISO 9241-11 defines it as **effectiveness, efficiency and satisfaction** for specified users, goals and context of use.

1. **Understand and specify the context of use**: users, tasks, equipment, physical and social environment (a short `docs/CONTEXT_OF_USE.md`).
2. **Specify user requirements**, including accessibility and measurable usability targets (e.g. "90% of first-time users complete invoice creation in under 3 minutes without help").
3. **Produce design solutions** iteratively: sketches → prototypes → product.
4. **Evaluate against requirements** with real or representative users; iterate until targets are met.

| Measure | How | Enterprise target (set per product) |
|---|---|---|
| Effectiveness | Task completion rate, errors | ≥ 90% completion on primary tasks |
| Efficiency | Time on task, clicks/steps | Meets the target in requirements |
| Satisfaction | SUS (System Usability Scale) or UMUX-Lite | SUS ≥ 68 (average); ≥ 80 for mature products |
| Accessibility | Completion by assistive-tech users | Parity with other users |

- Enterprise: at least 5 representative users per round for formative testing; include users with disabilities.
- Record results in the **ISO/IEC 25066 Common Industry Format** (context, method, results, findings); summative tests MAY use ISO/IEC 25062.
- Map findings to ISO/IEC 25010:2023 **interaction capability** sub-characteristics: appropriateness recognisability, learnability, operability, user error protection, user engagement, inclusivity, user assistance, self-descriptiveness.
- Heuristic review (e.g. against §1 principles) is a supplement, never a replacement, for testing with users.

## 17. Component Engineering and Testing

- Components are built once, in a shared library, documented with every state (§6), variant and theme, e.g. in Storybook or an equivalent catalogue.
- Each component has: semantic HTML/native control base, keyboard behaviour per WAI-ARIA APG, unit tests, an accessibility test, a visual regression snapshot per theme.
- Test pyramid for UI:
  - unit and component tests (logic, rendering, a11y via axe-core or platform equivalent);
  - end-to-end tests for every primary journey in a real browser or the real app (Playwright, WinAppDriver/Appium, XCUITest, Espresso);
  - visual regression for both themes and key breakpoints;
  - manual assistive-technology passes before release.
- **UI coverage:** every render target, control and interactive element is reached by at least one automated interaction test; conditional ones are listed with a reason (no silent exclusions).
- Tests assert behaviour and accessible names, not CSS class names or pixel positions.
- No console errors or unhandled promise rejections in any journey.

## 18. Required UI Delivery Workflow

### Phase A — Discover
Context of use, user tasks, existing design system, platforms, accessibility level, locales, and the UAISES requirements for the feature.

### Phase B — Specify
Journeys with Given/When/Then criteria; the state inventory (§6); usability targets (§16); content needs (§3).

### Phase C — Design
Information architecture, wireframes, then high-fidelity in every theme; token changes recorded; accessibility annotations (headings, landmarks, focus order, names) on the design.

### Phase D — Implement
Components first, then screens; semantic markup; strings externalised; states built alongside the happy path.

### Phase E — Verify
Automated (lint, unit, a11y scan, E2E, visual regression, performance budget), then manual (keyboard, screen reader, zoom/reflow, forced colours, RTL and long-string pseudo-locale), then usability test where the level requires.

### Phase F — Ship
Accessibility conformance report and statement updated; release notes in plain language; monitoring of real-user performance and errors.

### Phase G — Learn
Record defects found late and why; add the missing test or rule; update the design system.

## 19. Persistent Project Files

```text
project/
├── docs/
│   ├── DESIGN_SYSTEM.md        # Tokens, components, patterns, do/don't
│   ├── CONTENT_GUIDE.md        # Voice, terminology, error-message patterns
│   ├── CONTEXT_OF_USE.md       # Users, tasks, environments (ISO 9241-210)
│   ├── UI_STATES.md            # State inventory per screen (§6)
│   ├── ACCESSIBILITY.md        # Target level, test method, known issues, ACR link
│   ├── USABILITY_REPORTS/      # ISO/IEC 25066-format evaluation reports
│   └── DECISIONS.md            # Recorded SHOULD exceptions and design decisions
└── tokens/                     # Design tokens (source of truth)
```

## 20. UI Production Readiness Gates

| Gate | Minimum evidence | Block release when |
|---|---|---|
| Interaction principles | §1 review of primary journeys | A principle is violated on a primary journey |
| States | §6 inventory complete and tested | Any reachable state is blank, misleading or a raw error |
| Accessibility | Automated scan clean + keyboard + screen reader + zoom/reflow passes | Any WCAG A failure (Core) or AA failure (Enterprise) on a primary journey |
| Theming | Contrast and visual review per theme | Any theme fails contrast, or one theme is visibly unfinished |
| Palette and restraint | §8.16 named palette per theme; §8.17 restraint test (no decorative gradients, gradient text, glass or coloured shadows) | Decorative gradients or glows, gradient text, several filled buttons, the same palette in both themes, or status colours reused as decoration |
| Focus and descriptions | §8.18 switch persists and hides only explanatory text; §8.19 primary input above the fold, history on its own page | Data or errors hidden by the switch, a cramped primary input, optional inputs nobody uses, or secondary records stacked under the task |
| Restraint and density | §8.15 button budget; §9.1 screenshots at 1366 × 768 and 1536 × 864 | More than one primary action per view, duplicate actions, or the primary input/action not visible above the fold on a laptop |
| Professional polish | §8.14 top-20 checklist; screenshots per theme at desktop and phone width | Themes indistinguishable in the header, no first-run state, buttons with no busy state, unlabelled mobile tables, or nested interactive elements |
| Rich interface | §8.11 patterns used where data is live, scored or multi-step; §8.13 identity recorded | Live data without freshness, scores without bands/targets, repeated alerts without grouping, or a UI that copies another product's look |
| Visual design | §8 tokens, colour roles, type scale, formats; screenshots per theme | Flat UI with no hierarchy, status shown by colour alone, literals instead of tokens, or formats inconsistent with §8.7–8.8 |
| Responsive | Checked at the §9 widths and zoom levels | Content lost, overlapping, or two-direction scroll |
| Content | Terminology and error messages reviewed against content guide | Blaming, vague or jargon errors on primary journeys |
| Forms | §4 rules verified | Data loss on error, unlabeled fields, blocked paste in sign-in |
| Truthfulness | Every displayed value and control traced to real behaviour | Fake data, dead controls, or untrue status |
| Ethics | §12.3 check | Any dark pattern |
| i18n | Pseudo-locale and RTL pass (if localised) | Hard-coded strings, broken layout |
| Performance | §14 metrics on target hardware/network | Targets missed on primary journeys |
| Usability | §16 evaluation (Enterprise+) | Targets missed with no accepted plan |
| Tests | §17 automated suite green, UI coverage complete | Primary journey untested or failing |

**Gate states:** PASS / FAIL / NOT APPLICABLE / UNVERIFIED. Never translate UNVERIFIED into PASS.

## 21. Reusable Prompts

### Build a UI

```text
Read UNIVERSAL_ENTERPRISE_UI_STANDARD.md and UNIVERSAL_AI_SOFTWARE_ENGINEERING_STANDARD.md.
Build [FEATURE / SCREENS] for [USERS / PLATFORM] at conformance level [Core|Enterprise|Regulated].
Use the existing design system and tokens. Define journeys and the §6 state inventory first.
Implement every state, both themes, keyboard support and screen-reader semantics.
Run the automated checks and the manual §7 passes you can perform; mark the rest UNVERIFIED.
Report with the §22 template, including the §20 gate table.
```

### Audit an existing UI

```text
Read UNIVERSAL_ENTERPRISE_UI_STANDARD.md.
Audit this UI without editing code first. For each primary journey, check §1 principles,
§6 states, §7 WCAG 2.2 AA (automated + keyboard + screen reader + 320 px reflow + 200% zoom),
§8 theme parity and contrast, §4 forms, §12.3 dark patterns, and §14 performance.
List every finding with: WCAG/ISO reference, severity (blocker/major/minor), evidence
(screenshot, selector, steps), and fix. Return a prioritised remediation plan.
```

### Produce an accessibility conformance report

```text
Using the audit results, produce an accessibility conformance report for WCAG 2.2 AA
(and EN 301 549 where required): each success criterion as Supports / Partially Supports /
Does Not Support / Not Applicable, with remarks. Do not mark Supports without evidence.
```

## 22. Completion Report Template

```markdown
## UI delivery summary
- Conformance level targeted:
- Screens / components changed:
- Design tokens changed:
- Journeys verified:

## Verification evidence
| Check | Tool / method | Result | Evidence |
|---|---|---|---|
| Automated a11y scan | | | |
| Keyboard-only pass | | | |
| Screen reader pass | | | |
| 200% zoom / 320 px reflow | | | |
| Forced colours / high contrast | | | |
| Light and dark theme review | | | |
| Token contrast test (§8.10) | | | |
| E2E journeys | | | |
| Visual regression | | | |
| Performance (LCP / INP / CLS) | | | |
| Usability test | | | |

## UI production readiness gates (§20)
| Gate | PASS / FAIL / N/A / UNVERIFIED | Reason |
|---|---|---|

## Risks and remaining work
- Known accessibility issues:
- Unverified claims:
- Rollback:
- Next highest-value step:
```

## 23. Reference Standards

**ISO / ISO/IEC** (read the official texts for formal claims):
- ISO 9241-11:2018: Usability, definitions and concepts
- ISO 9241-20:2021: Accessibility guidelines for ICT equipment and services
- ISO 9241-110:2020: Interaction principles
- ISO 9241-112:2017: Principles for the presentation of information
- ISO 9241-125:2017: Guidance on visual presentation of information
- ISO 9241-129:2010: Guidance on software individualisation
- ISO 9241-143:2012: Forms
- ISO 9241-161:2016: Guidance on visual user-interface elements
- ISO 9241-171:2008: Guidance on software accessibility
- ISO 9241-210:2019: Human-centred design for interactive systems
- ISO 9241-220:2019: Processes for human-centred design in organisations
- ISO 9241-391:2016: Reduction of photosensitive seizures
- ISO/IEC 25010:2023: Product quality model (interaction capability)
- ISO/IEC 25019:2023: Quality-in-use model
- ISO/IEC 25062:2006 and ISO/IEC 25066:2016: Common Industry Format usability reports
- ISO/IEC 30071-1:2019: Code of practice for creating accessible ICT products
- ISO/IEC 40500:2012: W3C WCAG 2.0 as an international standard
- ISO/IEC 11581-10:2010: Icon framework
- ISO 24495-1:2023: Plain language, governing principles
- ISO/IEC 29100:2011: Privacy framework
- ISO 8601, ISO 639, ISO 3166, ISO 4217, ISO/IEC 10646: dates, languages, countries, currencies, Unicode
- IEC 62366-1:2015+A1:2020: Usability engineering for medical devices (Regulated only)

**W3C and regional:**
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/) and [Understanding WCAG 2.2](https://www.w3.org/WAI/WCAG22/Understanding/)
- [WAI-ARIA 1.2](https://www.w3.org/TR/wai-aria-1.2/) and the [ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/)
- [EN 301 549](https://www.etsi.org/human-factors-accessibility/en-301-549-v3-the-harmonized-european-standard-for-ict-accessibility): EU ICT accessibility requirements
- [US Section 508](https://www.section508.gov/)
- European Accessibility Act (Directive (EU) 2019/882), applying since 28 June 2025

**Rich-interface and monitoring sources (§8.11):**
- ANSI/ISA-101.01-2015: Human Machine Interfaces for Process Automation Systems (high-performance HMI)
- ANSI/ISA-18.2-2016 and IEC 62682:2022: Management of alarm systems
- ISO 11064-5:2008: Ergonomic design of control centres, displays and controls
- [IBCS International Business Communication Standards](https://www.ibcs.com/standards/)
- Stephen Few, *Bullet Graph Design Specification* (Perceptual Edge)
- [W3C Design Tokens Community Group format](https://www.designtokens.org/)
- [WAI-ARIA Graphics Module](https://www.w3.org/TR/graphics-aria-1.0/)
- [Nielsen Norman Group: 10 usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/)
- [IBM Carbon Design System](https://carbondesignsystem.com/), [Atlassian Design System](https://atlassian.design/), [GitHub Primer](https://primer.style/)

**Platform design guidance (follow on that platform):**
- [Microsoft Fluent 2](https://fluent2.microsoft.design/) and [Windows app design](https://learn.microsoft.com/en-us/windows/apps/design/)
- [Apple Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines/)
- [Material Design 3](https://m3.material.io/)
- [GOV.UK Design System](https://design-system.service.gov.uk/) (a strong public reference for forms, errors and plain language)

## Appendix A. Quick Clause Map

| UEUIS section | Primary sources |
|---|---|
| §1 Interaction principles | ISO 9241-110 |
| §2 Presentation | ISO 9241-112, ISO 9241-125, WCAG 1.4.1 |
| §3 Content | ISO 24495-1, WCAG 3.1, 3.3 |
| §4 Forms | ISO 9241-143, WCAG 1.3.5, 3.3.x |
| §5 UI elements | ISO 9241-161, ISO/IEC 11581-10, WCAG 1.4.13, 4.1.2, 4.1.3 |
| §6 States | ISO 9241-110 (self-descriptiveness, use error robustness) |
| §7 Accessibility | ISO/IEC 40500, WCAG 2.2, ISO 9241-171, ISO 9241-20, ISO/IEC 30071-1, EN 301 549 |
| §8 Visual design system | ISO 9241-112, ISO 9241-125, ISO 9241-161, WCAG 1.4.1, 1.4.3, 1.4.11 |
| §8.14 Professional polish checklist | ISA-101, WAI-ARIA APG, GOV.UK, Carbon, Fluent 2, Material 3, Primer |
| §8.11–8.13 Rich interfaces, crosswalk, identity | ANSI/ISA-101, ISA-18.2 / IEC 62682, ISO 11064-5, IBCS, Few bullet graph, Fluent 2, Material 3, Carbon, Apple HIG |
| §8.16–§8.19 Palettes, enterprise restraint, descriptions switch, focused pages | Fluent 2, IBM Carbon, SAP Fiori, Atlassian, GitHub Primer; ISO 9241-110 (suitability for the task), ISO 9241-112 (freedom from distraction), ISO 9241-129 (individualisation) |
| §8.15 Button restraint; §9.1 Laptop density | Material 3 and Fluent 2 button hierarchy; Carbon density and grid |
| §9 Responsive | WCAG 1.4.4, 1.4.10, 2.5.8 |
| §10 Navigation | ISO 9241-110, WCAG 2.4.x, 3.2.x, WAI-ARIA APG |
| §11 Feedback | ISO 9241-110 (controllability, use error robustness) |
| §12 Trust | ISO/IEC 29100, EU DSA Art. 25, national dark-pattern rules |
| §13 i18n | ISO 639, 3166, 4217, 8601, ISO/IEC 10646, BCP 47 |
| §14 Performance | Core Web Vitals (industry) |
| §15 Personalisation | ISO 9241-129 |
| §16 HCD and evaluation | ISO 9241-210, -11, -220, ISO/IEC 25010, 25066, 25062 |
| §17 Testing | UAISES §6, WAI-ARIA APG |
