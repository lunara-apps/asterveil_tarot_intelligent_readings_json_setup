# Asterveil Tarot — Rule Schema v2

This document defines the proposed v2 authored synthesis structure for **Asterveil Tarot: Daily Cards**.

The v2 model separates **shared matching logic** from **localized authored text**:

```text
source/shared/rules/combination_rules_v2.json
source/shared/rules/triad_rules_v2.json
source/shared/rules/orientation_rules_v2.json
source/shared/rules/rule_schema_v2.md

source/en/rules/combination_rule_texts_v2.json
source/en/rules/triad_rule_texts_v2.json
source/en/rules/orientation_rule_texts_v2.json
source/en/rules/reading_templates_v2.json
```

## Design goals

- Keep stable IDs, matching criteria, priorities, card IDs, tags, suit names, arcana names, positions, and reading type IDs in English.
- Localize only user-facing text.
- Avoid AI at runtime: the app only selects matching authored rules and renders templates.
- Stay backward-compatible with a future Claude Code implementation by keeping every rule optional-field based.
- Keep readings reflective, non-deterministic, emotionally safe, and legally safe.

## Shared matcher files

Each shared file has:

```json
{
  "schemaVersion": 2,
  "kind": "combinationRuleSet | triadRuleSet | orientationRuleSet",
  "rules": []
}
```

Each rule has stable fields:

| Field | Type | Notes |
|---|---:|---|
| `id` | string | Stable rule ID. Must match the localized text key. |
| `kind` | string | `combination`, `triad`, or `orientation_pattern`. |
| `priority` | number | Higher priority wins when multiple rules match. |
| `readingTypes` | string[] | Supported topics: `general`, `love`, `career`, `money`, `growth`. |
| `spreads` | string[] | Supported spread IDs, usually `one_card`, `pickup_card`, `three_cards`. |
| `positions` | array | For pair rules: objects with `from` and `to`. For triads: position IDs. |
| `orientationPattern` | string[] or string | Examples: `["upright","reversed","upright"]`, `any`, or pair sequences. |
| `matchScope` | string | Recommended values: `ordered_pair`, `reading`, `orientation_sequence`. |

Optional matcher fields include:

```text
fromTagsAny
toTagsAny
requiredTags
requiredTagsAcrossPair
requiredTagsAcrossReading
optionalTags
optionalTagsAny
excludedTags
excludedTagsAcrossPair
requiredCardIds
requiredCardIdsAny
requiredArcana
requiredSuit
requiredSuitCount
minMajorCount
minMinorCount
minCourtCount
minAceCount
minRankCount
minReversedCount
maxReversedCount
cardCount
```

Do not require all fields. A rule matches only the fields it declares.

## Combination rules

Combination rules are ordered pair rules for two cards in a spread.

Recommended matching order:

1. Confirm `spread.id` is in `spreads`.
2. Confirm `readingType` is in `readingTypes`.
3. For every declared pair in `positions`, test the actual cards in those positions.
4. Match `fromTagsAny` against the first card’s active tags.
5. Match `toTagsAny` against the second card’s active tags.
6. Apply orientation constraints if present.
7. Pick the highest priority matching rule, or allow multiple if the UI supports it.

`activeTags` should include upright tags for upright cards and reversed tags for reversed cards. Optionally include base card tags for reversed cards if the app wants broader matching.

## Triad rules

Triad rules read the whole three-card spread.

Recommended matching order:

1. Confirm `three_cards`.
2. Confirm `readingType`.
3. Evaluate whole-reading counts and tag presence.
4. Apply orientation constraints.
5. Pick the highest priority triad rule, or render top N.

## Orientation rules

Orientation rules explain upright/reversed patterns without needing card-specific text.

They can apply to:

- one-card spreads
- pick-a-card spreads
- three-card spreads
- pair connections inside three-card spreads

Pattern values:

```text
upright
reversed
any
```

Example:

```json
{
  "id": "present_reversed_future_upright",
  "kind": "orientation_pattern",
  "orientationPattern": ["any", "reversed", "upright"]
}
```

## Localized text files

Each localized rule text file has:

```json
{
  "schemaVersion": 2,
  "locale": "en",
  "kind": "combinationRuleTexts",
  "ruleTexts": {
    "rule_id": {
      "general": {
        "theme": "...",
        "text": "...",
        "advice": "...",
        "journalPrompt": "...",
        "challenge": "...",
        "opportunity": "..."
      }
    }
  }
}
```

Topics may be omitted if the shared rule does not support them. The renderer should fallback in this order:

1. `ruleTexts[id][readingType]`
2. `ruleTexts[id].general`
3. no localized rule text → skip rule text, render fallback template

## Rendering recommendation

For a three-card reading:

1. Render each card position from existing card `positions.{position}.{readingType}`.
2. Add the best orientation rule if useful.
3. Add top 1–2 combination rules between `past → present` and `present → future`.
4. Add top triad rule for the whole spread.
5. Add advice and journal prompt from the highest-priority matched rule, or from card content fallback.
6. Always append the safety closing.

## Safety rules

- Money text must remain reflective and practical.
- Do not produce investment, profit/loss, legal, medical, pregnancy, or death predictions.
- Reversed cards are never “bad omens”; they indicate blocked, inward, delayed, excessive, or redirected energy.
- Avoid deterministic phrasing such as “this will happen.”
