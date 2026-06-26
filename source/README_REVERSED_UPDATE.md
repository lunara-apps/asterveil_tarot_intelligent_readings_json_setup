# Asterveil Tarot — English reversed card content update

This pack updates the English card JSON files with an optional `reversed` block for every card.

## What changed

Each card now has:

```json
"orientationSupport": {
  "upright": true,
  "reversed": true
},
"reversed": {
  "keywords": [],
  "tags": [],
  "toneTags": [],
  "meanings": {
    "general": { "summary": "", "advice": "" },
    "love": { "summary": "", "advice": "" },
    "career": { "summary": "", "advice": "" },
    "money": { "summary": "", "advice": "" },
    "growth": { "summary": "", "advice": "" }
  },
  "positions": {
    "message": {},
    "situation": {},
    "past": {},
    "present": {},
    "future": {}
  },
  "journalPrompts": {
    "general": [],
    "love": [],
    "career": [],
    "money": [],
    "growth": []
  }
}
```

## Suggested app rule

If the drawn card is reversed and `card.reversed` exists, use:

- `card.reversed.meanings[readingType]`
- `card.reversed.positions[position][readingType]`
- `card.reversed.journalPrompts[readingType]`
- `card.reversed.tags` for reversed-specific combination rules

If the drawn card is reversed but `card.reversed` does not exist, fall back to the upright fields.

## Recommended launch behavior

Reversals are valid in tarot, but not every reader uses them. For Asterveil, consider:

- default: reversed cards disabled
- user setting: "Use reversed cards"
- probability when enabled: 25%–35%, not 50%, to keep the app gentle and beginner-friendly

## Local update commands

Copy these five files over your repository's English card files:

```powershell
cd "D:\Documents\Project\Github Public Projects\asterveil_tarot_intelligent_readings_json_setup"

# copy files into:
# source\en\cards\major_arcana.json
# source\en\cards\cups.json
# source\en\cards\wands.json
# source\en\cards\swords.json
# source\en\cards\pentacles.json

python scripts\build_bundle.py
git status
git add source\en\cards docs
git commit -m "Add English reversed tarot meanings"
git push
```
