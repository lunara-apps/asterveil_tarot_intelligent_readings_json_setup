#!/usr/bin/env python3
"""Build Asterveil Tarot schema-v2 content bundles + manifest for GitHub Pages.

This script is intentionally a breaking v2 replacement for the old v1 builder.
It assumes the app is not yet published, so it does not preserve the old top-level
``combinationRules`` / ``triadRules`` runtime shape.

Authoring layout expected by the script::

    source/shared/rules/combination_rules_v2.json
    source/shared/rules/triad_rules_v2.json
    source/shared/rules/orientation_rules_v2.json
    source/shared/rules/rule_schema_v2.md

    source/<locale>/cards/major_arcana.json
    source/<locale>/cards/cups.json
    source/<locale>/cards/wands.json
    source/<locale>/cards/swords.json
    source/<locale>/cards/pentacles.json

    source/<locale>/readings/pickup_card.json
    source/<locale>/readings/one_card.json
    source/<locale>/readings/three_cards.json

    source/<locale>/reading_types.json
    source/<locale>/safety.json

    source/<locale>/rules/combination_rule_texts_v2.json
    source/<locale>/rules/triad_rule_texts_v2.json
    source/<locale>/rules/orientation_rule_texts_v2.json
    source/<locale>/rules/reading_templates_v2.json

Runtime output layout::

    docs/manifest.json
    docs/bundles/v2-<hash>/tarot_content_en.json
    docs/bundles/v2-<hash>/tarot_content_it.json
    docs/bundles/v2-<hash>/tarot_content_es.json
    docs/pages/<locale>/<reading>.json

Each runtime bundle contains cards, reading types, spread definitions, safety,
and a fully merged localized ``readingSynthesis`` block. The Flutter app should
therefore download exactly one bundle per locale from the manifest.

Run locally from the repo root or scripts folder:

    py scripts\\build_bundle.py
    python scripts/build_bundle.py

Optional env override for unusual locations:

    TAROT_CONTENT_ROOT=/path/to/repo python scripts/build_bundle.py

Stdlib only. Exits non-zero with a detailed error list on validation failure.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

# Breaking schema-v2 bundles.
VERSION_PREFIX = "v2"
CONTENT_SCHEMA_VERSION = 2
MANIFEST_SCHEMA_VERSION = 2
MINIMUM_APP_VERSION = "1.0.0"

# Keep locale IDs stable. Spanish is neutral Latin American Spanish but the
# runtime locale key remains "es" because that is what the Flutter app already uses.
LOCALES = ["en", "it", "es"]
DEFAULT_LOCALE = "en"

DECK_ID = "asterveil_tarot"
DECK_NAME = "Asterveil Tarot"

READING_TYPES = ["general", "love", "career", "money", "growth"]
SUITS = ["cups", "wands", "swords", "pentacles"]
ARCANA = ["major", "minor"]

# Card set files in canonical merge order.
SPLIT_FILES = ["major_arcana.json", "cups.json", "wands.json", "swords.json", "pentacles.json"]
LEGACY_CARDS_FILE = "sample_cards.json"
READING_FILES = ["pickup_card.json", "one_card.json", "three_cards.json"]
EXPECTED_CARD_COUNT = 78

REQUIRED_CARD_KEYS = [
    "id",
    "name",
    "arcana",
    "keywords",
    "tags",
    "meanings",
    "positions",
    "journalPrompts",
]

SET_FILE_EXPECT = {"major_arcana.json": ("major", None)}
SET_FILE_EXPECT.update({f"{s}.json": ("minor", s) for s in SUITS})

SHARED_RULE_FILES_V2 = {
    "combinationRules": "combination_rules_v2.json",
    "triadRules": "triad_rules_v2.json",
    "orientationRules": "orientation_rules_v2.json",
}

LOCALIZED_RULE_TEXT_FILES_V2 = {
    "combinationRules": "combination_rule_texts_v2.json",
    "triadRules": "triad_rule_texts_v2.json",
    "orientationRules": "orientation_rule_texts_v2.json",
    "templates": "reading_templates_v2.json",
}

GENERATED_VERSION_RE = re.compile(r"v\d+-[0-9a-f]{8,}")
PLACEHOLDER_RE = re.compile(r"\{[A-Za-z][A-Za-z0-9_]*\}")

# Resolve repo root. In normal use the script lives at <repo>/scripts/build_bundle.py.
if os.environ.get("TAROT_CONTENT_ROOT"):
    ROOT = Path(os.environ["TAROT_CONTENT_ROOT"]).resolve()
else:
    _here = Path(__file__).resolve()
    ROOT = _here.parents[1] if _here.parent.name == "scripts" else _here.parent


class BuildError(Exception):
    """Raised on any content/validation problem; aborts the build."""


def rel(path: Path) -> str:
    """Repo-relative path for readable error messages."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def read_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{rel(path)} is not valid UTF-8: {exc}") from exc
    except FileNotFoundError as exc:
        raise BuildError(f"missing file: {rel(path)}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise BuildError(f"invalid JSON in {rel(path)}: {exc}") from exc


def dump_bytes(obj: Any) -> bytes:
    """Serialize published JSON deterministically: UTF-8, no BOM, no trailing newline."""
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False).encode("utf-8")


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def require_object(value: Any, label: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{label}: expected object, got {type(value).__name__}")
        return {}
    return value


def require_array(value: Any, label: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{label}: expected array, got {type(value).__name__}")
        return []
    return value


def load_card_buckets(cards_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Return {set_file: [cards]} in canonical merge order.

    Prefers split set files. Falls back to legacy sample_cards.json only when no
    split files exist, so old local tooling still has a clear migration path.
    """
    buckets: dict[str, list[dict[str, Any]]] = {}

    if any((cards_dir / fname).exists() for fname in SPLIT_FILES):
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

    buckets["major_arcana.json"] = [c for c in arr if isinstance(c, dict) and c.get("arcana") == "major"]
    for suit in SUITS:
        buckets[f"{suit}.json"] = [
            c for c in arr if isinstance(c, dict) and c.get("arcana") == "minor" and c.get("suit") == suit
        ]

    bucketed = sum(len(v) for v in buckets.values())
    if bucketed != len(arr):
        raise BuildError(
            f"{rel(legacy)}: {len(arr) - bucketed} card(s) could not be bucketed "
            f"(bad arcana, or minor without a valid suit)"
        )
    return buckets


def merge_cards(buckets: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Flatten buckets in canonical order, each set sorted by numeric number."""
    merged: list[dict[str, Any]] = []
    for fname in SPLIT_FILES:
        merged.extend(sorted(buckets.get(fname, []), key=lambda c: c.get("number", 999)))
    return merged


def normalize_reading_definition(reading: dict[str, Any]) -> dict[str, Any]:
    """Remove old v1 prose templates from spread definitions.

    v2 prose lives in source/<locale>/rules/reading_templates_v2.json and is
    published under readingSynthesis.templates. The spread JSON should stay as
    UI/position/draw metadata only.
    """
    result = copy.deepcopy(reading)
    result.pop("template", None)
    return result


def load_shared_rules_v2() -> dict[str, dict[str, Any]]:
    shared_dir = ROOT / "source" / "shared" / "rules"
    return {key: read_json(shared_dir / filename) for key, filename in SHARED_RULE_FILES_V2.items()}


def load_locale(loc: str) -> dict[str, Any]:
    src = ROOT / "source" / loc
    rules_dir = src / "rules"

    buckets = load_card_buckets(src / "cards")
    raw_readings = [read_json(src / "readings" / name) for name in READING_FILES]
    readings = [normalize_reading_definition(r) for r in raw_readings]

    localized_rule_texts = {
        key: read_json(rules_dir / filename)
        for key, filename in LOCALIZED_RULE_TEXT_FILES_V2.items()
    }

    return {
        "src": src,
        "buckets": buckets,
        "cards": [c for cards in buckets.values() for c in cards],
        "readings": readings,
        "readingTypes": read_json(src / "reading_types.json"),
        "safety": read_json(src / "safety.json"),
        "localizedRuleTexts": localized_rule_texts,
    }


def id_set(items: list[Any], label: str, loc: str | None, errors: list[str]) -> set[str]:
    prefix = f"[{loc}] " if loc else ""
    ids: list[str] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item.get("id"):
            errors.append(f"{prefix}{label}: entry missing a non-empty string 'id'")
            continue
        ids.append(item["id"])
    dupes = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    if dupes:
        errors.append(f"{prefix}{label}: duplicate id(s) {dupes}")
    return set(ids)


def check_same_sets(per_locale_sets: dict[str, set[str]], label: str, errors: list[str]) -> None:
    ref = per_locale_sets[DEFAULT_LOCALE]
    for loc in LOCALES:
        cur = per_locale_sets[loc]
        if cur != ref:
            errors.append(
                f"{label} id sets differ between '{DEFAULT_LOCALE}' and '{loc}': "
                f"missing in {loc}={sorted(ref - cur)}, extra in {loc}={sorted(cur - ref)}"
            )


def collect_card_vocabulary(cards: list[dict[str, Any]]) -> tuple[set[str], set[str], set[str]]:
    card_ids: set[str] = set()
    tags: set[str] = set()
    ranks: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        if isinstance(card.get("id"), str):
            card_ids.add(card["id"])
        tags.update(t for t in as_list(card.get("tags")) if isinstance(t, str))
        ranks.update([card.get("rank")] if isinstance(card.get("rank"), str) else [])
        reversed_block = card.get("reversed")
        if isinstance(reversed_block, dict):
            tags.update(t for t in as_list(reversed_block.get("tags")) if isinstance(t, str))
    return card_ids, tags, ranks


def validate_card_sources(per_locale: dict[str, dict[str, Any]], errors: list[str]) -> None:
    card_id_sets: dict[str, set[str]] = {}
    reading_id_sets: dict[str, set[str]] = {}
    type_id_sets: dict[str, set[str]] = {}

    for loc in LOCALES:
        data = per_locale[loc]

        for fname, cards in data["buckets"].items():
            exp_arcana, exp_suit = SET_FILE_EXPECT[fname]
            for index, card in enumerate(cards):
                if not isinstance(card, dict):
                    errors.append(f"[{loc}] {fname}[{index}]: card entry is not an object")
                    continue

                cid = card.get("id", f"<index {index}>")
                missing = [key for key in REQUIRED_CARD_KEYS if key not in card]
                if missing:
                    errors.append(f"[{loc}] {fname} card {cid!r}: missing required key(s) {missing}")

                if not is_number(card.get("number")):
                    errors.append(f"[{loc}] {fname} card {cid!r}: 'number' must be numeric, got {card.get('number')!r}")

                arcana = card.get("arcana")
                if arcana not in ARCANA:
                    errors.append(f"[{loc}] {fname} card {cid!r}: arcana must be one of {ARCANA}, got {arcana!r}")
                elif arcana != exp_arcana:
                    errors.append(f"[{loc}] {fname} card {cid!r}: arcana {arcana!r} does not match this set file")

                if arcana == "minor":
                    suit = card.get("suit")
                    if suit not in SUITS:
                        errors.append(f"[{loc}] {fname} card {cid!r}: minor card needs a valid suit, got {suit!r}")
                    elif exp_suit is not None and suit != exp_suit:
                        errors.append(f"[{loc}] {fname} card {cid!r}: suit {suit!r} does not match this set file")

                for topic in READING_TYPES:
                    meanings = card.get("meanings")
                    if not isinstance(meanings, dict) or topic not in meanings:
                        errors.append(f"[{loc}] card {cid!r}: meanings.{topic} is missing")
                    prompts = card.get("journalPrompts")
                    if not isinstance(prompts, dict) or topic not in prompts:
                        errors.append(f"[{loc}] card {cid!r}: journalPrompts.{topic} is missing")

        cards = data["cards"]
        card_id_sets[loc] = id_set(cards, "cards", loc, errors)
        if len(cards) != EXPECTED_CARD_COUNT:
            errors.append(f"[{loc}] expected {EXPECTED_CARD_COUNT} cards, found {len(cards)}")

        readings = require_array(data["readings"], f"[{loc}] readings", errors)
        reading_id_sets[loc] = id_set(readings, "readings", loc, errors)

        reading_types = require_array(data["readingTypes"], f"[{loc}] reading_types.json", errors)
        type_id_sets[loc] = id_set(reading_types, "reading types", loc, errors)
        missing_types = sorted(set(READING_TYPES) - type_id_sets[loc])
        extra_types = sorted(type_id_sets[loc] - set(READING_TYPES))
        if missing_types or extra_types:
            errors.append(f"[{loc}] reading type mismatch: missing={missing_types}, extra={extra_types}")

    check_same_sets(card_id_sets, "card", errors)
    check_same_sets(reading_id_sets, "reading", errors)
    check_same_sets(type_id_sets, "reading type", errors)


def get_shared_rules_array(shared_rules: dict[str, Any], key: str, errors: list[str]) -> list[dict[str, Any]]:
    obj = require_object(shared_rules.get(key), f"shared {key}", errors)
    if obj.get("schemaVersion") != 2:
        errors.append(f"shared {key}: schemaVersion must be 2")
    rules = require_array(obj.get("rules"), f"shared {key}.rules", errors)
    return [r for r in rules if isinstance(r, dict)]


def get_rule_text_map(localized: dict[str, Any], key: str, loc: str, errors: list[str]) -> dict[str, Any]:
    obj = require_object(localized.get(key), f"[{loc}] localized {key}", errors)
    if obj.get("schemaVersion") != 2:
        errors.append(f"[{loc}] localized {key}: schemaVersion must be 2")
    if obj.get("locale") != loc:
        errors.append(f"[{loc}] localized {key}: locale must be {loc!r}, got {obj.get('locale')!r}")
    rule_texts = obj.get("ruleTexts")
    if not isinstance(rule_texts, dict):
        errors.append(f"[{loc}] localized {key}.ruleTexts must be an object keyed by rule id")
        return {}
    return rule_texts


def validate_rule_topic_payload(payload: Any, label: str, errors: list[str]) -> None:
    obj = require_object(payload, label, errors)
    for field in ["theme", "text", "advice", "journalPrompt"]:
        if not isinstance(obj.get(field), str) or not obj[field].strip():
            errors.append(f"{label}.{field}: missing non-empty string")
    for optional in ["challenge", "opportunity"]:
        if optional in obj and (not isinstance(obj.get(optional), str) or not obj[optional].strip()):
            errors.append(f"{label}.{optional}: must be a non-empty string when present")


def validate_rule_matchers(
    rules: list[dict[str, Any]],
    key: str,
    card_ids: set[str],
    card_tags: set[str],
    ranks: set[str],
    safety_tags: set[str],
    reading_ids: set[str],
    errors: list[str],
    warnings: list[str],
) -> None:
    for rule in rules:
        rid = rule.get("id", "<no id>")
        if not isinstance(rule.get("id"), str):
            errors.append(f"shared {key}: rule missing string id")
        if not isinstance(rule.get("priority"), int):
            errors.append(f"shared {key}.{rid}: priority must be an integer")
        if not isinstance(rule.get("kind"), str):
            errors.append(f"shared {key}.{rid}: kind must be a string")

        reading_types = as_list(rule.get("readingTypes"))
        invalid_types = sorted({t for t in reading_types if t not in READING_TYPES})
        if invalid_types or not reading_types:
            errors.append(f"shared {key}.{rid}: invalid or missing readingTypes {invalid_types}")

        spreads = as_list(rule.get("spreads"))
        invalid_spreads = sorted({s for s in spreads if s not in reading_ids})
        if invalid_spreads or not spreads:
            errors.append(f"shared {key}.{rid}: invalid or missing spreads {invalid_spreads}")

        for field in ["requiredCardIds", "excludedCardIds"]:
            for cid in as_list(rule.get(field)):
                if cid not in card_ids:
                    errors.append(f"shared {key}.{rid}.{field}: unknown card id {cid!r}")

        # For TagsAny lists, synonyms are allowed. Fail only if the entire list
        # cannot match any current card tag; warn about individual unused synonyms.
        for field, values in rule.items():
            if not field.endswith("TagsAny") and field not in {"optionalTagsAny"}:
                continue
            if not isinstance(values, list):
                errors.append(f"shared {key}.{rid}.{field}: must be an array")
                continue
            if values and not any(tag in card_tags for tag in values):
                errors.append(f"shared {key}.{rid}.{field}: none of these tags exist in the deck: {values}")
            for tag in values:
                if tag not in card_tags:
                    warnings.append(f"shared {key}.{rid}.{field}: tag {tag!r} is not used by current cards")

        # Required tag lists must be matchable one-by-one, otherwise the rule can never fire.
        for field in ["requiredTags", "requiredTagsAcrossReading", "fromTagsAll", "toTagsAll"]:
            values = rule.get(field)
            if values is None:
                continue
            if not isinstance(values, list):
                errors.append(f"shared {key}.{rid}.{field}: must be an array")
                continue
            missing = sorted({tag for tag in values if tag not in card_tags})
            if missing:
                errors.append(f"shared {key}.{rid}.{field}: required tag(s) not used by current cards: {missing}")

        # Excluded safety tags may be either real card tags or safety blocked topics.
        for field, values in rule.items():
            if not field.startswith("excluded") or "Tags" not in field:
                continue
            if not isinstance(values, list):
                errors.append(f"shared {key}.{rid}.{field}: must be an array")
                continue
            unknown = sorted({tag for tag in values if tag not in card_tags and tag not in safety_tags})
            if unknown:
                warnings.append(f"shared {key}.{rid}.{field}: excluded tag(s) not used by cards or safety topics: {unknown}")

        required_suit_count = rule.get("requiredSuitCount")
        if required_suit_count is not None:
            if not isinstance(required_suit_count, dict):
                errors.append(f"shared {key}.{rid}.requiredSuitCount: must be an object")
            else:
                for suit, count in required_suit_count.items():
                    if suit not in SUITS:
                        errors.append(f"shared {key}.{rid}.requiredSuitCount: invalid suit {suit!r}")
                    if not isinstance(count, int) or count < 1:
                        errors.append(f"shared {key}.{rid}.requiredSuitCount.{suit}: count must be positive integer")

        for field in ["requiredSuit"]:
            if field in rule:
                values = rule[field] if isinstance(rule[field], list) else [rule[field]]
                invalid = sorted({value for value in values if value not in SUITS})
                if invalid:
                    errors.append(f"shared {key}.{rid}.{field}: invalid suit value(s) {invalid}")
        for field in ["requiredArcana"]:
            if field in rule:
                values = rule[field] if isinstance(rule[field], list) else [rule[field]]
                invalid = sorted({value for value in values if value not in ARCANA})
                if invalid:
                    errors.append(f"shared {key}.{rid}.{field}: invalid arcana value(s) {invalid}")
        for field in ["requiredRank"]:
            if field in rule:
                values = rule[field] if isinstance(rule[field], list) else [rule[field]]
                invalid = sorted({value for value in values if value not in ranks})
                if invalid:
                    errors.append(f"shared {key}.{rid}.{field}: invalid rank value(s) {invalid}")

        if "orientationPattern" in rule:
            pattern = rule["orientationPattern"]
            pattern_values = pattern if isinstance(pattern, list) else [pattern]
            invalid_orientation = sorted({value for value in pattern_values if value not in {"upright", "reversed", "any"}})
            if invalid_orientation:
                errors.append(f"shared {key}.{rid}.orientationPattern: invalid value(s) {invalid_orientation}")

        for field in ["minMajorCount", "minReversedCount", "maxReversedCount", "minCourtCount", "minAceCount", "cardCount"]:
            if field in rule and (not isinstance(rule[field], int) or rule[field] < 0):
                errors.append(f"shared {key}.{rid}.{field}: must be a non-negative integer")

        min_rank_count = rule.get("minRankCount")
        if min_rank_count is not None:
            if not isinstance(min_rank_count, dict):
                errors.append(f"shared {key}.{rid}.minRankCount: must be an object like {'{'}'ten': 2{'}'}")
            else:
                for rank, count in min_rank_count.items():
                    if rank not in ranks:
                        errors.append(f"shared {key}.{rid}.minRankCount: invalid rank {rank!r}")
                    if not isinstance(count, int) or count < 1:
                        errors.append(f"shared {key}.{rid}.minRankCount.{rank}: count must be positive integer")


def validate_v2_synthesis_sources(
    shared_rules: dict[str, Any],
    per_locale: dict[str, dict[str, Any]],
    errors: list[str],
    warnings: list[str],
) -> None:
    en_cards = per_locale[DEFAULT_LOCALE]["cards"]
    card_ids, card_tags, ranks = collect_card_vocabulary(en_cards)
    reading_ids = {r["id"] for r in per_locale[DEFAULT_LOCALE]["readings"] if isinstance(r, dict) and isinstance(r.get("id"), str)}
    safety = per_locale[DEFAULT_LOCALE].get("safety", {})
    safety_tags = set(as_list(safety.get("blockedTopics") if isinstance(safety, dict) else []))

    shared_rule_ids: dict[str, set[str]] = {}
    for key in ["combinationRules", "triadRules", "orientationRules"]:
        rules = get_shared_rules_array(shared_rules, key, errors)
        shared_rule_ids[key] = id_set(rules, f"shared {key}", None, errors)
        validate_rule_matchers(rules, key, card_ids, card_tags, ranks, safety_tags, reading_ids, errors, warnings)

    # Localized rule text coverage + topic payload validation.
    en_text_maps: dict[str, dict[str, Any]] = {}
    for loc in LOCALES:
        localized = per_locale[loc]["localizedRuleTexts"]
        for key in ["combinationRules", "triadRules", "orientationRules"]:
            text_map = get_rule_text_map(localized, key, loc, errors)
            if loc == DEFAULT_LOCALE:
                en_text_maps[key] = text_map
            text_ids = set(text_map.keys())
            missing = sorted(shared_rule_ids[key] - text_ids)
            extra = sorted(text_ids - shared_rule_ids[key])
            if missing or extra:
                errors.append(f"[{loc}] {key} rule text mismatch: missing={missing}, extra={extra}")

            # Every rule text must contain at least the topics declared by that rule.
            shared_by_id = {
                r["id"]: r
                for r in get_shared_rules_array(shared_rules, key, errors)
                if isinstance(r.get("id"), str)
            }
            for rid, topics in text_map.items():
                if not isinstance(topics, dict):
                    errors.append(f"[{loc}] {key}.{rid}: ruleTexts entry must be an object keyed by topic")
                    continue
                allowed_topics = set(shared_by_id.get(rid, {}).get("readingTypes", READING_TYPES))
                present_topics = set(topics.keys())
                invalid_topics = sorted(present_topics - set(READING_TYPES))
                missing_topics = sorted(allowed_topics - present_topics)
                if invalid_topics:
                    errors.append(f"[{loc}] {key}.{rid}: invalid topic(s) {invalid_topics}")
                if missing_topics:
                    errors.append(f"[{loc}] {key}.{rid}: missing localized topic(s) {missing_topics}")
                for topic, payload in topics.items():
                    if topic in READING_TYPES:
                        validate_rule_topic_payload(payload, f"[{loc}] {key}.{rid}.{topic}", errors)

        templates = require_object(localized.get("templates"), f"[{loc}] reading_templates_v2", errors)
        if templates.get("schemaVersion") != 2:
            errors.append(f"[{loc}] reading_templates_v2.schemaVersion must be 2")
        if templates.get("locale") != loc:
            errors.append(f"[{loc}] reading_templates_v2.locale must be {loc!r}, got {templates.get('locale')!r}")
        readings = require_object(templates.get("readings"), f"[{loc}] reading_templates_v2.readings", errors)
        for reading_id in reading_ids:
            reading_templates = require_object(readings.get(reading_id), f"[{loc}] templates.readings.{reading_id}", errors)
            supported = set(as_list(reading_templates.get("supportedReadingTypes")))
            if supported != set(READING_TYPES):
                errors.append(f"[{loc}] templates.readings.{reading_id}.supportedReadingTypes must be {READING_TYPES}")
            topic_templates = require_object(reading_templates.get("templates"), f"[{loc}] templates.readings.{reading_id}.templates", errors)
            missing_topics = sorted(set(READING_TYPES) - set(topic_templates.keys()))
            if missing_topics:
                errors.append(f"[{loc}] templates.readings.{reading_id}.templates missing topics {missing_topics}")

    # Placeholder consistency versus English prevents broken translated templates.
    en_templates = per_locale[DEFAULT_LOCALE]["localizedRuleTexts"]["templates"]
    for loc in LOCALES:
        if loc == DEFAULT_LOCALE:
            continue
        compare_placeholders(
            en_templates,
            per_locale[loc]["localizedRuleTexts"]["templates"],
            f"reading_templates_v2 {DEFAULT_LOCALE}->{loc}",
            errors,
        )
        for key in ["combinationRules", "triadRules", "orientationRules"]:
            compare_placeholders(en_text_maps[key], per_locale[loc]["localizedRuleTexts"][key].get("ruleTexts", {}), f"{key} {DEFAULT_LOCALE}->{loc}", errors)


def compare_placeholders(reference: Any, localized: Any, label: str, errors: list[str], path: str = "") -> None:
    """Ensure translated strings preserve placeholder tokens like {cardName}."""
    if isinstance(reference, dict):
        if not isinstance(localized, dict):
            errors.append(f"{label}{path}: localized value is not an object")
            return
        for key, ref_value in reference.items():
            if key not in localized:
                # ID/topic coverage is checked elsewhere; do not duplicate huge errors here.
                continue
            compare_placeholders(ref_value, localized[key], label, errors, f"{path}.{key}" if path else f".{key}")
        return
    if isinstance(reference, list):
        if not isinstance(localized, list):
            errors.append(f"{label}{path}: localized value is not an array")
            return
        for index, ref_value in enumerate(reference):
            if index < len(localized):
                compare_placeholders(ref_value, localized[index], label, errors, f"{path}[{index}]")
        return
    if isinstance(reference, str):
        if not isinstance(localized, str):
            return
        ref_tokens = sorted(set(PLACEHOLDER_RE.findall(reference)))
        loc_tokens = sorted(set(PLACEHOLDER_RE.findall(localized)))
        if ref_tokens != loc_tokens:
            errors.append(f"{label}{path}: placeholder mismatch, expected {ref_tokens}, got {loc_tokens}")


def validate(per_locale: dict[str, dict[str, Any]], shared_rules: dict[str, Any]) -> list[str]:
    """Run all content checks. Raises BuildError on errors; returns warnings."""
    errors: list[str] = []
    warnings: list[str] = []
    validate_card_sources(per_locale, errors)
    validate_v2_synthesis_sources(shared_rules, per_locale, errors, warnings)
    if errors:
        raise BuildError("content validation failed:\n  - " + "\n  - ".join(errors))
    return warnings


def merge_rules_with_texts(shared_rules_obj: dict[str, Any], localized_texts_obj: dict[str, Any], label: str) -> list[dict[str, Any]]:
    """Merge shared matcher rules with localized text by id for runtime use."""
    rules = shared_rules_obj["rules"]
    text_map = localized_texts_obj["ruleTexts"]

    merged: list[dict[str, Any]] = []
    for rule in rules:
        rid = rule["id"]
        runtime_rule = copy.deepcopy(rule)
        runtime_rule["texts"] = copy.deepcopy(text_map[rid])
        merged.append(runtime_rule)

    # Highest priority first. ID tie-breaker keeps output stable.
    merged.sort(key=lambda r: (-int(r.get("priority", 0)), r["id"]))
    return merged


def build_reading_synthesis(data: dict[str, Any], shared_rules: dict[str, Any]) -> dict[str, Any]:
    localized = data["localizedRuleTexts"]
    return {
        "schemaVersion": 2,
        "combinationRules": merge_rules_with_texts(shared_rules["combinationRules"], localized["combinationRules"], "combinationRules"),
        "triadRules": merge_rules_with_texts(shared_rules["triadRules"], localized["triadRules"], "triadRules"),
        "orientationRules": merge_rules_with_texts(shared_rules["orientationRules"], localized["orientationRules"], "orientationRules"),
        "templates": copy.deepcopy(localized["templates"]),
    }


def build_bundle(loc: str, data: dict[str, Any], shared_rules: dict[str, Any], version: str) -> dict[str, Any]:
    return {
        "schemaVersion": CONTENT_SCHEMA_VERSION,
        "contentVersion": version,
        "locale": loc,
        "deckId": DECK_ID,
        "deckName": DECK_NAME,
        "cards": merge_cards(data["buckets"]),
        "readingTypes": copy.deepcopy(data["readingTypes"]),
        "readings": copy.deepcopy(data["readings"]),
        "readingSynthesis": build_reading_synthesis(data, shared_rules),
        "safety": copy.deepcopy(data["safety"]),
    }


def compute_version(bundles: dict[str, dict[str, Any]]) -> str:
    """Content-addressed version: changes iff delivered runtime content changes."""
    h = hashlib.sha256()
    for loc in LOCALES:
        h.update(loc.encode("utf-8"))
        h.update(b"\0")
        h.update(dump_bytes(bundles[loc]))
        h.update(b"\0")
    return f"{VERSION_PREFIX}-{h.hexdigest()[:12]}"


def write_outputs(bundles: dict[str, dict[str, Any]], version: str) -> Path:
    docs_dir = ROOT / "docs"
    out_dir = docs_dir / "bundles" / version
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "contentSchemaVersion": CONTENT_SCHEMA_VERSION,
        "latestContentVersion": version,
        "minimumAppVersion": MINIMUM_APP_VERSION,
        "defaultLocale": DEFAULT_LOCALE,
        "availableLocales": LOCALES,
        "bundles": {},
    }

    for loc in LOCALES:
        data = dump_bytes(bundles[loc])
        path = out_dir / f"tarot_content_{loc}.json"
        path.write_bytes(data)
        manifest["bundles"][loc] = {
            "version": version,
            "schemaVersion": CONTENT_SCHEMA_VERSION,
            "url": f"bundles/{version}/tarot_content_{loc}.json",
            "sha256": hashlib.sha256(data).hexdigest(),
            "sizeBytes": len(data),
        }

    manifest_path = docs_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def generate_pages() -> None:
    """Refresh docs/pages/<locale>/* as verbatim copies of source spread definitions.

    These files are useful if the site or tooling references individual reading
    definitions directly. Runtime Flutter should still prefer the locale bundle.
    """
    for loc in LOCALES:
        src_dir = ROOT / "source" / loc / "readings"
        dst_dir = ROOT / "docs" / "pages" / loc
        dst_dir.mkdir(parents=True, exist_ok=True)
        for name in READING_FILES:
            shutil.copyfile(src_dir / name, dst_dir / name)


def copy_schema_docs() -> None:
    """Publish schema docs beside the bundles for humans / Claude Code handoff."""
    src = ROOT / "source" / "shared" / "rules" / "rule_schema_v2.md"
    if not src.exists():
        return
    dst_dir = ROOT / "docs" / "schema"
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst_dir / "rule_schema_v2.md")


def self_verify(manifest_path: Path) -> None:
    manifest = read_json(manifest_path)
    docs = manifest_path.parent

    if manifest.get("schemaVersion") != MANIFEST_SCHEMA_VERSION:
        raise BuildError(f"manifest schemaVersion must be {MANIFEST_SCHEMA_VERSION}")
    if manifest.get("contentSchemaVersion") != CONTENT_SCHEMA_VERSION:
        raise BuildError(f"manifest contentSchemaVersion must be {CONTENT_SCHEMA_VERSION}")

    for loc, info in manifest["bundles"].items():
        bundle_path = docs / info["url"]
        if not bundle_path.exists():
            raise BuildError(f"manifest references missing bundle: {info['url']}")
        raw = bundle_path.read_bytes()
        if len(raw) != info["sizeBytes"]:
            raise BuildError(f"size mismatch for {loc}: {len(raw)} != manifest {info['sizeBytes']}")
        if hashlib.sha256(raw).hexdigest() != info["sha256"]:
            raise BuildError(f"sha256 mismatch for {loc} bundle")
        bundle = json.loads(raw.decode("utf-8"))
        if bundle.get("schemaVersion") != CONTENT_SCHEMA_VERSION:
            raise BuildError(f"{loc} bundle schemaVersion must be {CONTENT_SCHEMA_VERSION}")
        if bundle.get("contentVersion") != info["version"]:
            raise BuildError(f"{loc} bundle contentVersion does not match manifest version")
        if "readingSynthesis" not in bundle:
            raise BuildError(f"{loc} bundle missing readingSynthesis")


def prune_old_bundles(keep_versions: set[str]) -> list[str]:
    """Delete superseded docs/bundles/<version>/ folders."""
    bundles_root = ROOT / "docs" / "bundles"
    if not bundles_root.is_dir():
        return []

    removed: list[str] = []
    for child in sorted(bundles_root.iterdir()):
        if not child.is_dir() or child.name in keep_versions:
            continue
        if GENERATED_VERSION_RE.fullmatch(child.name) is None:
            continue
        try:
            shutil.rmtree(child)
        except OSError as exc:
            print(f"WARNING: could not prune {rel(child)}: {exc}", file=sys.stderr)
            continue
        removed.append(child.name)
        print(f"Pruned superseded bundle version: {child.name}")
    return removed


def main() -> int:
    try:
        shared_rules = load_shared_rules_v2()
        per_locale = {loc: load_locale(loc) for loc in LOCALES}
        warnings = validate(per_locale, shared_rules)

        # Build with empty contentVersion first; hash the actual delivered content;
        # then stamp the computed version into every bundle.
        bundles = {loc: build_bundle(loc, per_locale[loc], shared_rules, "") for loc in LOCALES}
        version = compute_version(bundles)
        for loc in LOCALES:
            bundles[loc]["contentVersion"] = version

        manifest_path = write_outputs(bundles, version)
        generate_pages()
        copy_schema_docs()
        self_verify(manifest_path)
        prune_old_bundles({version})

    except BuildError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        return 1

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    card_count = len(per_locale[DEFAULT_LOCALE]["cards"])
    combo_count = len(bundles[DEFAULT_LOCALE]["readingSynthesis"]["combinationRules"])
    triad_count = len(bundles[DEFAULT_LOCALE]["readingSynthesis"]["triadRules"])
    orientation_count = len(bundles[DEFAULT_LOCALE]["readingSynthesis"]["orientationRules"])
    print(
        f"Built {version}: {len(LOCALES)} locales, {card_count} cards each, "
        f"{combo_count} combination rules, {triad_count} triad rules, "
        f"{orientation_count} orientation rules. Validation + self-verify OK."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
