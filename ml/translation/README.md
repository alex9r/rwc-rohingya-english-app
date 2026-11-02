# ml/translation

Phrase-lookup translator: Rohingya ↔ English. No LLM yet; it only returns phrases already in `data/`.

## Use
```python
from ml.translation import translate
translate("Take your pills.", "en->roh")
# {"translation": "Tua*r bori lo.", "status": "ok", "confidence": 1.0}
```
- Directions: `"en->roh"` or `"roh->en"`
- Status: `ok`, `uncertain` (no good match, translation is `None`) or `failed` (bad input)
- Confidence: 0–1 match score, not a correctness score

## Test
Run from the repo root:
```
python -m ml.translation.run_tests --reverse
python -m ml.translation.run_tests --file a.csv b.json
```
Add tests to `tests.csv` (`english, rohingya, reverse`). Leave `rohingya` blank to expect `uncertain`. Misses go to `failures.csv`.

## Status
- David's phrases are treated as the verified set.
- Nothing has been checked by a native speaker.