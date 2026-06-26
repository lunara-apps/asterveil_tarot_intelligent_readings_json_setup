#!/usr/bin/env python3
"""Build per-locale tarot content bundles + manifest for GitHub Pages.

Cards are authored per set under ``source/<locale>/cards/``:

    major_arcana.json  cups.json  wands.json  swords.json  pentacles.json

The deprecated single-file ``sample_cards.json`` is only used as a fallback when
no split files exist (if both are present, the split files win).

For each locale the script merges the five sets into one flat ``cards`` array
(Major Arcana first, then Cups, Wands, Swords, Pentacles; each sorted by
``number`` ascending — Ace=1 .. King=14), assembles the bundle, validates the
content, writes the bundle + manifest, refreshes the public reading pages, and
self-verifies the generated output.

Run locally (Windows):  py scripts\\build_bundle.py
Run in CI (Linux):       python scripts/build_bundle.py
Stdlib only; exits non-zero with a clear message on any validation failure.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

VERSION = "2026.06.26-v1"
ROOT = Path(__file__).resolve().parents[1]
LOCALES = ["en", "it", "es"]
SUITS = ["cups", "wands", "swords", "pentacles"]

# Card set files in canonical merge order (Major Arcana first, then the suits).
SPLIT_FILES = ["major_arcana.json"] + [f"{s}.json" for s in SUITS]
LEGACY_CARDS_FILE = "sample_cards.json"
READING_FILES = ["pickup_card.json", "one_card.json", "three_cards.json"]
REQUIRED_CARD_KEYS = [
    "id", "name", "arcana", "keywords", "tags", "meanings", "positions", "journalPrompts",
]

# Expected (arcana, suit) for each set file. suit is None where not applicable.
SET_FILE_EXPECT = {"major_arcana.json": ("major", None)}
SET_FILE_EXPECT.update({f"{s}.json": ("minor", s) for s in SUITS})


class BuildError(Exception):
    """Raised on any content/validation problem; aborts the build."""


def rel(path):
    """Repo-relative path for readable error messages."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def read_json(path):
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{rel(path)} is not valid UTF-8: {exc}")
    except FileNotFoundError:
        raise BuildError(f"missing file: {rel(path)}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise BuildError(f"invalid JSON in {rel(path)}: {exc}")


def dump_bytes(obj):
    """Serialize exactly like the published bundles: UTF-8, no BOM, no trailing newline."""
    return json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def load_card_buckets(cards_dir):
    """Return an ordered dict {set_file: [cards]} in canonical merge order.

    Prefers the split set files; falls back to the legacy sample_cards.json only
    when none of the split files exist.
    """
    buckets = {}
    if any((cards_dir / f).exists() for f in SPLIT_FILES):
        for fname in SPLIT_FILES:
            path = cards_dir / fname
            arr = read_json(path) if path.exists() else []
            if not isinstance(arr, list):
                raise BuildError(f"{rel(path)} must be a JSON array, got {type(arr).__name__}")
            buckets[fname] = arr
        return buckets

    legacy = cards_dir / LEGACY_CARDS_FILE
    if not legacy.exists():
        raise BuildError(
            f"no card source in {rel(cards_dir)} "
            f"(neither split set files nor {LEGACY_CARDS_FILE})"
        )
    arr = read_json(legacy)
    if not isinstance(arr, list):
        raise BuildError(f"{rel(legacy)} must be a JSON array, got {type(arr).__name__}")
    # Partition the legacy array into the same buckets for a consistent merge order.
    buckets["major_arcana.json"] = [c for c in arr if isinstance(c, dict) and c.get("arcana") == "major"]
    for s in SUITS:
        buckets[f"{s}.json"] = [
            c for c in arr if isinstance(c, dict) and c.get("arcana") == "minor" and c.get("suit") == s
        ]
    bucketed = sum(len(v) for v in buckets.values())
    if bucketed != len(arr):
        raise BuildError(
            f"{rel(legacy)}: {len(arr) - bucketed} card(s) could not be bucketed "
            f"(bad arcana, or minor without a valid suit)"
        )
    return buckets


def merge_cards(buckets):
    """Flatten buckets in canonical order, each set sorted by numeric `number`."""
    merged = []
    for fname in SPLIT_FILES:
        merged.extend(sorted(buckets.get(fname, []), key=lambda c: c["number"]))
    return merged


def load_locale(loc):
    src = ROOT / "source" / loc
    buckets = load_card_buckets(src / "cards")
    readings = [read_json(src / "readings" / name) for name in READING_FILES]
    reading_types = read_json(src / "reading_types.json")
    return {
        "src": src,
        "buckets": buckets,
        "cards": [c for arr in buckets.values() for c in arr],
        "readings": readings,
        "reading_types": reading_types,
    }


def _id_set(items, label, loc, errors):
    ids = []
    for item in items:
        if not isinstance(item, dict) or "id" not in item:
            errors.append(f"[{loc}] {label}: entry missing an 'id'")
            continue
        ids.append(item["id"])
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        errors.append(f"[{loc}] {label}: duplicate id(s) {dupes}")
    return set(ids)


def validate(per_locale):
    """Run all content checks; raise BuildError listing every problem found."""
    errors = []
    card_ids, reading_ids, type_ids = {}, {}, {}

    for loc in LOCALES:
        data = per_locale[loc]

        # Per-card checks, per set file (so misfiled cards are caught too).
        for fname, cards in data["buckets"].items():
            exp_arcana, exp_suit = SET_FILE_EXPECT[fname]
            for card in cards:
                if not isinstance(card, dict):
                    errors.append(f"[{loc}] {fname}: a card entry is not an object")
                    continue
                cid = card.get("id", "<no id>")
                missing = [k for k in REQUIRED_CARD_KEYS if k not in card]
                if missing:
                    errors.append(f"[{loc}] {fname} card {cid!r}: missing required key(s) {missing}")
                if not is_number(card.get("number")):
                    errors.append(f"[{loc}] {fname} card {cid!r}: 'number' must be numeric, got {card.get('number')!r}")
                arcana = card.get("arcana")
                if arcana not in ("major", "minor"):
                    errors.append(f"[{loc}] {fname} card {cid!r}: arcana must be 'major' or 'minor', got {arcana!r}")
                elif arcana != exp_arcana:
                    errors.append(f"[{loc}] {fname} card {cid!r}: arcana {arcana!r} does not match this set file")
                if arcana == "minor":
                    suit = card.get("suit")
                    if suit not in SUITS:
                        errors.append(f"[{loc}] {fname} card {cid!r}: minor card needs a valid suit, got {suit!r}")
                    elif exp_suit is not None and suit != exp_suit:
                        errors.append(f"[{loc}] {fname} card {cid!r}: suit {suit!r} does not match this set file")

        card_ids[loc] = _id_set(data["cards"], "cards", loc, errors)
        reading_ids[loc] = _id_set(data["readings"], "readings", loc, errors)
        if not isinstance(data["reading_types"], list):
            errors.append(f"[{loc}] reading_types.json must be a JSON array")
            type_ids[loc] = set()
        else:
            type_ids[loc] = _id_set(data["reading_types"], "reading types", loc, errors)

    # Cross-locale: every locale must expose the same id sets.
    _check_same_sets(card_ids, "card", errors)
    _check_same_sets(reading_ids, "reading", errors)
    _check_same_sets(type_ids, "reading type", errors)

    if errors:
        raise BuildError("content validation failed:\n  - " + "\n  - ".join(errors))


def _check_same_sets(per_locale_sets, label, errors):
    ref_loc = LOCALES[0]
    ref = per_locale_sets[ref_loc]
    for loc in LOCALES[1:]:
        cur = per_locale_sets[loc]
        if cur != ref:
            missing = sorted(ref - cur)
            extra = sorted(cur - ref)
            errors.append(
                f"{label} id sets differ between '{ref_loc}' and '{loc}': "
                f"missing in {loc}={missing}, extra in {loc}={extra}"
            )


def build_bundle(loc, data):
    return {
        "schemaVersion": 1,
        "contentVersion": VERSION,
        "locale": loc,
        "deckId": "asterveil_tarot",
        "deckName": "Asterveil Tarot",
        "cards": merge_cards(data["buckets"]),
        "readingTypes": data["reading_types"],
        "readings": data["readings"],
        "combinationRules": read_json(data["src"] / "rules" / "combination_rules.json"),
        "triadRules": read_json(data["src"] / "rules" / "triad_rules.json"),
        "safety": read_json(data["src"] / "safety.json"),
    }


def write_outputs(per_locale):
    manifest = {
        "schemaVersion": 1,
        "latestContentVersion": VERSION,
        "minimumAppVersion": "1.0.0",
        "defaultLocale": "en",
        "availableLocales": LOCALES,
        "bundles": {},
    }
    out_dir = ROOT / "docs" / "bundles" / VERSION
    out_dir.mkdir(parents=True, exist_ok=True)

    for loc in LOCALES:
        data = dump_bytes(build_bundle(loc, per_locale[loc]))
        path = out_dir / f"tarot_content_{loc}.json"
        path.write_bytes(data)
        manifest["bundles"][loc] = {
            "version": VERSION,
            "url": f"bundles/{VERSION}/tarot_content_{loc}.json",
            "sha256": hashlib.sha256(data).hexdigest(),
            "sizeBytes": len(data),
        }

    # write_text (not write_bytes) preserves the repo's existing manifest line-ending
    # behavior under core.autocrlf=true, so regenerating never shows a spurious diff.
    manifest_path = ROOT / "docs" / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def generate_pages():
    """Refresh docs/pages/<locale>/* as verbatim copies of the source readings."""
    for loc in LOCALES:
        src_dir = ROOT / "source" / loc / "readings"
        dst_dir = ROOT / "docs" / "pages" / loc
        dst_dir.mkdir(parents=True, exist_ok=True)
        for name in READING_FILES:
            shutil.copyfile(src_dir / name, dst_dir / name)


def self_verify(manifest_path):
    manifest = read_json(manifest_path)
    docs = manifest_path.parent
    for loc, info in manifest["bundles"].items():
        bundle_path = docs / info["url"]
        if not bundle_path.exists():
            raise BuildError(f"manifest references missing bundle: {info['url']}")
        raw = bundle_path.read_bytes()
        if len(raw) != info["sizeBytes"]:
            raise BuildError(f"size mismatch for {loc}: {len(raw)} != manifest {info['sizeBytes']}")
        if hashlib.sha256(raw).hexdigest() != info["sha256"]:
            raise BuildError(f"sha256 mismatch for {loc} bundle")
        json.loads(raw.decode("utf-8"))  # must parse


def main():
    try:
        per_locale = {loc: load_locale(loc) for loc in LOCALES}
        validate(per_locale)
        manifest_path = write_outputs(per_locale)
        generate_pages()
        self_verify(manifest_path)
    except BuildError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        return 1

    card_count = len(per_locale["en"]["cards"])
    print(f"Built {VERSION}: {len(LOCALES)} locales, {card_count} cards each. Validation + self-verify OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
