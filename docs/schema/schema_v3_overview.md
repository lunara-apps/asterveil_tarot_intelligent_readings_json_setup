# Asterveil Tarot — content schema v3 overview

Schema **v3** is a breaking bump over v2. The app is not yet published, so v2 runtime
compatibility is intentionally not preserved.

## v3 = v2 readingSynthesis + personalizedReadings.arcanaSignature

v3 keeps the entire v2 `readingSynthesis` engine **conceptually unchanged** and adds one new
top-level bundle key, `personalizedReadings`.

- `readingSynthesis` retains its own internal `schemaVersion: 2`, its `*_v2.json` source files,
  and its `combinationRules` / `triadRules` / `orientationRules` / `templates` shape. Its rules
  are documented in **`rule_schema_v2.md`**, which remains the authority for drawn/random
  readings. Nothing there was renamed.
- `personalizedReadings` is new (module `schemaVersion: 1`) and currently contains the
  **Arcana Signature** module, documented in **`arcana_signature_schema.md`**.

So the bundle/manifest envelope moves to 3 while the synthesis engine inside it stays at 2.

## Bundle root keys (v3)

```
schemaVersion        // 3
contentVersion       // "v3-<hash>"
locale
deckId
deckName
cards
readingTypes
readings
readingSynthesis     // unchanged from v2 (internal schemaVersion: 2)
personalizedReadings // NEW: { schemaVersion: 1, arcanaSignature: {...} }
safety
```

## Manifest (v3)

```
schemaVersion: 3
contentSchemaVersion: 3
latestContentVersion: "v3-<hash>"
...
features:
  arcanaSignature:
    enabled: true
    moduleSchemaVersion: 1
    delivery: "inside_locale_bundle"
    bundlePath: "personalizedReadings.arcanaSignature"
    requiresContentSchemaVersion: 3
bundles: { en|it|es: { version, schemaVersion: 3, url: "bundles/v3-<hash>/...", sha256, sizeBytes } }
```

## Flutter handoff

The app's content gate must move from an exact `contentSchemaVersion == 2` check to accept `3`.
Once updated, existing drawn/random readings work exactly as before (they read the same
`readingSynthesis` block), and the new Arcana Signature feature reads
`personalizedReadings.arcanaSignature`. The birthday → card calculation is implemented in
Flutter using the constants in `personalizedReadings.arcanaSignature.calculation`; this repo only
describes the method and provides localized copy.
