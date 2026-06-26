#!/usr/bin/env python3
"""Build per-locale tarot content bundles + manifest for GitHub Pages.

Cards are authored per set under ``source/<locale>/cards/``:

    major_arcana.json  cups.json  wands.json  swords.json  pentacles.json

The deprecated single-file ``sample_cards.json`` is only used as a fallback when
no split files exist (if both are present, the split files win).

For each locale the script merges the five sets into one flat ``cards`` array
(Major Arcana first, then Cups, Wands, Swords, Pentacles; each sorted by
``number`` ascending — Ace=1 .. King=14), assembles the bundle, validates the
content, writes the bundle + manifest, refreshes the public reading pages,
self-verifies the generated output, and prunes superseded bundle version folders
(keeping only the version the manifest points at, so old ``v1-*`` folders never
accumulate).

The content version (``v1-<hash>``) is content-addressed: it is derived from a
hash of the delivered content, so it changes automatically — and only — when the
content changes. The app can therefore detect updates by comparing the manifest's
``latestContentVersion`` (which also drives the bundle URL, so a new version busts
any cache), and verify integrity via each bundle's ``sha256``.

Run locally (Windows):  py scripts\\build_bundle.py
Run in CI (Linux):       python scripts/build_bundle.py
Stdlib only; exits non-zero with a clear message on any validation failure.
"""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

# Content version is derived from a hash of the delivered content (see compute_version),
# so it changes automatically — and only — when card/reading content actually changes.
# Bump VERSION_PREFIX manually only for a breaking schema change or to force every client
# to re-download regardless of content.
VERSION_PREFIX = "v1"
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


def build_bundle(loc, data, version):
    return {
        "schemaVersion": 1,
        "contentVersion": version,
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


def compute_version(bundles):
    """Content-addressed version: changes iff the delivered content changes.

    Hashes each locale's assembled bundle while its `contentVersion` is still the
    "" placeholder, so the result depends only on the actual content (cards,
    readings, reading types, rules, safety, deck metadata) and never on the
    version string itself. Identical content -> identical version, so no-op
    rebuilds produce no diff and no new bundle folder.
    """
    h = hashlib.sha256()
    for loc in LOCALES:
        h.update(loc.encode("utf-8"))
        h.update(b"\0")
        h.update(dump_bytes(bundles[loc]))
        h.update(b"\0")
    return f"{VERSION_PREFIX}-{h.hexdigest()[:12]}"


def write_outputs(bundles, version):
    manifest = {
        "schemaVersion": 1,
        "latestContentVersion": version,
        "minimumAppVersion": "1.0.0",
        "defaultLocale": "en",
        "availableLocales": LOCALES,
        "bundles": {},
    }
    out_dir = ROOT / "docs" / "bundles" / version
    out_dir.mkdir(parents=True, exist_ok=True)

    for loc in LOCALES:
        data = dump_bytes(bundles[loc])
        path = out_dir / f"tarot_content_{loc}.json"
        path.write_bytes(data)
        manifest["bundles"][loc] = {
            "version": version,
            "url": f"bundles/{version}/tarot_content_{loc}.json",
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


def prune_old_bundles(keep_versions):
    """Delete superseded ``docs/bundles/<version>/`` folders.

    Keeps only the version(s) the freshly built manifest points at (today that's
    the single ``latestContentVersion``) and removes every other generated
    version folder, so they can't pile up. Stale folders are harmless to the app
    (it always follows the manifest) but untidy, and a checkout that carried more
    than one of them is what broke the old shell-glob CI validation.

    Safe by construction: runs only after ``self_verify`` has confirmed the kept
    version is good, and touches only directories named like a generated version
    (``v<digits>-<hex>``) — anything else under ``docs/bundles/`` is left alone.
    Best-effort: a folder that can't be removed logs a warning but never fails
    the build, since the kept bundle is already written and verified.

    Old folders are never needed for rollback: the version is content-addressed
    and rebuilt from source, so reverting content in git regenerates the prior
    folder on the next build.
    """
    bundles_root = ROOT / "docs" / "bundles"
    if not bundles_root.is_dir():
        return []
    keep = set(keep_versions)
    removed = []
    for child in sorted(bundles_root.iterdir()):
        if not child.is_dir() or child.name in keep:
            continue
        if re.fullmatch(r"v\d+-[0-9a-f]+", child.name) is None:
            continue  # not a generated version folder — leave it untouched
        try:
            shutil.rmtree(child)
        except OSError as exc:
            print(f"WARNING: could not prune {rel(child)}: {exc}", file=sys.stderr)
            continue
        removed.append(child.name)
        print(f"Pruned superseded bundle version: {child.name}")
    return removed


def main():
    try:
        per_locale = {loc: load_locale(loc) for loc in LOCALES}
        validate(per_locale)
        # Assemble bundles with a placeholder version, derive the content hash,
        # then stamp the real version in (reassigning an existing key keeps order).
        bundles = {loc: build_bundle(loc, per_locale[loc], "") for loc in LOCALES}
        version = compute_version(bundles)
        for loc in LOCALES:
            bundles[loc]["contentVersion"] = version
        manifest_path = write_outputs(bundles, version)
        generate_pages()
        self_verify(manifest_path)
        prune_old_bundles({version})
    except BuildError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        return 1

    card_count = len(per_locale["en"]["cards"])
    print(f"Built {version}: {len(LOCALES)} locales, {card_count} cards each. Validation + self-verify OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
