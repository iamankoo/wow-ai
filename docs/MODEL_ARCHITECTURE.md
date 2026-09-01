# WOW Brain model architecture

## Shape: three heads, one base model

A WOW Brain "model version" (`training/models/wow-brain/<version>/`) is not
a single model - it's three independent text-classification heads, each a
full fine-tuned copy of the same base encoder with its own classification
layer:

```
training/models/wow-brain/<version>/
├── intent/    predicts Intent      (17 classes)
├── context/   predicts ContextMode (7 classes)
├── action/    predicts Action      (13 classes)
└── metadata.json
```

`backend/app/providers/llm/local_wow.py:LocalWOWModelProvider` loads all
three at construction time and runs one forward pass per head per request.
This keeps each head simple (a single linear classification layer on top of
the base encoder's pooled output) at the cost of 3x the inference compute
of a single shared-trunk multi-head model. That tradeoff is intentional for
now - see "Future direction" below - and is why the base model choice below
has to stay lightweight: the real per-request cost is three forward passes,
not one.

## v0: prajjwal1/bert-tiny

2-layer, 128-hidden BERT (~4.4M parameters). Chosen for v0 purely to prove
the training pipeline end-to-end on CPU in minutes. It was never claimed to
be production-quality (see `docs/TRAINING.md` "WOW Brain v0 post-mortem").

## v1: distilbert-base-multilingual-cased

Switched base model for a specific, verified reason, not just "bigger is
better": bert-tiny's vocabulary is the stock `bert-base-uncased` vocab -
English-only WordPiece - so Hindi (both Devanagari and, to a lesser extent,
Romanized) had no meaningful representation at all. Verified directly:

```python
>>> BertTokenizer.from_pretrained("prajjwal1/bert-tiny").tokenize(
...     "मैं सो रहा हूँ, कॉल्स संभाल लेना।")
['म', 'स', '##ो', 'र', '##ह', '##ा', 'ह', ',', '[UNK]', 'स', '##भ', '##ा', '##ल', 'ल', '##न', '##ा', '।']

>>> AutoTokenizer.from_pretrained("distilbert-base-multilingual-cased").tokenize(
...     "मैं सो रहा हूँ, कॉल्स संभाल लेना।")
['म', '##ैं', 'स', '##ो', 'रहा', 'ह', '##ू', '##ँ', ',', 'क', '##ॉल', '##्स', 'सं', '##भा', '##ल', 'ले', '##ना', '।']
```

Same input: bert-tiny drops a combining vowel sign as `[UNK]` and fragments
everything else into single characters with no learned Hindi semantics
behind them (it was never pretrained on Hindi). distilbert-multilingual
tokenizes the same text into meaningful multi-character subwords (`रहा`,
`सं`, `भा`, `ल`, `ले`, `ना`) with zero `UNK`s, backed by actual Hindi
pretraining - it's one of 104 languages in its training corpus.

**Size**: 6 transformer layers, 768 hidden, ~135M parameters. That's ~30x
bert-tiny's parameter count, but it's still DistilBERT - a distilled,
CPU-practical model, not a large multilingual model like mBERT-large or
XLM-R-large. It fine-tunes on this dataset's size in minutes on CPU (see
the v1 training run in `training/models/wow-brain/v1/metadata.json` for
actual wall-clock numbers) and single-sequence CPU inference latency is
in the tens-of-milliseconds range per head - practical for a call
assistant's real-time turn-taking budget, at three heads per request.

**Vocabulary**: 119,547 tokens (vs. bert-tiny's 30,522), covering all three
of WOW's target languages (English, Hindi, Hinglish) natively.

This is a deliberate middle step, not a jump to a large model: `google/muril-base-cased`
(Google's India-focused multilingual BERT, transliteration-aware) was
considered and is a reasonable next step if v1's Hindi/Hinglish accuracy is
still the weak point after this dataset expansion, but it's ~238M
parameters (heavier, and not clearly justified until the dataset-quality
and class-imbalance fixes are isolated as variables first).

## Config-driven, no code changes to swap models

`base_model` is a config value (`training/configs/model_config*.yaml`), not
hardcoded - `training/training/train.py` and
`backend/app/providers/llm/local_wow.py` work with any
`AutoModelForSequenceClassification`-compatible checkpoint. Swapping base
models (e.g. to MuRIL, or a GPU-trained larger encoder for a future
version) requires only a new config file and a training run, per
`docs/TRAINING.md`.

## Future direction

- **Shared trunk, multiple heads**: run the base encoder once per request
  and attach three small classification heads to the same pooled output,
  instead of three full independent model copies. Cuts inference compute
  ~3x and model storage ~3x. Not done for v1 because it's an architecture
  change independent of the dataset/training fixes v1 needed to validate
  first - see `docs/TRAINING.md` for why v1 stayed focused on data quality,
  class balance, and the Hindi tokenization fix.
- **MuRIL or a larger multilingual encoder**, if Hindi/Hinglish accuracy
  remains the specific bottleneck after v1's evaluation (see
  `training/evaluation/latest_report.json` per-language breakdown).
