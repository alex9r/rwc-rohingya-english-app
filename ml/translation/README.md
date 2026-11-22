# ml/translation

Dictionary-first Rohingya ↔ English translator, with optional LLM fallback for unsupported phrases.

## Use
```python
from ml.translation import translate
translate("Hello", "en->roh")
# source=dictionary, verification_status=approved
```
- Directions: `"en->roh"` or `"roh->en"`
- Status: `ok`, `uncertain`, or `failed`
- Each result includes `source` (dictionary / gemini / …) and `verification_status` (`approved` or `pending_review`)
- Ambiguous matches (e.g. `gom` → Good/Fine) return `uncertain` with an `alternatives` list

## LLM fallback
Set `TRANSLATION_PROVIDER` to `gemini`, `openai`, or `anthropic` (plus that provider’s API key/model in `.env`). Misses are saved to `data/pending_translations.json` as `pending_review` and labeled with the provider so they aren’t treated as approved.

## Review / approve
```
python -m ml.translation.review_translations list
python -m ml.translation.review_translations approve <ID> --reviewer "Name"
python -m ml.translation.review_translations approve <ID> --reviewer "Name" --translation "correction"
python -m ml.translation.review_translations reject <ID>
```
Approve moves the entry into `data/approved_translations.json` (loaded with the dictionary) and keeps the original `source`.

## Test
```
python -m ml.translation.run_tests --reverse
```

## Status
- LLM fallback + review/approve flow: working
- Computer-made translations are labeled (`source` + `pending_review`)
- Approved translations move into the dictionary
- Pending file has **not** been reviewed by a Rohingya speaker yet
