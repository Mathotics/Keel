# Brand colors

Canonical palette sampled from `assets/logos.png` (Keel logo sheet: brand blue marks on white, light gray sheet). The UI reads the same tokens from [`assets/brand.css`](../assets/brand.css).

| Token | Hex | Role |
| --- | --- | --- |
| `--keel-blue` | `#0068B0` | Primary brand blue (menu bar background). Dominant non-white color on the sheet. |
| `--keel-blue-deep` | `#0062AB` | Deeper saturated blue from the same marks; body text. |
| `--keel-white` | `#FFFFFF` | Mark interiors, icon well on the bar, page background. |
| `--keel-sheet` | `#EBF0F3` | Light gray-blue of the logo sheet; footer background (distinct from the menu bar). |

Type identity hues, recorded by [ADR 027](adr/ADR-027.md). The top bar and footer stay on the logo tokens above. Card washes and chip fills are a light mix of these hues on white, so title and meta stay dark and readable.

| Token | Hex | Role |
| --- | --- | --- |
| `--keel-type-epic` | `#0068B0` | Epic. Same as brand blue. |
| `--keel-type-story` | `#0F7A73` | Story. Teal, distinct from brand blue. |
| `--keel-type-subtask` | `#B86A00` | Subtask. Amber. |

See [ADR 001](adr/ADR-001.md) and [ADR 002](adr/ADR-002.md). Version numbers are not listed here; see [Package version](version.md).
