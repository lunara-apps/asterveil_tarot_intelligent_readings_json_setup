# Asterveil Tarot — Intelligent Readings JSON Setup

Content schema: **v3** (`schemaVersion: 3`). Content version is **content-addressed** —
`v3-<hash>`, derived automatically by the build from a hash of the delivered content
(see [Versioning](#versioning)).

This repository layout is designed for non-AI, deterministic-but-dynamic tarot readings.
The app downloads only `docs/manifest.json` and the selected language bundle
(`tarot_content_en.json`, `tarot_content_it.json`, or `tarot_content_es.json`). Each bundle
carries the deck, reading spreads, the `readingSynthesis` rule engine, and a
`personalizedReadings` module (Arcana Signature). See [Schema v3](#schema-v3).

## Editing vs delivery

- `source/` = human/Claude-editable small JSON files (the source of truth).
- `docs/` = generated public static delivery files for the app. **Do not hand-edit `docs/`** —
  it is produced by `scripts/build_bundle.py`.

Supported locales: `en`, `it`, `es`. Internal IDs, tags, reading IDs, position IDs, and rule IDs
must stay identical across languages; only user-facing text is translated. Tags stay as internal
English-style identifiers (`healing`, `loss`, `new_beginning`, `stability`, …).

## Card content (authored per set)

Cards are edited **per set**, one file per arcana/suit, in each locale's `cards/` folder:

```
source/<locale>/cards/
  major_arcana.json   # arcana == "major"
  cups.json           # arcana == "minor", suit == "cups"
  wands.json          # arcana == "minor", suit == "wands"
  swords.json         # arcana == "minor", suit == "swords"
  pentacles.json      # arcana == "minor", suit == "pentacles"
```

Each file is a bare JSON array of card objects. A set with no cards yet is still present as `[]`
(e.g. `wands.json` / `swords.json`). The build merges all five sets into a single flat `cards`
array per bundle, ordered **Major Arcana first, then Cups, Wands, Swords, Pentacles**, each set
sorted by `number` ascending (Ace = 1 … 10, Page = 11, Knight = 12, Queen = 13, King = 14).

> **`sample_cards.json` is removed (deprecated).** It is no longer authored. The build script keeps
> a backward-compatibility fallback: if a locale has none of the five split files, it will read a
> `sample_cards.json` instead. When both exist, the split files win. Do not reintroduce it.

### Required card fields

Every card must include at least: `id`, `name`, `arcana`, `keywords`, `tags`, `meanings`,
`positions`, `journalPrompts`. Additionally: every card needs a numeric `number`; every **minor**
card needs a valid `suit` (`cups`/`wands`/`swords`/`pentacles`). Extra fields used by the deck —
`rank`, `romanNumeral` (major), `assetId`, `toneTags` — are preserved as-is.

### How to add a new card

1. Add the card object to the matching set file (e.g. a wand card → `wands.json`) in **all three
   locales** (`en`, `it`, `es`).
2. Keep the **same `id`** and the **same internal identifiers** (`arcana`, `suit`, `number`, `tags`,
   `assetId`, etc.) across the three locales. Translate only the display prose (`name`, `meanings`,
   `positions`, `journalPrompts`).
3. Run the build (below). It validates that all locales share the same card IDs, reading IDs, and
   reading-type IDs, that required fields are present, that minors have a valid suit, and that every
   `number` is numeric — and fails with a clear message if anything is off.

## Reading pages included

- `pickup_card`: pick from 3 facedown cards, 1 selected card.
- `one_card`: one focused card reading.
- `three_cards`: Past · Present · Future.

These page templates live in `source/<locale>/readings/` and are copied verbatim into
`docs/pages/<locale>/` by the build.

## Schema v3

Schema **v3** = the existing v2 `readingSynthesis` engine (unchanged) **plus** a new
`personalizedReadings` module. The bundle/manifest envelope is `schemaVersion: 3`, while the
synthesis engine inside keeps its own internal `schemaVersion: 2` and its `*_v2.json` sources —
`docs/schema/rule_schema_v2.md` remains the authority for drawn/random readings, and nothing there
was renamed. Full overview: `docs/schema/schema_v3_overview.md`.

Bundle root keys (v3): `schemaVersion`, `contentVersion`, `locale`, `deckId`, `deckName`,
`cards`, `readingTypes`, `readings`, `readingSynthesis`, `personalizedReadings`, `safety`.

The manifest gains a `features.arcanaSignature` block (`enabled`, `moduleSchemaVersion: 1`,
`delivery: "inside_locale_bundle"`, `bundlePath: "personalizedReadings.arcanaSignature"`,
`requiresContentSchemaVersion: 3`).

> **Flutter handoff:** v3 is a breaking bump (the app is not yet published). The app's content
> gate must move from an exact `contentSchemaVersion == 2` check to accept `3`. Once updated,
> drawn/random readings work exactly as before.

## Personalized readings — Arcana Signature

Arcana Signature is a **birthday-calculated** reading (not a random draw): from a date of birth it
surfaces two **Major Arcana** archetypes — a Personality Card and a Soul Card. Required input is a
birthday; an optional Preferred Focus (`love`, `work`, `self_growth`, `healing`, `creativity`) only
shifts the interpretation angle and journal prompts, **never** the calculated cards. There is **no**
name/nickname input, no name numerology, and no reversed cards. The five focus ids are
feature-scoped and are **not** added to the global `readingTypes` list.

The birthday → card calculation is implemented in **Flutter**; this repo only describes the method
(constants under `calculation`, including the 1–22 range and the `22 → Fool (deck number 0)`
resolution) and supplies localized templates, focus copy, 13 pair themes, helper/privacy copy, and
validation.

```
source/shared/personalized_readings/
  arcana_signature_pairs.json   # non-localized pair card data (the 13 reachable pairs)
  arcana_signature_schema.md    # method + field reference
source/shared/schema_v3_overview.md
source/<locale>/personalized_readings/
  arcana_signature.json         # module structure + localized text per locale
```

Structural fields (ids, positions, focus ids, calculation constants, placeholders, blocked
claims, pair ids) are validated **identical** across `en`/`it`/`es`; only display text differs.
The build also enforces the allowed placeholder set, blocks any name-feature artifacts, and scans
all user-facing strings for deterministic/unsafe wording (English plus high-risk IT/ES
equivalents). Details: `docs/schema/arcana_signature_schema.md`.

## Running the build locally

The build script is pure Python 3 (standard library only) and writes UTF-8 (no BOM).

**Windows (PowerShell):**

```powershell
cd "D:\Documents\Project\Github Public Projects\asterveil_tarot_intelligent_readings_json_setup"
py scripts\build_bundle.py
```

If `py` is unavailable, use the full interpreter path (note: a bare `python` may be a Microsoft
Store alias that does nothing):

```powershell
& "D:\Python\Sdk\Python314\python.exe" scripts\build_bundle.py
```

**Linux / macOS / CI:**

```bash
python scripts/build_bundle.py
```

The script (re)generates `docs/manifest.json`, the three `docs/bundles/<VERSION>/tarot_content_*.json`
bundles, and `docs/pages/<locale>/*`, then self-verifies that each bundle matches its recorded
`sha256`/`sizeBytes` in the manifest.

## Versioning

The content version is **content-addressed**: the build hashes the delivered content and produces a
version of the form `v3-<hash>` (e.g. `v3-e5a09ebdf731`). You do **not** bump it by hand — it changes
automatically, and only, when card/reading content actually changes. Rebuilding with no content change
produces the exact same version (and therefore no diff and no new bundle folder).

Because the version is also part of the bundle URL (`bundles/<VERSION>/tarot_content_<locale>.json`),
a content change yields a brand-new URL, which reliably busts any CDN/browser cache. The app should:

- **detect updates** by comparing the manifest's `latestContentVersion` to the version it last fetched;
- **verify integrity** of a downloaded bundle against the manifest's `sha256`.

Each published version gets its own immutable `bundles/<VERSION>/` folder; older folders are left in
place so clients mid-download keep working. The `v3` prefix (`VERSION_PREFIX` in
`scripts/build_bundle.py`) is the only manual lever — bump it for a breaking schema change or to force
every client to re-download regardless of content.

## How publishing works (GitHub Pages)

`.github/workflows/deploy-pages.yml` runs on every push to `main` (and via manual dispatch):

1. Checks out the repo and sets up Python.
2. Runs `python scripts/build_bundle.py` — which **validates** content and regenerates `docs/`.
   The job fails (and nothing deploys) if validation fails.
3. Confirms the manifest and all three locale bundles exist.
4. Uploads `docs/` and deploys it to GitHub Pages.

`.github/workflows/validate-json.yml` additionally parses every `*.json` file on each push and pull
request, so malformed JSON is caught on branches before merge.

> **One-time setup:** the Actions-based deploy requires **Settings → Pages → Source = "GitHub
> Actions"** in the GitHub UI. Until that switch is made, the deploy job stays inactive and the
> repository keeps serving via the older branch-folder mode (`main` / `docs`). Switching the source
> supersedes branch-folder serving; the two modes are mutually exclusive.

### Other hosting (optional)

- Cloudflare Pages: build command empty, output directory `docs`.
- Future `bogdansurel.eu` / Hetzner DNS: keep the same files; change only the manifest URL in the
  app or Remote Config.

## Production notes

- Grow the deck toward all 78 cards by adding card objects to the per-set files above
  (sourced from the app's `assets/data/tarot_cards.json`).
- Keep IDs and tags stable across EN/IT/ES.
- Translate display prose, not internal IDs.
- Do not put API keys, Firebase Admin credentials, GitHub tokens, keystores, `.env` files, or
  private notes in these public files.
