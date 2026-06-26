# Asterveil Tarot — Intelligent Readings JSON Setup

Version: `2026.06.26-v1`

This repository layout is designed for non-AI, deterministic-but-dynamic tarot readings.
The app downloads only `docs/manifest.json` and the selected language bundle
(`tarot_content_en.json`, `tarot_content_it.json`, or `tarot_content_es.json`).

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
`sha256`/`sizeBytes` in the manifest. To publish a new content version, bump `VERSION` at the top of
`scripts/build_bundle.py` and re-run.

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
