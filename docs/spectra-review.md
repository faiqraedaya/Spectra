# Spectra: technical review and next-stage plan

| Item | Value |
|---|---|
| Date | 30 October 2026 |
| Code reviewed | `main` at commit `f4ebfa4` (app version string 1.2.1, `src/spectra/analyser/config/settings.py:9`) |
| Scope | Whole repository and its git history. No code was changed. |
| Licence and source checks | Licence files fetched from GitHub on the review date. arXiv, Zenodo, gnu.org and ultralytics.com could not be reached from the review environment, so claims that depend on them are marked. |

> **Update, later on 30 October 2026: decisions taken and Spectra 2.0 built.** The review below is kept as written. Your answers to its open questions changed the plan; this note records how. Commit references are on branch `claude/spectra-v2`.
>
> **Decisions.** Q1: the `test/` files were removed from every commit and the history force-pushed (ask GitHub Support to purge cached views of the old commits, since GitHub can still serve them by hash). Q2: all drawings are CAD vector PDFs, with real text or SHX. Q3: training happens on your RTX 3070 laptop. Q4: local training on client drawings is allowed. Q5 and Q6: permissive licences only, internal use. Q7: IOGP 434-01 (2019) only. Q8: two flanges per valve, check valves as manual valves, relief valves as actuated valves, instrument connections in their own category. Q9: hundreds of pages of Bluebeam point markups exist. Q10: Roboflow dropped. Q12: "reliable" means 90 % of detections need no edit.
>
> **What changed in the plan.**
> 1. *Vector-first detection replaces ML as the main engine.* With 100 % CAD vector drawings, every copy of a symbol is drawn with identical strokes. Spectra 2.0 snaps clicks to symbol strokes and matches symbol templates under the 8 right-angle rotations and mirror images. On the synthetic test set this is exact (every symbol found, no wrong matches); on a dense A0 test sheet (111,000 strokes) an 11-symbol library runs in about 3 s. A trained model (RF-DETR, section 2) remains, for drawing styles no library covers.
> 2. *Bluebeam markups become the dataset.* Count markups store one vertex per counted item in the PDF (`/Vertices`), with type and size in `/Label`. Spectra imports them, snaps each point to the symbol under it to get an exact box, builds symbol templates from them and proposes the symbols left unmarked. That turns past studies into libraries and training labels without re-annotating.
> 3. *PyMuPDF replaced* by pypdfium2 (Apache-2.0/BSD-3) and pypdf (BSD-3), following the permissive-only decision. Ultralytics is not used.
> 4. *The 1.x code was replaced*, not repaired. Defects D1 to D18 are gone by construction: geometry is stored in display-space PDF points, items have stable IDs, edits are undoable commands, sections are page-aware, the frequency look-up uses continuous bands and reports what it cannot cost, and the API key and temp PNGs no longer exist.
>
> **Roadmap status.** Phase 1 (local detection with an annotation loop) is delivered and goes further than planned: vector snapping, find similar, libraries, Bluebeam import, review workflow, dataset export, evaluation, the training project and the Excel report. Phase 2 (dataset growth) now depends on your data, per [data-requests.md](data-requests.md). Phase 3 is partly delivered: line numbers are read from the text layer (and AutoCAD SHX comments) to size items; OCR for SHX strokes is not done. Tags are read from bubbles and nearby text. Phases 4 and 5 are partly delivered: a first vector pipe tracer joins strokes at ends and tees (not at crossings) and proposes isolatable sections split at tagged isolation valves, exact on the synthetic set. Still to do: line jumps, pipes drawn through valves, off-page connector pairing across sheets, and validation on your drawings.

## How to read this document

Each claim carries one of these labels where it matters:

- **[Fact: code]** checked in this repository. File and line references are to commit `f4ebfa4`.
- **[Fact: run]** checked by running the code in the review environment.
- **[Fact: source]** checked in a primary source (licence file, README, official page), linked.
- **[Secondary]** from a secondary source that I could not check against the primary one.
- **[Assumption]** my inference; it needs confirming.
- **[Estimate]** an engineering estimate with the basis stated.
- **[Calc]** a calculation shown in the text.

This is an engineering review. The licence sections are not legal advice; anything you rely on commercially should go past Monaco's legal or IT governance.

## Summary

1. The current app is a usable viewer and manual parts-count tool, but its data layer is not fit to carry an annotation loop or a graph. Detections are stored in pixel coordinates of whichever render scale happened to be cached, edits are routed by list index into the wrong list, sections ignore the page, and two frequency look-up defects change results. These must be fixed first, inside Phase 1.
2. The local YOLO work does not exist in the code. The only trace is an 11-line scratch script, deleted in May 2026.
3. The poor model accuracy has two causes that a new model alone will not fix: whole-sheet inference shrinks a 6 mm valve to about 5 px, and the hosted model was probably trained on a synthetic dataset. Tiled inference at a fixed DPI fixes the first; your own reviewed data fixes the second.
4. Recommended model route: a permissively licensed detector (RF-DETR, Apache-2.0, as first choice; D-FINE or YOLOX as the comparison), trained on tiles on a local GPU, exported to ONNX and run in Spectra with ONNX Runtime. Ultralytics YOLO is only sensible with a paid Enterprise licence. PyMuPDF, which Spectra already depends on, has the same AGPL question.
5. Most client P&IDs from CAD systems are vector PDFs. For those, text and lines can be read exactly from the PDF, which makes tag recognition and line tracing far more tractable than raster methods. Confirming what fraction of your drawings are vector is the most valuable single fact for planning Phases 3 and 4.
6. Phase 1 (foundations, local model, annotation loop) is about 40–55 developer-days plus annotation time **[Estimate]**. The full roadmap to isolatable sections and frequencies is about 130–195 developer-days, plus 50–100 h of annotation **[Estimate]**.

---

## 1. Current state

### Conclusion

Spectra is a single-process PySide6 app in which the main window object is the shared state, and most logic reaches into it directly. The viewer and section-drawing interaction are the strongest parts. The detection data model is the weakest: it has no stable identity, no coordinate system independent of rendering, and no record of where a detection came from. That blocks the annotation loop, which needs exact, reproducible labels, and the graph, which needs stable IDs and geometry. Several defects already corrupt data silently. None of this needs a rewrite; it needs a data layer under the existing GUI.

### 1.1 Architecture and module responsibilities

| Module | Responsibility | Key functions |
|---|---|---|
| `main.py`, `src/spectra/analyser/main.py`, `core/app.py` | Entry points; create `QApplication`, splash, main window | `app.main()` |
| `core/main_window.py` | `Spectra(QMainWindow)`: owns all state (`detections`, `sections_list`, `undo_stack`, `redo_stack`, `api_key`, `confidence`, `overlap`), builds panels, forwards menu actions to managers, exports results CSV | `__init__` (l.64), `_apply_pending_updates` (l.396), `export_results_to_csv` (l.515) |
| `core/analysis_manager.py` | Starts the Roboflow thread, maps class names, merges results with manual detections | `run_analysis` (l.18), `on_analysis_complete` (l.65) |
| `core/detection_manager.py` | Cut, copy, paste, edit, delete, manual add, undo/redo, context menus | `add_manual_detection` (l.153), `on_bbox_changed` (l.248), `undo` (l.230) |
| `core/project_manager.py` | New/open/save project JSON; open PDF | `save_project` (l.102), `open_project` (l.56) |
| `detection/roboflow.py` | `RoboflowAnalysisThread(QThread)`: one hosted-API call per page image | `run` (l.27) |
| `detection/types.py` | `Detection` dataclass and dict (de)serialisation | `to_dict`, `from_dict` |
| `detection/categories_map.py` | Two maps: Roboflow class ID → object name; object name → frequency category | `get_category` (l.134), `get_frequency_category` (l.63) |
| `sections/sections.py` | `Section`, `Polyline`; section CRUD; assignment of detections to sections by polyline–box intersection | `assign_objects_to_sections` (l.608), `polyline_intersects_bbox` (l.696) |
| `utils/frequency.py` | Loads `assets/data/frequency.csv`; sums frequencies per section by hole size | `FrequencyTable.lookup` (l.45), `calculate_section_frequencies` (l.61) |
| `utils/spatial_index.py` | R-tree for section look-up when there are more than 10 sections | `SpatialIndex.get_section_for_bbox` (l.76) |
| `utils/ui_updater.py` | Debounced, coalesced table refreshes via a global `UIUpdateManager` | `request_update`, `request_group_update` |
| `utils/performance_monitor.py` | Timing decorator | `monitor_performance` |
| `ui/pdf_viewer.py` | `PDFViewer(QLabel)`, 1,856 lines: PDF rendering and page cache, zoom/pan, drawing and hit-testing of boxes and polylines, drag/resize, polyline editing, coordinate conversion | `_render_page_to_cache` (l.427), `get_page_image_paths` (l.1208), `widget_to_image_coords` (l.1469) |
| `ui/panels/*.py`, `ui/dialogs/*.py`, `ui/menus.py` | Panels (viewer, sections, objects, results), detection and section dialogs, menus | — |

All of the above is **[Fact: code]**; paths are relative to `src/spectra/analyser/`.

### 1.2 Data flow

```
Open PDF ─► PDFViewer.load_pdf ─► PyMuPDF page.get_pixmap(scale s) ─► PNG in temp dir ─► QPixmap cache
Run analysis ─► get_page_image_paths (cached PNGs, or render at current-zoom scale)
             ─► RoboflowAnalysisThread: model.predict(PNG) on Roboflow cloud, project "schemas" v1
             ─► Detection(name="1".."32", bbox in PNG pixels, page_num)
             ─► on_analysis_complete: get_category → "Manual Valve", "Flange", ... ; replaces model detections
             ─► assign_objects_to_sections (polyline crosses box → section)
             ─► Objects table, viewer overlay
Results tab  ─► calculate_section_frequencies: get_frequency_category(name) × lookup(category, line size) × count
             ─► Results table ─► CSV
Save project ─► JSON: sections, detections, confidence, overlap, api_key   (no PDF path or hash)
```

**[Fact: code]**

### 1.3 What is solid

- The viewer interaction: zoom about the cursor, pan, box drawing, drag and resize handles, polyline drawing and point editing (`ui/pdf_viewer.py`). This is the hardest part of a review GUI to get right, and it works. **[Fact: code]**
- Inference already runs off the GUI thread and talks back only through queued signals (`detection/roboflow.py`, `core/analysis_manager.py:38-49`). The pattern carries over directly to a local model. **[Fact: code]**
- `Detection` is a plain dataclass with dict round-tripping, and the project file is plain JSON. Both are easy to extend and version. **[Fact: code]**
- The frequency table is data, not code (`assets/data/frequency.csv`), and its hole-size bands (1–3, 3–10, 10–50, 50–150, >150 mm) match the IOGP 434-01 bands. **[Fact: code]**; the IOGP band match is **[Assumption]**, to be checked against the report.
- Section assignment by "polyline crosses box" is a sensible manual proxy for "this component is on this line".
- The project is now on uv with a lock file and Python 3.13 (`pyproject.toml`, `uv.lock`). **[Fact: code]**

### 1.4 Defects and fragile areas

Ranked by effect on results. All **[Fact: code]** unless marked.

| # | Issue | Where | Effect |
|---|---|---|---|
| D1 | Edit operations use an index into the viewer's per-page list (`PDFViewer.detections`, filtered to the current page at `pdf_viewer.py:623`) as if it were an index into the full list `main_window.detections`. | `bbox_changed` emit `pdf_viewer.py:1164,1174` → `detection_manager.py:248-251`; `bbox_right_clicked` → `cut/copy/edit/delete_detection` | On page 2 onwards, or with a filter set, dragging a box also overwrites another detection's box, and edit/delete/cut act on the wrong object. |
| D2 | Detection boxes are stored in pixels of the rendered PNG, and the render scale depends on the zoom at render time (0.75, 1.0, 1.5 or 2.0, `_calculate_optimal_scale_factor`, l.234). Preloaded pages render at 1.0 (l.312). Cache eviction re-renders at whatever the zoom is then. | `pdf_viewer.py:234-253, 299-334, 427-463, 1208-1230` | Boxes can be misplaced by a factor of up to 2.7 after a page is re-rendered, and pages in one analysis run can be analysed at different scales. Project files carry no scale, so saved coordinates are ambiguous. |
| D3 | Sections drawn on any page are stored as page 1. `add_section_with_points` reads `getattr(self, 'current_page', 1)` from the main window, which has no such attribute. | `sections/sections.py:306, 317` | Section polylines drawn on page 2+ appear on page 1 only. |
| D4 | Section assignment ignores the page. `get_section_for_bbox_optimized` receives only the box. | `sections/sections.py:565-601, 667`; `utils/spatial_index.py` | A detection on page 3 is assigned to a section whose polyline is at the same coordinates on page 1. Combined with D3, multi-page drawings give wrong section totals. |
| D5 | Frequency look-up falls back to the largest size row when a line size falls between integer bands, e.g. 50.5 mm returns the 601–9,999 mm row. | `utils/frequency.py:45-58` | **[Fact: run]** checked with the shipped CSV: 50.5 mm and 100.5 mm both return the 601–9,999 mm row for flanged joints. Equipment rows start at 50 mm, so a 25 mm strainer also takes the largest row. |
| D6 | Roboflow class 20 "Expander" (a pipe reducer/expander fitting, **[Assumption]**) maps to the frequency category "Expanders", which in the IOGP data set is turbo-expander machinery. "Strainer" maps to "Filters" (filter vessels). | `detection/categories_map.py:43, 38` | Each reducer adds about 2.3 × 10⁻³ /yr in the tiny-hole band, roughly 500 times a flanged joint (frequency.csv rows "Expanders" and "Flanged Joints"). **[Fact: code]** for the values. |
| D7 | "Piping" detections are counted as items and multiplied by the "Steel Pipes" frequency, which in IOGP 434-01 is per metre-year **[Assumption]**, to confirm against the report. | `utils/frequency.py:61-112` | Pipe contribution is dimensionally wrong unless the user enters length as "count". |
| D8 | Renaming a section in the table sets its name to `None`: `section.name = item.setText(new_name)`. | `sections/sections.py:259` | Section loses its name; detections become unassigned. |
| D9 | Above 10 sections, the R-tree path picks the oldest intersecting section; below 10, the list path picks the newest. | `utils/spatial_index.py:88-105` vs `sections/sections.py:583` | Assignment changes when the eleventh section is added. |
| D10 | The category filter lists frequency categories ("Manual Valves") but model detections are named with object names ("Manual Valve"). | `ui/panels/objects_panel.py:51-59`, `core/detection_manager.py:49` | Filtering by category never shows model detections. |
| D11 | Silent exclusions: detections with no frequency category ("Spectacle Blind", "Unknown") or no line size are skipped without warning. | `utils/frequency.py:87-94` | Section totals can be low with no indication. **[Fact: run]** for the category mapping. |
| D12 | Undo covers only manual adds, and stores shallow list copies, so edited objects are not restored. | `core/detection_manager.py:178, 230-246` | Undo is unreliable. |
| D13 | The Roboflow API key is saved in plain text in every project file. | `core/project_manager.py:118` | Key leaks when project files are shared. |
| D14 | Project files do not record the PDF path, PDF hash, or render scale; opening a project does not reopen the PDF, and opening a PDF clears detections but not sections. | `core/project_manager.py:56-100, 132-139` | A project cannot be tied reliably to its drawing. |
| D15 | Rendered pages of client drawings are written as PNG files to the system temp folder. | `pdf_viewer.py:263, 320, 449` | Confidential images on disk; deleted on close, but left behind after a crash. |
| D16 | Pillow is imported directly (`pdf_viewer.py:11`) but is only a transitive dependency of `roboflow`. | `pyproject.toml` | Removing Roboflow will break PDF rendering. |
| D17 | README is out of date (Python 3.7+, `requirements.txt`, `run_spectra.py`), and Help lists Ctrl+P for Open PDF while the menu uses Ctrl+Shift+O. | `README.md`, `core/main_window.py:506`, `ui/menus.py:63` | Minor. |
| D18 | The only test (`tests/test_app.py`) checks the window title. No calculation is tested. | `tests/` | **[Fact: run]** It could not run in the review container (missing `libEGL`); that is an environment issue. |

One more item belongs here because it is not visible in the current tree: commit `a09218c` (20 May 2026) added `test/GeZero Combined P&IDs.pdf` (9.9 MB), `test/image.jpg` and sample project files, and commit `196aa15` deleted them. **[Fact: code]** They remain in git history. If the repository is public and any of these came from a client, the history needs rewriting and GitHub support asked to purge cached views. See open question Q1.

### 1.5 Blockers for the long-term goals

**Coupling between GUI and inference.** Inference is isolated in a `QThread`, which is good, but the model call, class mapping and merge logic are tied to Roboflow and to the main window (`analysis_manager.on_analysis_complete` reaches into `main_window.detections`, `detection_manager`, panels). There is no detector interface, so adding a local model means touching the manager, the thread and the class map at once. **[Fact: code]** Fix: a small `Detector` protocol (`detect(page_image, page_meta) -> list[RawDetection]`) and a pure-Python post-processing module (tiling, merge, class mapping) with no Qt imports, so it can be tested and reused by the training and evaluation scripts.

**How detections are stored.** A flat list of `Detection` objects identified by list position; class stored as a display name string; no ID, no model version, no review state, no history of the original proposal. **[Fact: code]** The annotation loop needs to know which pages are fully reviewed and what the model proposed versus what you accepted. The graph needs stable IDs to reference.

**Coordinate handling.** Image pixels at an unrecorded scale (D2), with a third set of widget coordinates converted ad hoc in several places in `pdf_viewer.py` (`widget_to_image_coords`, inline offset maths at l.736, 1101, 1307, and the polyline drag at l.1046). Fix: store all geometry in PDF points of the unrotated page (the coordinate system PyMuPDF uses for `page.rect`), and convert only at the rendering and inference edges, using one `PageTransform` object that knows render DPI and page rotation.

**Large drawings.** Each page is rendered once at 72–144 dpi and sent whole to the model. **[Fact: code]** The consequence for an A1 sheet:

```
A1 sheet: 841 mm × 594 mm = 2384 pt × 1684 pt              (1 pt = 25.4/72 mm)
Valve symbol ~6 mm; at 72 dpi: 6 / 25.4 × 72 = 17 px
If the hosted model resizes input to 640 px on the long side [Assumption]:
  downscale 640 / 2384 = 0.27  →  valve ≈ 4.6 px
At 144 dpi the rendered image is 4768 px, so the valve is still ≈ 4.6 px after resizing.
```

**[Calc]** Detectors trained on typical data lose most objects below about 10 px, so this alone explains much of the poor accuracy. Rendering at a higher scale does not help while the whole sheet goes through one model input. Tiling does (section 2.2).

**Confidentiality.** Every analysis uploads each page image to Roboflow's cloud (`detection/roboflow.py:47`). **[Fact: code]** This is incompatible with the stated requirement, so the Roboflow path should be removed or disabled for client work once the local model exists.

**Training data source of the current model.** The class map has IDs "1"–"32" (`detection/categories_map.py:87-121`), which matches the 32 symbol classes of the synthetic Dataset-P&ID (Paliwal et al., 2021). **[Assumption]** The hosted "schemas" model was trained on that dataset or a derivative. If so, its poor transfer to real client drawings is expected: the synthetic sheets use one symbol style on a simplified grid ([PID2Graph paper](https://arxiv.org/abs/2411.13929), **[Secondary]**).

**No line, text or graph capability.** Sections are drawn by hand; line size is typed in per section. There is no OCR, line tracing or connectivity anywhere in the code. **[Fact: code]**

### 1.6 Status of the local YOLO work

**Conclusion: not started in the codebase.** **[Fact: code]**

- No module, setting, menu item or dependency for a local model exists in any commit. A search of every commit for `yolo`, `ultralytics`, `torch` and `onnx` in Python files finds only `test/test.py`.
- `test/test.py` (added in `a09218c`, deleted in `196aa15`) is an 11-line script that loads `best.pt` (never committed) with Ultralytics and shows predictions on one image from a local OneDrive path. The same commit added the stock COCO weights `yolov8n.pt` and `yolo11n.pt`, which detect everyday objects, not P&ID symbols.
- The Help text says "Select a Detection Method", but no selector exists (`core/main_window.py:482`).

What is left to finish it is the whole of Phase 1 (section 5): a detector interface, tiled inference with merge, a model file format and loader, a trained model, and settings in the GUI. The data-layer fixes (D1–D4, D14) come first, or the local model will inherit the same coordinate and identity defects.

---

## 2. Model strategy

### Conclusion

Train your own detector locally on tiles cut from reviewed client and public drawings; export it to ONNX; run it in Spectra with ONNX Runtime on the CPU. Use RF-DETR (Small or Medium, Apache-2.0) as the first candidate and benchmark one alternative (D-FINE, Apache-2.0, or YOLOX, Apache-2.0) on the same held-out test set before committing. Keep training in a separate environment and script from the GUI, so the app carries no PyTorch dependency. Use Ultralytics YOLO only if Monaco buys an Ultralytics Enterprise licence; it is the easiest tool to train with, but its licence position is unfavourable for this use.

### 2.1 Detector options

Accuracy columns are about this task after tiling (symbols 30–70 px in a 512–640 px tile), which turns "small objects on large drawings" into ordinary medium-size detection. Published benchmarks are on photographs, not drawings, so none of them predicts P&ID accuracy; only your own test set will.

| Option | Licence | Expected accuracy on tiled P&ID symbols | Training effort | CPU inference (laptop) | Notes |
|---|---|---|---|---|---|
| RF-DETR S/M (`rfdetr`) | Apache-2.0 for N/S/M/L detection **[Fact: source]** | High **[Estimate]**. Vendor reports RF100-VL AP50 86.7 (S) vs 82.3 for YOLO11-S **[Fact: source]**, a vendor benchmark | Low: Python API, COCO-format data, pretrained DINOv2 backbone fine-tunes well on small datasets | Moderate: ~32 M parameters **[Fact: source]**; est. 0.3–1 s per 512–576 px tile **[Estimate]** | Optional ONNX export extra in its `pyproject.toml` **[Fact: source]**. XL/2XL and A/F/P sizes are under Roboflow's PML 1.0, which needs a paid add-on for self-hosting; avoid those. Check that weight download can be done once and then run offline. |
| D-FINE (Peterande/D-FINE) | Apache-2.0 **[Fact: source]** | High **[Estimate]** | Medium: research-repo config files, COCO format | Moderate | Strong COCO results; less packaged than RF-DETR ([arXiv 2410.13842](https://arxiv.org/abs/2410.13842)). |
| DEIM (training method for D-FINE/RT-DETR) | Apache-2.0 **[Fact: source]** | High **[Estimate]** | Medium | Moderate | Faster convergence for DETR-type models ([arXiv 2412.04234](https://arxiv.org/abs/2412.04234)). |
| RT-DETR (lyuwenyu/RT-DETR) | Apache-2.0 **[Fact: source]** | Medium–high | Medium | Moderate | Superseded by D-FINE/DEIM in accuracy. The Ultralytics copy of RT-DETR is AGPL. |
| YOLOX (Megvii) | Apache-2.0 **[Fact: source]** | Medium–high **[Estimate]** | Medium; mature, older (2021) | Fast (S model ~9 M parameters) | Good CPU option if RF-DETR is too slow. |
| YOLO (MultimediaTechLab/YOLO, v9/v7 reimplementation) | MIT **[Fact: source]** | Medium–high | Medium–high; smaller community | Fast | Permissive YOLO, but less mature tooling. |
| Ultralytics YOLO11 / YOLO26 | AGPL-3.0 or paid Enterprise **[Fact: source]** | High **[Estimate]**; YOLO26 adds small-target label assignment (vendor claim) | Lowest: one-line training, built-in tiling-friendly tooling, ONNX export | Fast (S ~9.4 M parameters **[Fact: source]**) | See licence discussion below. YOLO26 launched 14 January 2026 ([Business Wire](https://www.businesswire.com/news/home/20260114168538/en)). |
| torchvision Faster R-CNN | BSD-3 | Medium | Medium | Slow | Baseline only. |

**Why RF-DETR first.** It combines a permissive licence, the simplest training API among the permissive options, good published fine-tuning results on small datasets, and an ONNX export path. Its weakness is CPU speed (larger backbone). If inference per A1 sheet exceeds about a minute on your laptop, YOLOX-S is the fallback. **[Estimate]**

#### Ultralytics AGPL-3.0: what it means for an internal tool

- **The licence text.** AGPL-3.0 obligations are triggered when you convey (distribute) the software, or when you modify it and let users interact with it over a network (section 13). Using unmodified AGPL software privately, without distributing it, triggers no source-release duty under the text itself. **[Fact: source]** for the licence being AGPL-3.0 ([LICENSE](https://github.com/ultralytics/ultralytics/blob/main/LICENSE)); the reading of sections 2 and 13 is mine.
- **Ultralytics' position is stricter.** Its README says the Enterprise licence is for "development and production use … including internal tools, automated workflows, and production deployments, bypassing the open-source requirements of AGPL-3.0" **[Fact: source]** ([README](https://github.com/ultralytics/ultralytics#-license)). Its licence page, as reported by search results, says trained models are covered by AGPL-3.0 by default, "even if you … use YOLO only internally" **[Secondary]** ([ultralytics.com/license](https://www.ultralytics.com/license); [forum reply](https://community.ultralytics.com/t/yolov11-agpl-license-for-on-premises-use/1529)). Whether trained weights are a derivative work under copyright law is unsettled.
- **Distribution is where it bites.** Giving the Nuitka `.exe` (`build.bat`) to colleagues inside the same legal entity is generally not treated as conveying under the FSF's interpretation **[Secondary]**; I could not reach the GPL FAQ to confirm. Giving it to a client, a joint-venture partner or another group company would be conveying: you would then owe recipients the complete corresponding source of Spectra under AGPL-3.0, and Spectra's MIT licence could not apply to the combined program.
- **Practical risk for Monaco.** The risk is less a court case than a vendor licence claim, or a client's software audit asking which licences their deliverables depend on. A tool used to produce QRA deliverables for major operators should have a clean, documentable licence position.
- **Recommendation.** Avoid Ultralytics unless Monaco buys an Enterprise licence. If it does, Ultralytics becomes the lowest-effort option and the rest of this plan is unchanged; the detector sits behind the same interface.

#### PyMuPDF has the same question

PyMuPDF, already a core dependency, is AGPL-3.0 or a paid Artifex commercial licence **[Fact: source]** ([COPYING](https://github.com/pymupdf/PyMuPDF/blob/main/COPYING)). Everything above applies to it too, and it is the library this plan relies on for vector text and line extraction. Options:

1. Accept AGPL for strictly internal use, with a documented decision. Lowest effort.
2. Buy an Artifex commercial licence.
3. Replace it: pypdfium2 (Apache-2.0 or BSD-3-Clause **[Fact: source]**, [REUSE.toml](https://github.com/pypdfium2-team/pypdfium2/blob/main/REUSE.toml)) for rendering, and pdfminer.six (MIT **[Fact: source]**) for vector paths and text. More code for the vector work.

Decide this together with the detector licence (decision D-1.1 in section 5).

### 2.2 Full-size drawings: tiling and merging

**Conclusion.** Render each page at a fixed DPI chosen so the smallest symbol is at least about 30 px; cut overlapping square tiles at the model's input size; run the detector on each tile; map boxes back to PDF points; discard boxes cut by an internal tile edge; merge the rest with class-aware greedy non-maximum merging using intersection-over-smaller; run a second, low-resolution whole-page pass for large equipment. Write this as a small pure-Python module (~150–250 lines **[Estimate]**) with pytest tests, rather than depending on SAHI. SAHI (MIT **[Fact: source]**, [obss/sahi](https://github.com/obss/sahi); Akyon et al., ICIP 2022, [arXiv 2202.06934](https://arxiv.org/abs/2202.06934)) is the reference design and worth reading, but it does not wrap every detector, and owning the code keeps evaluation and inference identical.

**Resolution.**

```
symbol size in pixels   s_px = s_mm / 25.4 × dpi
6 mm valve:   150 dpi → 35 px     200 dpi → 47 px     300 dpi → 71 px
A1 page:      150 dpi → 4967 × 3508 px     200 dpi → 6622 × 4677 px
```

**[Calc]** Start at 200 dpi and test 150 dpi in Phase 1; pick the lowest that holds recall on the smallest classes (instrument connection dots, small check valves).

**Tile grid.**

```
stride  S = T − O              (T = tile size, O = overlap, px)
tiles   n_x = ceil((W − T) / S) + 1,   n_y = ceil((H − T) / S) + 1
Example, A1 at 200 dpi, T = 640, O = 160 (20 mm):
  S = 480;  n_x = ceil(5982/480) + 1 = 14;  n_y = ceil(4037/480) + 1 = 10;  140 tiles
Example, A1 at 150 dpi, same T and O:
  n_x = ceil(4327/480) + 1 = 11;  n_y = ceil(2868/480) + 1 = 7;  77 tiles
```

**[Calc]** The last tile in each row and column is shifted back to end at the page edge, so no tile is padded. Overlap must exceed the largest symbol you want detected whole in some tile; 20 mm covers valves, fittings and instrument bubbles. Equipment larger than the overlap is handled by the low-resolution pass.

**CPU inference time per A1 sheet** at 0.1–0.4 s per tile: 77–140 tiles → about 10–60 s. **[Estimate]** Acceptable for a batch run with a progress bar; tiles can be batched and run in a worker thread.

**Merging detections across tile edges.**

1. Shift each tile's boxes by the tile origin, then convert to PDF points: `x_pt = x_px × 72 / dpi`.
2. Edge filter. For each box, if it lies within a margin `m` (e.g. 4 px) of a tile edge that is not a page edge, mark it truncated. Drop truncated boxes when a non-truncated box of the same class overlaps them with intersection-over-smaller (IoS) ≥ 0.5. The overlap guarantees the neighbouring tile saw the symbol whole.
3. Class-aware greedy non-maximum merging (NMM): sort by confidence; for each box, absorb same-class boxes with IoS ≥ 0.5, taking the union box and the maximum confidence. IoS is used instead of IoU because a truncated box and the full box have low IoU (e.g. 0.4) but high IoS (≈ 1.0).
4. Cross-class conflicts (same location, different class, e.g. gate vs globe valve): keep the higher-confidence class and store the runner-up class and score on the detection for the review UI.
5. Large-object pass: render the whole page with its long side at 1,600–2,048 px, run the same model (or a separate equipment model), keep only classes flagged "large" (vessels, columns, exchangers, pumps, compressors), and merge with step 3.

Unit-test steps 1–3 with synthetic boxes: a box split across two tiles merges to one; two adjacent real symbols stay two; page-edge boxes are kept.

### 2.3 Symbol class list for parts counting

**Conclusion.** Use a two-level taxonomy. The detector learns **visual classes**: what the symbol looks like. A versioned, editable mapping turns visual class plus tag and attributes into an **engineering type**, and engineering type plus size into a **frequency category** in a chosen data set (IOGP 434-01 or HSE HCR). This separation matters because ESD role is not visible in the symbol: an ESDV, an XV and an on/off SDV share the actuated-valve symbol and differ by tag prefix and cause-and-effect role. It also fixes D6 and D7, where a visual name was mapped straight to a frequency category.

Proposed visual classes v1 (append-only IDs; never renumber):

| ID | Visual class | Typical engineering types | Frequency category (IOGP 434-01 naming) |
|---|---|---|---|
| 0 | gate_valve | manual isolation | Manual valves |
| 1 | globe_valve | manual / throttling | Manual valves |
| 2 | ball_valve | manual isolation | Manual valves |
| 3 | butterfly_valve | manual isolation | Manual valves |
| 4 | plug_valve | manual isolation | Manual valves |
| 5 | needle_valve | instrument isolation | Manual valves (small bore) |
| 6 | check_valve | non-return | Manual valves **[Assumption]**; confirm convention |
| 7 | three_way_valve | diverter | Manual or actuated, by actuator |
| 8 | control_valve | control valve (body + actuator) | Actuated valves |
| 9 | actuated_onoff_valve | ESDV, SDV, XV, BDV (role from tag) | Actuated valves |
| 10 | relief_valve | PSV, PRV, TSV | Actuated valves or own category **[Assumption]** |
| 11 | rupture_disc | bursting disc | per study convention |
| 12 | choke_valve | choke | Actuated or manual by actuator |
| 13 | flange_joint | flanged joint (drawn) | Flanged joints |
| 14 | blind_flange | blind | Flanged joints |
| 15 | spectacle_blind | spectacle / spade / spacer | Flanged joints (two joints) **[Assumption]** |
| 16 | reducer | concentric / eccentric reducer | none (welded) or flanged joints if flanged |
| 17 | strainer | Y / basket / temporary strainer | Filters only if a vessel-type filter; else flanged joints |
| 18 | orifice_plate | flow element, restriction orifice | Flanged joints (orifice flanges) |
| 19 | instrument_bubble_field | field instrument | Instrument connections |
| 20 | instrument_bubble_panel | DCS / shared display / PLC | none (no process connection) |
| 21 | instrument_connection | small-bore tapping, sample point | Instrument connections |
| 22 | open_end_vent_drain | vent, drain | Manual valves + flanged joints by rule |
| 23 | vessel_vertical | separator, scrubber, drum | Pressure vessels / process vessel |
| 24 | vessel_horizontal | separator, drum | Pressure vessels |
| 25 | column | column, contactor | Pressure vessels |
| 26 | pump_centrifugal | — | Centrifugal pumps |
| 27 | pump_reciprocating | — | Reciprocating pumps |
| 28 | compressor_centrifugal | — | Centrifugal compressors |
| 29 | compressor_reciprocating | — | Reciprocating compressors |
| 30 | heat_exchanger_shell_tube | — | Shell & tube (shell or tube HC by data) |
| 31 | heat_exchanger_plate | plate / PCHE | Plate heat exchangers |
| 32 | air_cooler | — | Air-cooled exchangers |
| 33 | filter_vessel | — | Filters |
| 34 | pig_launcher_receiver | — | Pig traps |
| 35 | tank | atmospheric tank | per study |
| 36 | off_page_connector | continuation to another sheet | none (graph link) |
| 37 | line_continuation_arrow | flow arrow / tie-in | none |
| 38 | spec_break | piping class break | none (graph attribute) |
| 39 | other_symbol | anything else worth reviewing | none; flagged |

Notes:

- Flanges are often not drawn at every flanged valve. Parts counts therefore need a rules table for **implied components** (for example "flanged valve → 2 flanged joints", "instrument bubble with process connection → 1 instrument connection + 1 root valve"). Keep these rules in a data file per study, visible in the report, and editable. This is a methodology choice you should own, not the model.
- Text classes (tag, line number) are handled by OCR (section 4.1), not the detector.

**Client-specific symbols.**

1. Most client variants mean the same thing as an existing class (a different gate-valve glyph). Keep the class, add examples to training. The model generalises across styles only if the training set spans them.
2. A genuinely new symbol needed for counting becomes a new appended class, trained with roughly 30–100 examples **[Estimate]**, harvested from the client's legend sheet and a few P&IDs.
3. Symbols not needed for counting go to `other_symbol`, so they are visible in review rather than forced into a wrong class.
4. A per-client mapping file (JSON) holds tag regexes and visual-class → engineering-type overrides. The model stays single; the mapping varies by client.

---

## 3. Data and training workflow

### Conclusion

Start from Dataset-P&ID for a bootstrap model, but plan for your own reviewed sheets to be the training set that matters. Build a review mode into Spectra in which the model proposes, you correct, and a page is marked reviewed only when every symbol on it is correct. Export reviewed pages to COCO JSON (and YOLO text if needed) from a master label store in PDF points. Split by drawing and by client at ingestion and never re-split. Evaluate on whole sheets, after tile merging, on a frozen test set that includes clients the model has never seen.

### 3.1 Public datasets

| Dataset | Content | Source | Licence | Status |
|---|---|---|---|---|
| Dataset-P&ID (Paliwal, Jain, Sharma, Vig, "Digitize-PID", ICDAR 2021 workshops) | 500 synthetic P&IDs, 32 symbol classes, with symbol, line and text annotations | [arXiv 2109.03794](https://arxiv.org/abs/2109.03794); Google Drive link via the paper; mirrors on Hugging Face, e.g. [hamzas/digitize-pid-symbols](https://huggingface.co/datasets/hamzas/digitize-pid-symbols) | Not stated in the sources I could reach. Third-party repos describe it as CC BY-SA 4.0 **[Secondary]** | Not confirmed. Check the Drive folder and the paper. Mirrors are third-party re-packagings. |
| PID2Graph (Stürmer, Graumann, Koch, IEEE DSAA 2025) | Synthetic diagrams plus a small real subset (OPEN100), with graph-level labels: symbols and connections | [arXiv 2411.13929](https://arxiv.org/abs/2411.13929); [Zenodo record 14803338](https://zenodo.org/records/14803338) | Described as CC BY-SA 4.0 by third-party repos **[Secondary]** | Not confirmed; Zenodo was unreachable from the review environment. The real part is small (reported as about a dozen sheets **[Secondary]**). Most useful as a line and graph benchmark. |
| SynthPID (2026) | Synthetic P&ID generator and data, evaluated on PID2Graph OPEN100 | [arXiv 2604.16513](https://arxiv.org/abs/2604.16513) | Unknown | Not confirmed; could not read the paper. |
| Roboflow Universe P&ID projects | Many small community datasets | [universe.roboflow.com](https://universe.roboflow.com) | Per project, often CC BY 4.0 **[Assumption]** | Not checked individually. Many appear derived from Dataset-P&ID **[Assumption]**. Download once; never upload client data. |

Notes:

- Share-alike (CC BY-SA) terms on training data raise an unsettled question about whether trained weights must be shared alike. For internal use the practical risk is low, but record which datasets each model used (the model card in 3.2 does this).
- Synthetic data teaches symbol shapes but not real drawing clutter, scan noise or client styles. Expect a bootstrap model trained only on it to perform poorly on client drawings, as the current one does.
- Your own drawings are the main dataset. Before using them, confirm whether client contracts allow using their drawings to train an internal model, and how labels and weights are stored and retained (open question Q4).

### 3.2 Annotation loop inside Spectra

**Data model (master labels, independent of any model or render).**

```python
@dataclass
class Annotation:
    id: str                    # uuid4, stable across edits and saves
    sheet_id: str              # sha256 of the PDF file + ":" + page index
    bbox_pt: tuple[float, float, float, float]   # x0, y0, x1, y1 in PDF points, unrotated page
    class_id: int              # visual class ID from the versioned class list
    source: str                # "model" | "manual"
    status: str                # "proposed" | "accepted" | "corrected" | "rejected"
    confidence: float | None
    model_version: str | None  # model card ID that proposed it
    original: dict | None      # proposed class and box, kept when corrected
    attrs: dict                # tag, size, count, runner-up class, etc.

@dataclass
class SheetState:
    sheet_id: str
    pdf_sha256: str
    page_index: int
    client_code: str           # anonymised, e.g. "C07"
    style_code: str            # drawing style family
    split: str                 # "train" | "val" | "test_in_style" | "test_new_style"; set once
    review_state: str          # "unreviewed" | "in_review" | "reviewed"
    reviewer: str
    reviewed_at: str
    class_list_version: str
```

**Review mode (GUI).**

1. Run the model on a page at a low confidence threshold (e.g. 0.2) so that recall is high; proposals appear in a distinct style.
2. Step through proposals ordered by lowest confidence first (Tab / Shift+Tab). Keys: accept (A), change class (number keys or a searchable class palette), delete (Del), draw a missing box (existing Add Object mode). Bulk-accept everything above a set confidence once you trust a class.
3. A reviewed page means every symbol on it is boxed and correct. Only reviewed pages are exported, because an unboxed symbol on an exported page teaches the model that it is background.
4. "Mark page reviewed" records reviewer and time. Reopening a reviewed page for edits returns it to `in_review`.
5. Record the original proposal on each corrected annotation. The fraction of proposals accepted unchanged per class is a free, continuous measure of how well the model is doing on new work.

**Storage.** A dataset folder outside the repository, on an encrypted company drive:

```
spectra-dataset/
  manifest.json              # class list version, sheets (SheetState), dataset version
  classes/v1.json            # class IDs, names, "large" flag, description, example image refs
  labels/<pdf_sha256>_<page>.json   # list[Annotation]; master copy, PDF points
  pdfs/<pdf_sha256>.pdf      # source drawings, or a path map if they must stay in project folders
  exports/<dataset_version>/ # generated; never edited by hand
```

**Export.** A command-line tool (`uv run spectra-export --dpi 200 --tile 640 --overlap 160 --format coco`) renders reviewed pages, cuts tiles with the same tiler as inference, clips boxes to tiles (dropping slivers below a minimum visible fraction, e.g. 50 %), subsamples empty tiles (e.g. keep 20 %), and writes COCO JSON (for RF-DETR, D-FINE) or YOLO text files (normalised centre, width, height per line). Output is deterministic for a given manifest and settings, and the export folder name includes a hash of both.

**Training.** A separate script and uv dependency group (`train`), run on the GPU machine, never inside the GUI. It writes a model folder:

```
models/<model_id>/
  model.onnx
  model_card.json   # class list version, dataset version + hash, detector + version, config,
                    # seed, git commit, training time, hardware, test metrics
  eval_report.md
```

Spectra loads a model folder, checks that the class list version matches, and records `model_id` on every proposal.

**Active learning.** Rank unreviewed pages by expected value: many low-confidence proposals, many class conflicts, or a new client style. Review those first.

**Effort.** Reviewing a dense sheet (150–400 symbols) from proposals is about 10–25 minutes; annotating from scratch is about 45–90 minutes. **[Estimate]** A first useful cross-style model needs on the order of 100–200 reviewed sheets across at least 5 drawing styles. **[Estimate]**

**Hardware.** Client drawings cannot go to cloud GPUs unless Monaco has an approved private tenancy, so training is local.

- Recommended: an NVIDIA GPU with at least 8 GB VRAM, preferably 12–16 GB (for example a laptop RTX 4070/4080 or a desktop RTX 4070 Ti or better), with CUDA on Windows. **[Estimate]**
- Training time, basis: 150 sheets × ~100 tiles, empty tiles subsampled, ≈ 8,000 tiles; 50 epochs ≈ 400,000 tile iterations.
  - GPU at 20–40 tiles/s: 400,000 / 30 ≈ 13,000 s ≈ 4 h; range 2–8 h. **[Estimate]**
  - Laptop CPU at 0.5–1 tile/s: 400,000 / 0.75 ≈ 530,000 s ≈ 6 days; range 4–10 days. **[Estimate]**
- CPU training is workable only for small experiments (a few thousand tiles, about a day). It is not a practical loop for a growing dataset.
- Inference does not need a GPU (section 2.2).

### 3.3 Evaluation

**Test sets.**

- `test_in_style`: whole sheets from clients and styles that also appear in training, but never the same sheet or drawing set.
- `test_new_style`: whole sheets from clients and styles that never appear in training. This is the set that answers "does it work on the next client's drawings".
- Assign splits by drawing set and client at ingestion; store them in the manifest; never re-split. Tiles from one sheet must never appear in two splits.
- Tune thresholds and choose checkpoints on `val` only. Freeze test sets with a version tag; adding sheets creates a new test-set version and results are reported against both.

**Metrics.** Computed on whole sheets after tile merging, in PDF points, which is what you see in the app.

- Per class: precision and recall at the operating confidence threshold; AP at IoU 0.5 (AP50) and AP averaged over IoU 0.5:0.95 (COCO definition), using pycocotools or `faster-coco-eval`.
- Per class per sheet: count error, `|n_pred − n_true| / n_true`. This is the metric closest to a parts count.
- Per section, once sections exist: relative error in total release frequency between predicted and reviewed counts. This shows which classes matter for the QRA result.
- Confusion matrix of visual classes, to spot systematic confusions (gate vs globe).
- Report instance counts per class. With 50 test instances at a true recall of 0.90, the 95 % interval is about ±0.08 (`1.96 × √(0.9 × 0.1 / 50) = 0.083`) **[Calc]**. Classes with fewer test instances should be reported as indicative only.

**Reproducibility.**

- Pin all versions in `uv.lock` (app and training groups).
- Record seed, config file, dataset manifest hash, export settings hash, git commit and hardware in `model_card.json`.
- The evaluation script loads `model.onnx` with ONNX Runtime on CPU, which gives deterministic results for a fixed input, and writes `eval_report.md` plus a JSON of all numbers.
- A pytest test re-runs evaluation on a tiny fixture (two synthetic sheets) and checks that the numbers match exactly.

---

## 4. Beyond symbol detection

### Conclusion

Treat vector and raster drawings as two paths. For vector PDFs, read text and line geometry directly from the PDF; use ML only for symbols. For scanned or flattened PDFs, use OCR and image-based line extraction, with more review effort. Build a typed component graph with ports and pipe-segment edges, keep provenance on every element, and derive isolatable sections by cutting the graph at isolation valves. Each step ends in a review view, because errors compound along the chain.

### 4.1 Text, tags and association

**Vector PDFs.** PyMuPDF `page.get_text("words")` or `"rawdict"` returns every word with its box and writing direction. **[Fact: source]** for the API (PyMuPDF documentation; not re-checked in this session). This is exact and fast, and handles rotated line numbers. Check first whether a page has a usable text layer: some CAD exports draw text as vector strokes (SHX fonts), which then needs OCR.

**Raster PDFs.** RapidOCR (Apache-2.0 **[Fact: source]**, [RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR)) runs PaddleOCR's detection and recognition models (Apache-2.0 **[Fact: source]**) through ONNX Runtime (MIT **[Fact: source]**), so it shares the inference runtime with the detector and avoids installing PaddlePaddle. Run it on the same tiles at 300 dpi, plus a pass on the page rotated 90° for vertical text. Tesseract (Apache-2.0 **[Fact: source]**) is weaker on short, rotated engineering text **[Assumption]**; docTR (Apache-2.0 **[Fact: source]**) is an alternative.

**Classifying text.** Per-client regular expressions in the client mapping file, for example:

```
instrument tag   ^(?P<func>[A-Z]{2,4})[- ]?(?P<loop>\d{3,5})(?P<suffix>[A-Z]?)$
valve tag        ^(?P<type>ESDV|SDV|XV|BDV|PSV|HV|FV|LV|PV)[- ]?(?P<num>\d{3,5}[A-Z]?)$
line number      ^(?P<size>\d{1,2}(?:\.\d)?)"?-(?P<fluid>[A-Z]{1,3})-(?P<num>\d{3,6})-(?P<spec>[A-Z0-9]{2,6})
```

**Association.**

1. Text inside a symbol: instrument bubbles carry function letters and loop number on two lines inside the circle. Words whose centres fall inside the bubble box are joined top-to-bottom.
2. Text near a symbol: candidate pairs within a radius of k × symbol size (k ≈ 3), scored by distance, alignment with the symbol's pipe direction, and regex type compatibility (an `ESDV` tag goes with an actuated valve). Solve one-to-one with the Hungarian algorithm (`scipy.optimize.linear_sum_assignment`). Unmatched or low-margin pairs are flagged for review.
3. Leader lines: where a tag is connected by a thin leader, follow the leader from the line-extraction step (4.2) and override the proximity match.
4. Line numbers attach to pipe-segment edges they lie along. Parsing the size field gives line size automatically, which removes the manual per-section line-size entry and fixes much of the D5/D7 exposure.

### 4.2 Lines, crossings, jumps and off-page connections

**Vector path (preferred).**

1. Extract strokes with PyMuPDF `page.get_drawings()` (or pdfminer.six). Classify by stroke width, dash pattern and colour: process lines are solid and heavier; instrument signal lines are dashed or thin.
2. Remove strokes that lie inside detected symbol boxes, so symbols become nodes with ports.
3. Merge collinear touching segments; snap endpoints within a tolerance (e.g. 0.5 mm).
4. Build a planar line graph. Connection rules:
   - Endpoint on endpoint, or endpoint on another segment's interior (a T): connected.
   - Two segments crossing at interior points with no shared vertex: not connected (a crossing).
   - Junction dot (small filled circle) at a crossing: connected.
   - Line jump: a small arc or a gap in one line, with the other line passing through the gap: bridge the gap; the lines stay unconnected.
5. Ports: a line endpoint within tolerance of a symbol box edge becomes a connection to that symbol's nearest port. Valves have two ports on the line axis; equipment has many.
6. Flow arrows on lines give direction where present; otherwise the graph is undirected.

**Raster path (fallback).** Binarise (Otsu), mask text and symbol boxes, extract horizontal and vertical strokes with morphological opening (most P&ID lines are orthogonal), skeletonise (scikit-image, BSD-3 **[Fact: source]**), convert the skeleton to a pixel graph and simplify to segments; apply the same connection rules, with junction dots and jump arcs found by small template matches. OpenCV (Apache-2.0 **[Fact: source]**) `HoughLinesP` is an alternative for step 2. Expect lower reliability on scans and plan for more review time. **[Estimate]**

**Learned graph extraction.** Relationformer-style models that predict symbols and connections together (PID2Graph) are research-grade and need graph-labelled training data you do not have yet. Revisit after Phase 4, using the reviewed graphs from your own work as training data.

**Across sheets.** Detect `off_page_connector` symbols; read their text (target drawing number, continuation ID or line number); pair connectors across sheets by (target drawing, continuation ID), falling back to line number. A paired connector becomes one graph edge between sheets. Unpaired connectors are listed for review. Sheets are identified by drawing number and revision read from the title block, with manual override.

**Review view.** Colour each connected component differently on the drawing so breaks and false joins are visible at a glance; allow click-to-join and click-to-cut.

### 4.3 Graph data model

```python
@dataclass
class Provenance:
    sheet_id: str               # pdf sha256 + page
    bbox_pt: tuple[float, float, float, float] | None
    source: str                 # "model" | "vector" | "ocr" | "manual" | "rule"
    confidence: float | None
    reviewed: bool

@dataclass
class Node:
    id: str
    kind: str                   # "equipment" | "valve" | "fitting" | "instrument" | "connector" | "junction" | "line_end"
    visual_class: int | None
    eng_type: str | None        # "ESDV", "manual_gate", "vessel", ...
    tag: str | None
    ports: list[str]            # port IDs, e.g. ["a", "b"] for a two-way valve
    attrs: dict                 # size_mm, end connection (flanged/welded), normal position, fail action
    is_isolation_boundary: bool # True for ESDV/SDV per study basis
    prov: Provenance

@dataclass
class PipeSegment:
    id: str
    a: tuple[str, str]          # (node id, port id)
    b: tuple[str, str]
    line_number: str | None
    size_mm: float | None
    spec: str | None
    fluid: str | None
    length_m: float | None      # not measurable from a P&ID; user or isometric input
    path_pt: list[tuple[float, float]]
    prov: Provenance

@dataclass
class PlantGraph:
    schema_version: str
    sheets: dict[str, dict]     # sheet_id -> drawing number, revision, pdf sha256
    nodes: dict[str, Node]
    segments: dict[str, PipeSegment]
```

Stored as JSON in the project file; converted to a `networkx.MultiGraph` (BSD-3 **[Fact: source]**) for algorithms. Nodes are expanded to one vertex per port, joined internally, so a valve can be "opened" or "cut" by removing its internal link.

**Isolatable sections.**

1. Mark boundary valves (`is_isolation_boundary`) from tag prefix and a study basis list, editable by the user.
2. Remove the internal port-to-port link of each boundary valve.
3. Connected components of the remaining graph are candidate isolatable sections.
4. Boundary valves and their flanges are allocated to one side by a stated convention (for example the upstream section, or half to each); make the convention a study setting, shown in the report.
5. The user reviews and names the sections. The current hand-drawn sections stay as an override and as the fallback when the graph is incomplete.

**Parts count and frequencies per section.**

```
for each section:
    explicit components  = nodes in section, grouped by (eng_type, size_mm)
    implied components   = rules(eng_type, end connection)        # e.g. flanged valve → 2 flanged joints
    pipe length          = Σ length_m of segments                  # user input; not from the P&ID
    frequency(hole band) = Σ_components count × f(category, size, band) + Σ_pipes L × f_pipe(size, band)
```

The frequency data set (IOGP 434-01 v3.0, September 2019, [IOGP bookstore](https://www.iogp.org/bookstore/product/risk-assessment-data-directory-process-release-frequencies/) **[Fact: source]** for edition; or UK HSE HCR-derived data, source and edition to be recorded, not checked in this session) is selected per study, stored with its source, edition, units and basis in a header file, and cited in the exported report. Every number in the report traces to node IDs and their provenance.

---

## 5. Roadmap

Effort is developer-days for one person familiar with the code base, excluding annotation time unless stated. **[Estimate]** throughout.

### Phase 1: Local model and annotation loop

**Ends with:** Spectra running fully offline on a Windows laptop, proposing symbols on a whole A1 sheet in under a minute, with review mode, export, a training script, an evaluation report on a held-out test set, and Roboflow disabled for client work.

| Milestone | Scope | Effort |
|---|---|---|
| 1a Foundations | Fix D1–D5, D8–D10, D12–D14, D16. Annotation ID; geometry in PDF points; `PageTransform`; project format v2 with PDF hash, schema version and migration from v1; remove API key from saved files; render cache keyed by DPI; in-memory rendering (no temp PNGs, D15). pytest tests for frequency look-up, section assignment, coordinate transforms. | 10–14 d |
| 1b Detector layer | `Detector` protocol; Qt-free tiler and merge module with tests; ONNX Runtime detector; model folder and model card loader; class list v1; settings (DPI, tile size, threshold) in the GUI. | 8–12 d |
| 1c Review mode | Proposal styling, keyboard review flow, class palette, page review state, correction tracking. | 8–10 d |
| 1d Dataset tools | Dataset folder, manifest, split assignment, COCO/YOLO export CLI. | 5–7 d |
| 1e Training and evaluation | Training script (RF-DETR), evaluation script and report, reproducibility test; bootstrap model on Dataset-P&ID; first model on 20–30 reviewed own sheets; comparison run with one alternative detector. | 8–12 d |
| Annotation | 20–30 sheets reviewed | 10–20 h |
| **Total** | | **40–55 d** |

**Risks.**
- GPU not available or not approved: training on CPU limits iteration to small experiments.
- Licence decision delayed (detector and PyMuPDF): blocks 1b.
- First own-data model is weak on new styles: expected; Phase 2 addresses it. Mitigated by measuring `test_new_style` from the start.
- Windows packaging of ONNX Runtime and the Nuitka build: test early in 1b.
- Contractual limits on using client drawings for training (Q4).

**Decisions before Phase 1.**
- D-1.1 Licence route: permissive detector (recommended) or Ultralytics Enterprise; and PyMuPDF: accept AGPL internally, buy Artifex licence, or replace.
- D-1.2 Training hardware: which GPU machine, owned and controlled by Monaco.
- D-1.3 Where the dataset lives (encrypted drive, access list, retention).
- D-1.4 Class list v1: confirm or edit the table in 2.3.
- D-1.5 Whether to keep Roboflow at all (for public or synthetic drawings only) or remove it.

### Phase 2: Dataset growth and cross-style model

**Ends with:** a model card meeting agreed per-class targets on `test_new_style`, for example recall ≥ 0.90 and count error ≤ 10 % on valve and flange classes. **[Estimate]** for what is achievable.

- Scope: 100–200 reviewed sheets across at least 5 styles; active-learning queue; per-client mapping files; client legend-sheet ingestion; implied-component rules file; results report with provenance; retraining cadence.
- Effort: 15–25 d development; 40–80 h annotation.
- Risks: annotation time competes with project work; rare classes stay rare (mitigate by targeted harvesting from legends); label drift between reviewers (mitigate with a short labelling guide and a sample double-review).
- Decisions: per-class acceptance targets; which clients and styles go in `test_new_style`; implied-component conventions (flanges per valve, check valve category, relief valve category).

### Phase 3: Text and tag recognition

**Ends with:** tags and line numbers attached to symbols and lines on vector and raster sheets, with a review list of unmatched items, and line size filled in from line numbers.

- Scope: vector text extraction; RapidOCR path for raster; per-client regex configuration; association; tag and line-number review UI; text precision/recall on the test sheets.
- Effort: 20–30 d.
- Risks: SHX stroke text in vector PDFs needs OCR; dense overlapping text; inconsistent tag formats across clients.
- Decisions: fraction of drawings that are vector (Q2); tag format conventions per client.

### Phase 4: Line tracing and single-sheet graph

**Ends with:** a reviewed connectivity graph for one sheet, shown as coloured connected components, with join/cut editing, and graph accuracy measured against hand-checked sheets (edge precision and recall).

- Scope: vector line extraction and connection rules; raster fallback; ports; review UI; graph JSON in the project file; PID2Graph as an external benchmark if its licence allows.
- Effort: 30–45 d.
- Risks: highest technical risk in the plan. Raster drawings, line jumps drawn inconsistently, and lines passing behind symbols. Mitigate by vector-first scope and by keeping manual sections as the fallback.
- Decisions: whether raster support is in scope for this phase; minimum acceptable graph accuracy before Phase 5.

### Phase 5: Multi-sheet graph, isolatable sections, parts count and frequencies

**Ends with:** proposed isolatable sections between ESD valves across a drawing set, per-section parts counts with explicit and implied components, release frequencies by hole size from a selected and cited data set, and an exported report traceable to drawing locations.

- Scope: off-page connector pairing; sheet identification from title blocks; boundary-valve rules; section derivation and review; frequency data-set files with source and edition; pipe length input; report export (CSV and a document format).
- Effort: 25–40 d.
- Risks: incomplete drawing sets break connectivity; study conventions differ by client; pipe length is not on P&IDs.
- Decisions: frequency data sets and editions to support; boundary-valve conventions; report format; whether to verify results against a past manual study (recommended).

### Overall

About 130–195 developer-days for Phases 1–5, plus 50–100 h annotation **[Estimate]**. Each phase leaves a working tool: Phase 1 alone replaces the cloud model; Phase 2 makes it dependable; Phases 3–5 automate what is now drawn and typed by hand.

---

## Open questions

1. **Q1.** Are the files committed in `a09218c` and deleted in `196aa15` (`test/GeZero Combined P&IDs.pdf`, `image.jpg`, `test.spectra.json`) client or confidential material, and is the GitHub repository public? If both, the history needs rewriting.
2. **Q2.** What fraction of the client P&IDs you receive are vector PDFs exported from CAD, and what fraction are scans or flattened images? Do the vector ones carry real text or SHX stroke text?
3. **Q3.** Is there an approved Monaco machine with an NVIDIA GPU for training, or a budget for one? Is any private cloud GPU tenancy approved for client data?
4. **Q4.** Do your client contracts allow using their drawings to train an internal model, and what retention rules apply to drawings, labels and trained weights?
5. **Q5.** Licence route: is Monaco willing to buy an Ultralytics Enterprise licence and/or an Artifex PyMuPDF licence, or should the tool stay on permissive licences only? Who in Monaco signs off third-party licences?
6. **Q6.** Will Spectra ever be given to anyone outside Monaco's legal entity (clients, partners, other group companies)? This decides how much the AGPL question matters.
7. **Q7.** Which frequency data sets and editions must be supported (IOGP 434-01 v3.0 2019; which HSE HCR-derived data set and version)? What is the source of the current `frequency.csv`, and are the pipe values per metre-year?
8. **Q8.** What conventions do you use for implied components (flanges per valve, check valves, relief valves, instrument connections), and do they vary by client?
9. **Q9.** Do you have past studies with manual parts counts on drawings you could use as reference results for validating Phases 2 and 5?
10. **Q10.** Is the Roboflow "schemas" project yours (trained from Dataset-P&ID or another source), and do you still need the hosted path for non-client drawings?
11. **Q11.** What is the typical sheet size and symbol size across your clients (A1 vs A0, symbol heights)? This sets render DPI and tile overlap.
12. **Q12.** What does "reliably" mean for Goal 1 in numbers, e.g. recall on valves and flanges, maximum count error per section, and acceptable review time per sheet?

## References

Licences and code (checked on 30 October 2026 unless marked):

- Ultralytics: [LICENSE (AGPL-3.0)](https://github.com/ultralytics/ultralytics/blob/main/LICENSE), [README licence section](https://github.com/ultralytics/ultralytics#-license); [licence page](https://www.ultralytics.com/license) and [forum reply](https://community.ultralytics.com/t/yolov11-agpl-license-for-on-premises-use/1529) (secondary, via search).
- RF-DETR: [roboflow/rf-detr](https://github.com/roboflow/rf-detr) (Apache-2.0 for N/S/M/L, PML 1.0 for others); Robinson et al., [arXiv 2511.09554](https://arxiv.org/abs/2511.09554).
- D-FINE: [Peterande/D-FINE](https://github.com/Peterande/D-FINE) (Apache-2.0); Peng et al., [arXiv 2410.13842](https://arxiv.org/abs/2410.13842).
- DEIM: [Intellindust-AI-Lab/DEIM](https://github.com/Intellindust-AI-Lab/DEIM) (Apache-2.0); Huang et al., CVPR 2025, [arXiv 2412.04234](https://arxiv.org/abs/2412.04234).
- RT-DETR: [lyuwenyu/RT-DETR](https://github.com/lyuwenyu/RT-DETR) (Apache-2.0); Zhao et al., CVPR 2024, [arXiv 2304.08069](https://arxiv.org/abs/2304.08069).
- YOLOX: [Megvii-BaseDetection/YOLOX](https://github.com/Megvii-BaseDetection/YOLOX) (Apache-2.0); Ge et al., [arXiv 2107.08430](https://arxiv.org/abs/2107.08430).
- MIT YOLO: [MultimediaTechLab/YOLO](https://github.com/MultimediaTechLab/YOLO) (MIT).
- YOLO26 launch: [Business Wire, 14 January 2026](https://www.businesswire.com/news/home/20260114168538/en).
- SAHI: [obss/sahi](https://github.com/obss/sahi) (MIT); Akyon et al., ICIP 2022, [arXiv 2202.06934](https://arxiv.org/abs/2202.06934).
- PyMuPDF: [COPYING (AGPL-3.0)](https://github.com/pymupdf/PyMuPDF/blob/main/COPYING). pypdfium2: [REUSE.toml](https://github.com/pypdfium2-team/pypdfium2/blob/main/REUSE.toml) (Apache-2.0 or BSD-3-Clause). pdfminer.six: [LICENSE (MIT)](https://github.com/pdfminer/pdfminer.six/blob/master/LICENSE).
- ONNX Runtime: [LICENSE (MIT)](https://github.com/microsoft/onnxruntime/blob/main/LICENSE). PyTorch: [LICENSE (BSD-style)](https://github.com/pytorch/pytorch/blob/main/LICENSE).
- RapidOCR: [RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR) (Apache-2.0). PaddleOCR: [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) (Apache-2.0). Tesseract: [tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract) (Apache-2.0). docTR: [mindee/doctr](https://github.com/mindee/doctr) (Apache-2.0).
- OpenCV: [LICENSE (Apache-2.0)](https://github.com/opencv/opencv/blob/4.x/LICENSE). scikit-image: [LICENSE (BSD-3)](https://github.com/scikit-image/scikit-image/blob/main/LICENSE.txt). NetworkX: [LICENSE (BSD-3)](https://github.com/networkx/networkx/blob/main/LICENSE.txt).

Datasets and papers (licences not confirmed; see 3.1):

- Paliwal, Jain, Sharma, Vig, "Digitize-PID: Automatic Digitization of Piping and Instrumentation Diagrams", 2021, [arXiv 2109.03794](https://arxiv.org/abs/2109.03794).
- Stürmer, Graumann, Koch, "From Engineering Diagrams to Graphs: Digitizing P&IDs with Transformers", IEEE DSAA 2025, [arXiv 2411.13929](https://arxiv.org/abs/2411.13929); PID2Graph on [Zenodo 14803338](https://zenodo.org/records/14803338).
- SynthPID, 2026, [arXiv 2604.16513](https://arxiv.org/abs/2604.16513) (not read).

Frequency data:

- IOGP Report 434-01, Risk Assessment Data Directory: Process Release Frequencies, version 3.0, September 2019, [IOGP bookstore](https://www.iogp.org/bookstore/product/risk-assessment-data-directory-process-release-frequencies/). Table contents not checked in this review.
- UK HSE Hydrocarbon Releases (HCR) data: source and edition used by `frequency.csv` not identified; see Q7.

Sources that could not be reached from the review environment: arxiv.org, zenodo.org, gnu.org (GPL FAQ), ultralytics.com. To confirm the marked items, open those pages directly or allow those hosts in the session's network settings.
