# Spectra

P&ID parts counting for quantitative risk assessment (QRA). Spectra finds valves, flanges, instruments and equipment on CAD P&IDs, lets you review them quickly, groups them into isolatable sections and calculates release frequencies by hole size from IOGP Report 434-01 (2019). It runs entirely offline; no drawing leaves the machine.

## How it detects symbols

CAD P&IDs are vector PDFs: every copy of a symbol is drawn with identical strokes. Spectra uses that directly.

| Engine | What it does | Needs |
|---|---|---|
| Snap | Click a symbol and the box fits its strokes exactly | Nothing |
| Find similar | One example finds every copy across the drawing set, at any right-angle rotation or mirrored | One example |
| Symbol library | Reusable per-client templates; detects all known symbols in seconds per sheet | Built from reviewed items or Bluebeam markups |
| Bluebeam import | Turns past Bluebeam Count markups (type and size in the label) into snapped items, learns the symbols, and finds the ones left unmarked | Your marked-up PDFs |
| Trained model (optional) | RF-DETR detector for drawing styles no library covers; proposals only | A dataset exported from Spectra and a local GPU |

Sizes come from the item, a class default (instrument tapping), the line number printed along the pipe, or the section's line size, in that order. Every number in the Excel report traces back to drawing, page and position.

## Install and run (Windows)

1. Install [uv](https://docs.astral.sh/uv/).
2. In the repository folder:

```bash
uv sync
uv run spectra                 # the application
uv run spectra-cli --help      # batch tools: Bluebeam import, libraries, datasets, evaluation, reports
```

Try it without client data: Help > Open demo drawing (a synthetic P&ID with Bluebeam-style markups).

A stand-alone `Spectra.exe` can be built with `uv run --with nuitka build.bat`.

## Documentation

- [User guide](docs/user-guide.md): workflows, review keys, sections, conventions, reports.
- [Training a model](docs/training.md): dataset export and training on a local NVIDIA GPU.
- [Data requests](docs/data-requests.md): what to run on your drawings and report back.
- [Technical review and plan](docs/spectra-review.md): the October 2026 review, and what changed after it.

## Project layout

```
src/spectra/
  core/        Qt-free engine: PDF access (pdfdoc), geometry, vectors and snapping,
               template matching, library, Bluebeam import, sizes and line numbers,
               taxonomy, IOGP 434-01 frequencies, project files, reports,
               ONNX detector, dataset export, evaluation
  gui/         PySide6 application (light theme, Inter)
  cli.py       spectra-cli
  assets/      IOGP 434-01 table (CSV plus a JSON note of source and units), icon
training/      separate uv project: RF-DETR training for a local GPU
tests/         pytest suite on synthetic CAD drawings (no client data)
```

## Development

```bash
uv run pytest                  # 61 tests, about 5 s
```

Tests generate their own synthetic P&IDs. Never commit client drawings, projects, datasets or models; `.gitignore` excludes them.

## Licences

Spectra is MIT. Everything it ships with is permissive or weak copyleft, chosen so internal use needs no commercial licence:

| Component | Licence |
|---|---|
| PDFium via pypdfium2 | Apache-2.0 / BSD-3-Clause |
| pypdf | BSD-3-Clause |
| NumPy | BSD-3-Clause |
| ONNX Runtime | MIT |
| openpyxl | MIT |
| Pillow | MIT-CMU |
| PySide6 (Qt) | LGPL-3.0, dynamically linked |
| Inter font | SIL OFL 1.1 |
| RF-DETR and PyTorch (training only, separate environment) | Apache-2.0, BSD-3-Clause |

Spectra 1.x used PyMuPDF and the Roboflow cloud API; both are gone. PyMuPDF and Ultralytics YOLO are AGPL-3.0 and are deliberately not used.
