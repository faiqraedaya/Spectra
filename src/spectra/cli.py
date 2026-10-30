"""Command-line tools for batch work: Bluebeam import, libraries, datasets, evaluation.

    spectra-cli import-bluebeam study.spectra.json drawings/*.pdf
    spectra-cli build-library study.spectra.json --name ClientA
    spectra-cli detect study.spectra.json --library ClientA [--model models/v1]
    spectra-cli export-dataset reviewed/*.spectra.json --out datasets/v1
    spectra-cli evaluate test.spectra.json --model models/v1 [--library ClientA]
    spectra-cli report study.spectra.json --out study.xlsx
    spectra-cli demo --out demo/
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from .core.project import Project


def _load(path: str) -> Project:
    p = Path(path)
    return Project.load(p) if p.exists() else Project(name=p.name.removesuffix(".spectra.json"))


def _progress(label: str):
    def cb(i: int, n: int) -> None:
        print(f"\r{label}: {i}/{n}", end="" if i < n else "\n", file=sys.stderr, flush=True)

    return cb


def cmd_import_bluebeam(a) -> None:
    from .core.workspace import Workspace

    mapping = json.loads(Path(a.map).read_text()) if a.map else None
    ws = Workspace(_load(a.project))
    for pdf in a.pdfs:
        doc = ws.add_document(pdf)
        items, report, regions = ws.import_bluebeam(doc.id, a.field, mapping, with_regions=a.regions)
        ws.fill_details(items)
        ws.project.items += items
        ws.project.sections += regions
        print(f"{doc.name}: {report.summary()}")
        if a.csv:
            from .core.bluebeam import read_markup_csv, reconcile_with_csv

            for label, expected, got in reconcile_with_csv(read_markup_csv(a.csv), items):
                if expected != got:
                    print(f"  count differs for '{label}': CSV {expected}, imported {got}")
    ws.project.save(a.project)
    print(f"Saved {a.project}")


def cmd_build_library(a) -> None:
    from .core.library import SymbolLibrary, library_dir
    from .core.workspace import Workspace

    ws = Workspace(_load(a.project))
    path = library_dir() / f"{a.name}.json"
    lib = SymbolLibrary.load(path) if path.exists() else SymbolLibrary(a.name)
    added = ws.build_library(lib)
    lib.save(path)
    print(f"Library {path}: {len(lib.templates)} templates; added {added}")


def _detect(ws, library: str | None, model: str | None, pages) -> list:
    from .core.detectors import OnnxDetector
    from .core.library import SymbolLibrary, library_dir

    new = []
    if library:
        p = Path(library)
        lib = SymbolLibrary.load(p if p.suffix == ".json" else library_dir() / f"{library}.json")
        found = ws.detect_with_library(lib, pages, _progress("library"))
        ws.project.items += found
        new += found
    if model:
        found = ws.detect_with_model(OnnxDetector(model), pages, _progress("model"))
        ws.project.items += found
        new += found
    ws.fill_details(new)
    return new


def cmd_detect(a) -> None:
    from .core.workspace import Workspace

    ws = Workspace(_load(a.project))
    new = _detect(ws, a.library, a.model, ws.all_pages())
    ws.project.save(a.project)
    print(f"Added {len(new)} items ({sum(i.status == 'proposed' for i in new)} to review). Saved {a.project}")


def cmd_export_dataset(a) -> None:
    from .core.dataset import ExportSettings, PageSource, export_coco

    sources = []
    for path in a.projects:
        p = Project.load(path)
        for d in p.documents:
            pages = d.reviewed_pages if a.reviewed_only else sorted({i.page for i in p.items if i.doc == d.id})
            for page in pages:
                items = [i for i in p.items if i.doc == d.id and i.page == page and i.status == "accepted"]
                sources.append(PageSource(d.path, d.sha256, page, items))
    if not sources:
        sys.exit("No pages to export (mark pages reviewed, or drop --reviewed-only).")
    settings = ExportSettings(dpi=a.dpi, tile=a.tile, overlap=a.overlap)
    meta = export_coco(sources, a.out, settings, _progress("pages"))
    print(json.dumps(meta["stats"], indent=1))
    print(f"Dataset {a.out} (hash {meta['hash']}), classes: {', '.join(meta['classes'])}")


def cmd_evaluate(a) -> None:
    from .core.evaluation import Det, evaluate
    from .core.workspace import Workspace

    truth_project = Project.load(a.project)
    work = copy.deepcopy(truth_project)
    work.items = []
    ws = Workspace(work)
    pages = [(d.id, p) for d in work.documents for p in (d.reviewed_pages or range(d.n_pages))]
    preds = _detect(ws, a.library, a.model, pages)
    page_set = set(pages)
    key = {d.id: d.sha256 for d in work.documents}
    truth = [Det(f"{key[i.doc]}:{i.page}", i.box, i.cls) for i in truth_project.items
             if (i.doc, i.page) in page_set and i.status == "accepted"]
    pred = [Det(f"{key[i.doc]}:{i.page}", i.box, i.cls, i.score) for i in preds]
    report = evaluate(truth, pred)
    print(report.table())
    if a.out:
        Path(a.out).write_text(report.table() + "\n", encoding="utf-8")


def cmd_report(a) -> None:
    from .core.frequency import FrequencyTable
    from .core.report import write_xlsx

    p = Project.load(a.project)
    write_xlsx(p, FrequencyTable.builtin(p.settings.frequency_table), a.out)
    print(f"Wrote {a.out}")


def cmd_demo(a) -> None:
    from .core.synthetic import make_drawing

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    make_drawing(out / "synthetic_pid.pdf", seed=a.seed)
    print(f"Wrote {out / 'synthetic_pid.pdf'} (with Bluebeam-style Count markups)")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="spectra-cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("import-bluebeam", help="import Bluebeam markups from marked-up PDFs")
    s.add_argument("project")
    s.add_argument("pdfs", nargs="+")
    s.add_argument("--field", help="markup field holding the type (default: detected, usually Label)")
    s.add_argument("--map", help="JSON file mapping label text to class keys")
    s.add_argument("--csv", help="Bluebeam Markups List CSV to reconcile counts against")
    s.add_argument("--regions", action="store_true", help="also import polyline/polygon markups as sections")
    s.set_defaults(func=cmd_import_bluebeam)

    s = sub.add_parser("build-library", help="build or extend a symbol library from accepted items")
    s.add_argument("project")
    s.add_argument("--name", required=True)
    s.set_defaults(func=cmd_build_library)

    s = sub.add_parser("detect", help="run a symbol library and/or a model on every page")
    s.add_argument("project")
    s.add_argument("--library")
    s.add_argument("--model")
    s.set_defaults(func=cmd_detect)

    s = sub.add_parser("export-dataset", help="export accepted items as a COCO training dataset")
    s.add_argument("projects", nargs="+")
    s.add_argument("--out", required=True)
    s.add_argument("--dpi", type=float, default=200)
    s.add_argument("--tile", type=int, default=512)
    s.add_argument("--overlap", type=int, default=128)
    s.add_argument("--reviewed-only", action="store_true", help="only pages marked reviewed")
    s.set_defaults(func=cmd_export_dataset)

    s = sub.add_parser("evaluate", help="compare detection with the accepted items of a reviewed project")
    s.add_argument("project")
    s.add_argument("--library")
    s.add_argument("--model")
    s.add_argument("--out")
    s.set_defaults(func=cmd_evaluate)

    s = sub.add_parser("report", help="write the Excel report")
    s.add_argument("project")
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("demo", help="write a synthetic P&ID to try Spectra")
    s.add_argument("--out", default="spectra-demo")
    s.add_argument("--seed", type=int, default=3)
    s.set_defaults(func=cmd_demo)

    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
