# Asterveil Tarot — Intelligent Readings JSON Setup

Version: `2026.06.26-v1`

This repository layout is designed for non-AI, deterministic-but-dynamic tarot readings.
The app should download only `docs/manifest.json` and the selected language bundle.

## Recommended hosting

- GitHub Pages: publish from `main` / `docs`.
- Cloudflare Pages: build command empty, output directory `docs`.
- Future `bogdansurel.eu` / Hetzner DNS: keep the same files; change only the manifest URL in the app or Remote Config.

## Editing vs delivery

- `source/` = human/Claude-editable small JSON files.
- `docs/` = public static delivery files for the app.

## Reading pages included

- `pickup_card`: pick from 3 facedown cards, 1 selected card.
- `one_card`: one focused card reading.
- `three_cards`: Past · Present · Future.

## Production notes

- Replace the sample cards with all 78 cards from the app's `assets/data/tarot_cards.json`.
- Keep IDs and tags stable across EN/IT/ES.
- Translate display prose, not internal IDs.
- Do not put API keys, Firebase Admin credentials, GitHub tokens, keystores, or private notes in these public files.
