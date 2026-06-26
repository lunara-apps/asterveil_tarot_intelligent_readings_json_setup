#!/usr/bin/env python3
"""Simple starter bundle builder.
Replace/extend when all 78 cards are split by suit."""
import json, hashlib
from pathlib import Path

VERSION = "2026.06.26-v1"
ROOT = Path(__file__).resolve().parents[1]
LOCALES = ["en", "it", "es"]

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

manifest = {
    "schemaVersion": 1,
    "latestContentVersion": VERSION,
    "minimumAppVersion": "1.0.0",
    "defaultLocale": "en",
    "availableLocales": LOCALES,
    "bundles": {}
}

out_dir = ROOT / "docs" / "bundles" / VERSION
out_dir.mkdir(parents=True, exist_ok=True)

for loc in LOCALES:
    src = ROOT / "source" / loc
    cards = read_json(src / "cards" / "sample_cards.json")
    readings = [read_json(src / "readings" / name) for name in ["pickup_card.json", "one_card.json", "three_cards.json"]]
    bundle = {
        "schemaVersion": 1,
        "contentVersion": VERSION,
        "locale": loc,
        "deckId": "asterveil_tarot",
        "deckName": "Asterveil Tarot",
        "cards": cards,
        "readingTypes": read_json(src / "reading_types.json"),
        "readings": readings,
        "combinationRules": read_json(src / "rules" / "combination_rules.json"),
        "triadRules": read_json(src / "rules" / "triad_rules.json"),
        "safety": read_json(src / "safety.json")
    }
    data = json.dumps(bundle, ensure_ascii=False, indent=2).encode("utf-8")
    path = out_dir / f"tarot_content_{loc}.json"
    path.write_bytes(data)
    manifest["bundles"][loc] = {
        "version": VERSION,
        "url": f"bundles/{VERSION}/tarot_content_{loc}.json",
        "sha256": hashlib.sha256(data).hexdigest(),
        "sizeBytes": len(data)
    }

(ROOT / "docs" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print("Built", VERSION)
