# Training a symbol detector

Symbol libraries cover drawing styles you have already reviewed. A trained model covers the rest: it proposes symbols on a new client's drawings so the first study in a new style starts from proposals, not from a blank page. Training runs on your laptop's RTX 3070; inference runs on any CPU.

## 1. Build the dataset

The best source is your past studies, imported from Bluebeam (user guide section 5), reviewed, and with pages marked reviewed.

- Mark a page reviewed only when every countable symbol on it is boxed and correct. Bluebeam studies usually mark only the items in scope; use "find the ones left unmarked" and review the proposals before marking the page.
- Aim for 100 to 200 reviewed sheets across at least five clients or drawing styles. [Estimate]
- Keep one or two whole clients out of training as an unseen-style test set (a separate project).

Export: Training > Export dataset (or `spectra-cli export-dataset reviewed\*.spectra.json --out D:\spectra\datasets\v1 --reviewed-only`). Defaults: 200 dpi, 512 px tiles, 128 px overlap. At 200 dpi a 6 mm valve is about 47 px. Splits are per sheet; the export folder has `train`, `valid` and `test` in RF-DETR's COCO layout and a `dataset.json` with the class list, settings and a content hash.

## 2. Train

One-off setup (internet needed once for PyTorch and the pretrained weights; no drawing data is uploaded):

```bash
cd training
uv sync
```

Train RF-DETR Small (Apache-2.0) at 512 px:

```bash
uv run train_rfdetr.py --dataset D:\spectra\datasets\v1 --out D:\spectra\models\v1
```

Defaults fit an 8 GB GPU: batch 4, gradient accumulation 4 (effective batch 16), 60 epochs with early stopping, seed 42. Use `--size medium` with a 576 px dataset export for higher accuracy if memory allows.

Time on an RTX 3070 [Estimate]: about 100 tiles with symbols per A1 sheet, so 100 sheets give about 10,000 tiles. At 15 to 30 tiles/s, 40 epochs take 4 to 7 hours, an overnight run. On a CPU the same run would take about a week, so use the GPU.

The output folder holds `model.onnx` and `model_card.json` (classes, resolution, dpi, training settings, dataset hash).

## 3. Evaluate and use

- In Spectra, open the unseen-style test project and run Training > Evaluate detection, ticking only Trained model. Or: `spectra-cli evaluate test.spectra.json --model D:\spectra\models\v1`.
- The report gives, per class, precision, recall, AP50 and count error, plus the two numbers that matter: **kept without edit** (target 90 %) and **found**.
- Use the model through Detect…, Trained model. Its detections arrive as proposals, snapped to the strokes, and never duplicate library matches.

Library matches on known styles are exact; the model is for unknown styles. As you review studies in a new style, build a library for it too.
