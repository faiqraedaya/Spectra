# Spectra user guide

Spectra counts parts on CAD P&IDs for QRA and turns the counts into release frequencies (IOGP 434-01, 2019). The screen has three parts: drawings and pages on the left, the drawing in the middle, and **Items**, **Sections** and **Results** on the right. Every edit can be undone (Ctrl+Z).

## 1. Start a study

1. File > New project, then File > Add drawings (Ctrl+Shift+O). Add the whole P&ID set; each page appears on the left with its item count.
2. If a PDF carries Bluebeam markups, Spectra offers to import them (see section 5).
3. Save early (Ctrl+S). The project file (`.spectra.json`) stores drawing paths relative to itself, so keep it next to the drawings or in a parent folder.

## 2. Find the symbols

Use these in order; each one skips items that already exist.

| Step | How | Result |
|---|---|---|
| Detect with a library | Detect… (Ctrl+D), tick the client's library, choose the pages | Every known symbol, typically within seconds per sheet. Matches scoring at or above the auto-accept threshold (Settings) are accepted; the rest are proposals. |
| Find similar | Select one item, press F | Every copy of that symbol in the drawing, rotated or mirrored, as proposals |
| Add by clicking | Press A, pick the class (number keys or the class box), click the symbol | The box snaps to the symbol's strokes |
| Add with a box | In Add mode, drag round the symbol | The box tightens to the strokes inside it |
| Trained model | Detect…, tick Trained model | Proposals for symbols the library does not know |

Libraries are per client drawing style. Build one from a reviewed study with Detect > Build library from accepted items, or add single symbols with Detect > Add selected to library. Libraries live in `%APPDATA%\Spectra\libraries` and can be copied between machines.

## 3. Review

Proposals have dashed outlines; accepted items have solid ones. An orange dot marks an item with no size.

| Key | Action |
|---|---|
| N / Shift+N | Next / previous proposal, across all pages |
| Enter | Accept the selected proposal and move to the next |
| Ctrl+Enter | Accept every proposal on the page |
| Delete | Delete the selection |
| 1 to 7 | Set the class: 1 manual valve, 2 check valve, 3 actuated valve, 4 relief valve, 5 flanged joint, 6 instrument connection, 7 pressure vessel |
| F | Find similar to the selected item |
| V / A / S | Select, Add and Section modes; Esc returns to Select |
| Wheel / Space+drag / middle drag | Zoom / pan |
| PgUp / PgDn, Ctrl+0 | Previous / next page, fit page |

Keys act only while the drawing or the item table has focus, so typing a tag never triggers them. Drag a selected item to move it, or its edges to resize it. The inspector (Items tab) edits class, size, tag, count and section for one or many selected items.

When every symbol on a page is correct, click **Mark page reviewed**. Reviewed pages are the ones safe to use for training.

The status bar shows **Kept unchanged**: the share of automatic detections you accepted without changing class, box or size, counting deletions as changes. The target is 90 %.

## 4. Sections, tags and sizes

- **Propose sections from isolation valves** (Sections tab): Spectra traces the pipework strokes, joining them where a line ends on another line or on a symbol (lines that merely cross are not joined), and splits the network at actuated valves whose tags mark them as isolation valves (ESDV, SDV, ESV, SSV, XV, EIV, BDV, HIPPS, ZV; change the list under Settings > Detection). Each connected part becomes a section named after the drawing, page and number. Then:
  - check each section and rename it;
  - give sections that continue across off-page connectors the same name, so the results add them together;
  - assign each isolation valve to the section your convention requires (they are left unassigned on purpose).
- Tags are read from the drawing text when items are added or detected: function letters and loop number inside an instrument bubble (PT over 1006 gives PT-1006), and the nearest tag text beside other symbols.
- To draw sections by hand: Sections tab > Add section, name it, give it a line size (mm) and, if you count pipework, a pipe length (m).
- Draw region (or S): click points along the pipework, double-click or Enter to finish. Close the shape back on its first point to make an area instead. Items the region touches (or, for an area, items inside it) belong to the section. An item can also be assigned explicitly in the inspector.
- Size order: the item's own size; else the class default (instrument connections default to 25 mm, the tapping size); else the section's line size. Spectra fills missing item sizes from line numbers such as `6"-P-1001-A1A` or `150-HC-12345-B1A` printed along the pipe, and records which line number it used.

## 5. Bring in past Bluebeam studies

File > Import Bluebeam markups (or add a marked-up PDF):

1. Spectra reads every markup. Count markups give one item per counted point; a circle or box drawn round a symbol snaps to the strokes inside it.
2. It picks the field holding the type (usually **Label**) and parses type and size, for example `Manual Valve 6in` gives a manual valve of DN150.
3. Check the class for each label type in the dialog. Unmapped types are skipped and listed.
4. Leave **Learn the symbols and find the ones left unmarked** ticked: Spectra builds templates from the marked items and proposes every identical symbol that was not marked. This is a check on the original count as well as a way to complete it.

For many studies at once, use the command line:

```bash
uv run spectra-cli import-bluebeam study.spectra.json drawings\*.pdf --csv markups.csv
uv run spectra-cli build-library study.spectra.json --name ClientA
```

`--csv` reconciles counts with the Bluebeam Markups List summary and prints any label whose count differs.

## 6. Conventions

Settings > Classes and conventions sets, per class: the IOGP 434-01 category (or not counted), flanged joints implied per item (two per valve by default), the default size and the hotkey. Defaults follow your stated practice: check valves count as manual valves, relief valves as actuated valves, and instrument connections use their own category with no implied flanges. The Detection tab holds the match thresholds, the auto-accept score, the model confidence and the line-number pattern.

## 7. Results and report

The Results tab shows the release frequency per section and hole size (1-3, 3-10, 10-50, 50-150, >150 mm), the accepted item count, and every issue, such as items without a size or classes with no frequency category. Double-click an issue to go to the item. Proposals are excluded unless you tick the box.

File > Export Excel report (Ctrl+E) writes five sheets: Frequencies, Parts count (counted and implied items per category and size, with the data row used), Items (every item with drawing, page, position, source, size origin and Bluebeam label), Issues, and Basis (data set, edition, conventions, drawing hashes).

## 8. Notes

- Spectra reads CAD (vector) PDFs. Scanned drawings display and accept manual items, but snapping, find similar and libraries need vector strokes.
- SHX text: if line numbers are drawn as strokes, sizes cannot be read unless the PDF carries AutoCAD's SHX text comments (the PDFSHX export setting); give sections a line size instead.
- Nothing is sent anywhere. Rendered images stay in memory. Stroke geometry is cached in `%LOCALAPPDATA%\Spectra\cache` to make reopening fast; clear that folder when a study is archived.
