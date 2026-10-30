# Data requests

Spectra was built and tested on synthetic CAD drawings, because client drawings cannot leave your machine. These checks close the gap. Each one runs locally and asks only for summary numbers or short text back, never drawings.

## 1. Bluebeam import on past studies (most valuable)

Run on three to five past studies from different clients:

```bash
uv run spectra-cli import-bluebeam D:\check\study1.spectra.json D:\past\study1\*.pdf --csv D:\past\study1\markups.csv
```

Send back:

- the printed summary per drawing (items imported, how many snapped to symbols, how many kept at the markup position);
- any line listing "Labels with no class" (label text only);
- any "count differs" lines from the CSV reconciliation;
- the header row of the Markups List CSV (column names only).

Then open the project in Spectra, look at a few pages and tell me whether boxes sit on the right symbols. If snapping fails on a symbol type, say which type and how the markups were placed (on the symbol, beside it, a circle round it).

## 2. Line numbers and SHX text

On one drawing per client, after import, open the Results tab and count the "has no size" issues. If many items lack sizes, send three or four example line numbers as they appear on the drawing (text only, for example `6"-P-1001-A1A`). Say whether line numbers are selectable text in a PDF viewer; if they are not, they are SHX strokes.

## 3. Frequency table basis

Confirm that the Steel Pipes rows in `src/spectra/assets/iogp_434-01_2019.csv` are per metre per year, and whether you count pipe length per section. Everything else is taken as correct, as you said.

## 4. Conventions per client

List any client whose conventions differ from the defaults: two flanged joints per valve, check valves as manual valves, relief valves as actuated valves, instrument connections in their own category with no implied flanges and a 25 mm tapping size. They can then ship as presets.

## 5. Library detection on a fresh study

Build a library from one reviewed past study (`spectra-cli build-library ... --name ClientA`), then on a new study from the same client run Detect, review, and send the status-bar figure "Kept unchanged: x % of n automatic", or the Training > Evaluate summary (two percentages and the per-class table).

## 6. First training run

When you have about 100 reviewed sheets: export a dataset, train (docs/training.md) and send the last 30 lines of the training output plus the evaluation table on a client held out of training.

## 7. Speed on your laptop

Report the time to open your largest A0 sheet and to run Detect with a library on it. Above 10 s per sheet is worth a look.
