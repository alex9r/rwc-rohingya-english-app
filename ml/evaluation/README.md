# ml/evaluation

Analysis scripts for the Rohingya speech data and for the ASR models we might
build on. None of this ships in the app. Findings are in
[`docs/whisper-evaluation.md`](../../docs/whisper-evaluation.md).

```bash
pip install -r ml/evaluation/requirements.txt
```

## Read this before running anything

Whisper `small` and `medium` collapse into a repeated syllable whenever Bengali
is forced. They do it on Rohingya audio, on clean English speech, and on real
Bengali speech. So a forced-Bengali failure at those sizes tells you nothing
about Rohingya.

Every script that forces a language runs a TTS control in that language first
and says whether it passed. If the control fails, the results are not evidence.
I lost most of a day to this, so the control is built in rather than optional.

`large-v3` passes the Bengali control and behaves completely differently.

## Getting the audio

The VOA Rohingya corpus is public domain (17 USC 105), roughly 390 hours across
14 WebDataset shards, about 830 MB each. Two shards is a reasonable sample.

```python
from huggingface_hub import list_repo_files, hf_hub_download
from pathlib import Path

out = Path.home() / "voa_rhg"
tars = sorted(f for f in list_repo_files("freococo/rohingya_asr_audio",
                                         repo_type="dataset")
              if f.endswith(".tar"))
for f in tars[:2]:
    hf_hub_download("freococo/rohingya_asr_audio", f,
                    repo_type="dataset", local_dir=str(out))
```

Then extract one: `tar -xf ~/voa_rhg/train/rohingya-00000.tar -C ~/voa_rhg/x0`

The audio is not in this repo. Every script defaults to `~/voa_rhg/x0` and
takes `--clips` to override, or set `RWC_VOA_CLIPS`.

## Scripts

`profile_shards.py` reads the JSON sidecars and reports clips, hours, duration
distribution, date coverage and programme codes per shard, then extrapolates to
the full corpus. Extracts only the JSON, so the audio stays packed.

```bash
python -m ml.evaluation.profile_shards
```

`whisper_eval.py` samples one clip from each of N broadcasts and decodes each
three ways: forced Bengali, forced English, auto-detected. Greedy at
temperature 0, because the default temperature fallback drifts toward random
sampling on audio the model cannot handle and gives different output every run.
Writes after each clip, so it is resumable.

```bash
python -m ml.evaluation.whisper_eval --model large-v3
python -m ml.evaluation.whisper_eval --model small --n 10
```

On an M2 with 8 GB, `large-v3` takes 2 to 3 minutes per clip on CPU. Twenty
clips is about an hour.

`ident_check.py` transcribes clip 000001, the broadcast opening, which says
"Voice of America, Washington". The corpus has no transcripts, so this is the
only clip where output can be checked against known words. It romanizes the
output so you can spot the target words inside Bengali script.

```bash
python -m ml.evaluation.ident_check
```

## What came out of it

`large-v3` forced to English transcribes the ident exactly. Forced to Bengali
it produces Rohingya phonetics in Bengali script, and the same sounds come back
across Latin, Bengali and Devanagari on the same clip, which is hard to explain
as hallucination. One clip carries `COP27` and the word for loss on a broadcast
dated the day after COP27 opened.

Language detection is unreliable at every model size, median confidence 0.57 on
`large-v3`. Average log-probability on a forced-English pass separates languages
much better: English content sits near -0.2, Rohingya between -1.0 and -1.4,
with no overlap.

Full writeup and caveats in
[`docs/whisper-evaluation.md`](../../docs/whisper-evaluation.md).

## Not done

- 12 of 14 shards unprofiled
- No speaker has checked a transcript, so there is no accuracy measure
- MMS (`facebook/mms-1b-all` with the `rhg` adapter) has real Rohingya support
  and has not been evaluated here. It should be.
- `large-v3` on CPU is far too slow to ship. Latency on smaller models untested.

## A note on the romanizer

`common.romanize` maps Bengali and Devanagari to Latin crudely, so you can
eyeball whether a word is present without reading the script. It is not a
correct transliteration and should not be quoted as one.
