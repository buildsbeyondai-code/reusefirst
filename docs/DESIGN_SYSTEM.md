# Design system: Reuse-First Builder

Follows UEUIS v1.2 (OneDrive OPEN SOURCE/UNIVERSAL_ENTERPRISE_UI_STANDARD.md), Enterprise level.

## Identity (UEUIS §8.13, §8.16, §8.17)
- Enterprise and solid: no gradients, glows, gradient text, glass or coloured shadows (a test enforces it). The only
  gradient is the hard-stop band of the bullet graph (data).
- **Slate & Teal (light):** grey neutrals, white header and panels, primary teal #0f766e; categorical rust, raspberry,
  violet, teal, olive used only on icons, 3 px tile markers and avatars.
- **Graphite & Mint (dark):** graphite #0d1117 / #161b22, primary mint #2dd4bf with dark text; categorical orange, pink,
  lavender, aqua, lime.
- Compact 60 px header: logo mark, name, status pill (popover), Descriptions switch (hidden by default), theme control.
- Underline tabs at the top, under the header: 1 Analyze, 2 Build app, 3 Past requirements (its own page; the
  requirement editor is hidden there).
- The requirement box fills the free height on the start screen and shrinks after results; examples sit under it.
- Deliberately different from SysPerf: no glass, no score ring, no top pill-button row.

## Tokens
All in `static/app.css` (`:root`, dark blocks). Semantic roles: accent, success, warning, danger, info, violet (+ `-subtle`),
neutrals, surfaces (bg, panel, sunken), bullet bands q1-q4. `tests/test_ui_standard.py` checks every pair in every theme
and forbids hex literals outside the token blocks.

## Score mapping (UEUIS §8.3)
| Band | Range | Colour | Word |
|---|---|---|---|
| Reuse | ≥ 70% | success | Reuse |
| Fork / extend | 50–69% | info | Fork |
| Borrow parts | 30–49% | warning | Borrow |
| Build new | < 30% | neutral | Build new |

## §8.11 patterns used, and why
| Pattern | Where | Why |
|---|---|---|
| Status strip | App bar | Builds depend on Claude CLI, the standards files and GitHub limits; users see them before they start |
| Stepper | Under the tabs | The tool is a 5-step workflow (Describe, Analyze, Review inputs, Build, Done) |
| Bullet graphs | Best-match tile, every Closeness cell | Many scores are compared; bands and the 70% reuse target matter more than the number alone |
| Distribution bar | Results | Shows at a glance whether reuse is realistic |
| Skeleton | Results while analyzing | Analysis takes up to ~20 s |
| Toasts | Save, delete, build start, copy, launch | Confirm actions without moving focus |
| Relative time | History and builds | Recent work is what users look for |
| Copy buttons | Build folders | Paths are long and needed in a terminal |
Not used: notification centre (no alerts), view modes (one audience), glass materials (identity).
