# Arcana Signature — module schema (personalizedReadings v1)

Arcana Signature is a **birthday-calculated** personal reading. It is *not* a random draw and
*not* a generic two-card Major Arcana synthesis engine. From a date of birth it surfaces two
Major Arcana archetypes — a **Personality Card** and a **Soul Card** — as a reflective mirror.

It ships inside every locale bundle at `personalizedReadings.arcanaSignature` and requires
content schema v3. The module's own version is `personalizedReadings.schemaVersion: 1`.

## Authoring layout

```
source/shared/personalized_readings/arcana_signature_pairs.json   # non-localized card data (single source of truth)
source/shared/personalized_readings/arcana_signature_schema.md    # this file
source/<locale>/personalized_readings/arcana_signature.json       # structure + localized text per locale
```

The build (`scripts/build_bundle.py`) merges the shared `cards` / `bridgeCards` into each
locale's `pairThemes` and emits one fully merged module per locale. Structural fields are
validated **identical** across `en` / `it` / `es`; only display text differs.

## What this repo provides vs. what Flutter does

- **This repo:** localized templates, focus copy, the 13 pair themes, helper/privacy copy, the
  calculation *description* + constants, and validation.
- **Flutter:** computes the two card ids from the birthday using the constants below, fills the
  placeholders, and renders. The birthday math itself is **not** implemented here.

## Calculation (method `mm_dd_yy_yy_reduce_to_major_arcana`)

1. Take the birth date as four 2-digit parts: month (`mm`), day (`dd`), and the year split into
   two halves (`yy` + `yy`, e.g. `1990` → `19` + `90`). Sum them.
2. Digit-reduce the sum until it lands in the range **1–22** (`calculationRange`). This is the
   **Personality** value. Mapping of values:
   - `1` = The Magician … `21` = The World (value == Major Arcana number for 1–21).
   - `22` = The Fool. The Fool is **not** treated as `0` during reduction; only at the final
     deck lookup does `22` resolve to the existing Fool card, which is stored at
     `number == 0` (`maps22ToFool: true`, `foolNumber: 0`, `foolCalculationValue: 22`).
3. The **Soul** value is the Personality value reduced once more to a single digit (1–9), which
   resolves to the Major Arcana of that number. Single-digit Personality values (1–9) give
   Personality == Soul (the same card) — these render via the `combinedReflection` template and
   have **no** `pairThemes` entry.

### The 19 / Sun three-card exception

`19` (The Sun) reduces `19 → 10 → 1`, traditionally touching three cards. Policy
`collapse_to_two_with_note`: Arcana Signature shows **exactly two** visible cards
(Personality = The Sun, Soul = The Magician) and surfaces Wheel of Fortune (10) only through
`bridgeCards` + the localized `bridgeNote` / `calculation.threeCardExceptionNote`. There is no
third position.

## The 13 reachable pairs

Keyed in `arcana_signature_pairs.json`. `cards` lists the two **visible** cards; Flutter matches a
reading to a theme by the **unordered set** of the two visible card ids (key string + array order
are stable-id/cosmetic only).

| key | visible cards | bridge |
|-----|---------------|--------|
| `the_magician__wheel_of_fortune` | Magician(1), Wheel(10) | — |
| `the_high_priestess__justice` | High Priestess(2), Justice(11) | — |
| `the_empress__the_hanged_man` | Empress(3), Hanged Man(12) | — |
| `the_emperor__death` | Emperor(4), Death(13) | — |
| `the_hierophant__temperance` | Hierophant(5), Temperance(14) | — |
| `the_lovers__the_devil` | Lovers(6), Devil(15) | — |
| `the_chariot__the_tower` | Chariot(7), Tower(16) | — |
| `strength__the_star` | Strength(8), Star(17) | — |
| `the_hermit__the_moon` | Hermit(9), Moon(18) | — |
| `the_sun__wheel_of_fortune__the_magician` | Sun(19), Magician(1) | Wheel(10) |
| `the_high_priestess__judgement` | High Priestess(2), Judgement(20) | — |
| `the_empress__the_world` | Empress(3), World(21) | — |
| `the_fool__the_emperor` | Fool(0/22), Emperor(4) | — |

## Positions & focuses

- Positions: exactly `personality_card`, `soul_card`; each `cardFilter` = `{"arcana": "major"}`.
  No reversed cards.
- Supported focuses: exactly `love`, `work`, `self_growth`, `healing`, `creativity`. A focus is
  **optional** and only shifts interpretation angle + journal prompts; it **never** changes the
  calculated cards. These focus ids are feature-scoped and are **not** added to the global
  `readingTypes` list.

## Placeholders (the only ones allowed)

`{personalityCardName}`, `{soulCardName}`, `{focusLabel}`, `{personalityKeywords}`,
`{soulKeywords}`, `{personalitySummary}`, `{soulSummary}`, `{pairTheme}`, `{pairReflection}`,
`{journalPrompt}`.

`{journalPrompt}` is the substitution token a host string may use to embed the resolved
(default or focus) journal-prompt text; the `journalPrompt` template fields are its localized
sources, so it may appear zero times inside the templates themselves.

**Forbidden:** any `{name…}` placeholder, and the name-feature ids `name`, `nickname`,
`name_card`, `name_resonance`. Arcana Signature v1 has **no** name/nickname input, no name
numerology, and no Name Resonance Card.

## Templates

- `templates.default`: `opening`, `personalityIntro`, `soulIntro`, `combinedReflection`,
  `focusReflection`, `journalPrompt`, `closing`.
- `templates.focuses.<focus>`: `focusReflection`, `journalPrompt` (per focus).

## Safety

`safety.tone` = `reflective_not_predictive`. `safety.blockedClaims` (stable English tokens):
`destiny`, `fate`, `guaranteed_future`, `medical_advice`, `psychological_diagnosis`,
`legal_advice`, `financial_advice`.

Authored copy is scanned at build time for deterministic / unsafe wording (fate, destiny,
prediction, guarantees, defines-you, medical/legal/financial advice, diagnosis, pregnancy/death
prediction) in English plus the highest-risk Italian/Spanish equivalents. Keep the Asterveil
tone — calm, mystical, elegant, reflective: *symbolic reflection*, *personal archetype*,
*reflective mirror*, *themes you may explore*, *an invitation to notice*, *a gentle prompt for
self-discovery*.
