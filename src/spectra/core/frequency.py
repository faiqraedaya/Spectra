"""Parts count and release frequencies (IOGP Report 434-01, 2019).

The table gives, per equipment category and size band, the release frequency
in each hole-size band. Totals per section are

    F_section(band) = sum over components of  n * f(category, size, band)
                    + L_pipe * f_pipe(size, band)

where n includes implied components (for example two flanged joints per
valve) and L_pipe is the section's steel pipe length in metres.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from .project import Item, Project

HOLE_BANDS = ["1-3 mm", "3-10 mm", "10-50 mm", "50-150 mm", ">150 mm"]
PIPE_CATEGORY = "Steel Pipes"
UNASSIGNED = "Unassigned"


@dataclass(frozen=True)
class FrequencyRow:
    category: str
    min_mm: float
    max_mm: float
    values: tuple[float, ...]  # one per hole band, per item-year (per metre-year for pipes)


class FrequencyTable:
    def __init__(self, rows: list[FrequencyRow], meta: dict | None = None):
        self.rows = rows
        self.meta = meta or {}
        self._by_cat: dict[str, list[FrequencyRow]] = defaultdict(list)
        for r in rows:
            self._by_cat[r.category].append(r)
        for v in self._by_cat.values():
            v.sort(key=lambda r: r.max_mm)

    @classmethod
    def load(cls, path: str | Path) -> FrequencyTable:
        path = Path(path)
        rows = []
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = [h.strip() for h in next(reader)]
            if len(header) < 3 + len(HOLE_BANDS):
                raise ValueError(f"{path.name}: expected Category, min, max and {len(HOLE_BANDS)} hole-size columns")
            for line in reader:
                if not line or not line[0].strip():
                    continue
                rows.append(
                    FrequencyRow(
                        line[0].strip(),
                        float(line[1]),
                        float(line[2]),
                        tuple(float(v) for v in line[3 : 3 + len(HOLE_BANDS)]),
                    )
                )
        meta_path = path.with_suffix(".json")
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        return cls(rows, meta)

    @classmethod
    def builtin(cls, name: str = "iogp_434-01_2019.csv") -> FrequencyTable:
        with resources.as_file(resources.files("spectra.assets") / name) as p:
            return cls.load(p)

    @property
    def categories(self) -> list[str]:
        return list(self._by_cat)

    def lookup(self, category: str, size_mm: float) -> FrequencyRow | None:
        """Row for a category and size.

        Size bands are treated as continuous: a row covers sizes above the
        previous row's maximum up to and including its own maximum, so
        50.5 mm falls in the 51-100 mm row. Sizes below the first band use the
        first row; sizes above the last use the last.
        """
        rows = self._by_cat.get(category)
        if not rows:
            return None
        for r in rows:
            if size_mm <= r.max_mm:
                return r
        return rows[-1]

    def unit(self, category: str) -> str:
        units = self.meta.get("units", {})
        return units.get(category, units.get("default", "per item per year"))


@dataclass
class PartsLine:
    section: str
    category: str
    size_mm: float | None
    explicit: float = 0.0
    implied: float = 0.0

    @property
    def total(self) -> float:
        return self.explicit + self.implied


@dataclass
class Issue:
    item_id: str | None
    message: str


@dataclass
class SectionResult:
    section: str
    parts: list[PartsLine] = field(default_factory=list)
    by_band: list[float] = field(default_factory=lambda: [0.0] * len(HOLE_BANDS))

    @property
    def total(self) -> float:
        return sum(self.by_band)


@dataclass
class Results:
    sections: list[SectionResult]
    issues: list[Issue]
    not_counted: dict[str, int]


def calculate(project: Project, table: FrequencyTable, include_proposed: bool = False) -> Results:
    """Parts count and frequency per section. Nothing is dropped silently:
    items that cannot be costed are listed in Results.issues."""
    tax = project.taxonomy
    lines: dict[tuple[str, str, float | None], PartsLine] = {}
    issues: list[Issue] = []
    not_counted: dict[str, int] = defaultdict(int)

    def add(section: str, category: str, size: float | None, explicit: float = 0.0, implied: float = 0.0):
        key = (section, category, size)
        line = lines.setdefault(key, PartsLine(section, category, size))
        line.explicit += explicit
        line.implied += implied

    for item in project.items:
        if item.status != "accepted" and not include_proposed:
            continue
        cls = tax.get(item.cls)
        sec = project.section_of(item)
        sec_name = sec.name if sec else UNASSIGNED
        size = project.effective_size(item)
        if cls.category is None and not cls.implied:
            not_counted[cls.name] += item.count
            continue
        if size is None:
            issues.append(Issue(item.id, f"{cls.name} has no size (set it on the item or its section)"))
        if cls.category is not None:
            add(sec_name, cls.category, size, explicit=item.count)
        for cat, n in cls.implied.items():
            add(sec_name, cat, size, implied=n * item.count)

    for sec in project.sections:
        if sec.pipe_length_m > 0:
            add(sec.name, PIPE_CATEGORY, sec.size_mm, explicit=sec.pipe_length_m)
            if sec.size_mm is None:
                issues.append(Issue(None, f"Section {sec.name}: pipe length given without a line size"))

    order = {s.name: k for k, s in enumerate(project.sections)}
    results: dict[str, SectionResult] = {}
    for line in sorted(lines.values(), key=lambda l: (order.get(l.section, 1e9), l.category, l.size_mm or 0)):
        res = results.setdefault(line.section, SectionResult(line.section))
        res.parts.append(line)
        if line.size_mm is None:
            continue
        row = table.lookup(line.category, line.size_mm)
        if row is None:
            issues.append(Issue(None, f"No frequency data for category '{line.category}'"))
            continue
        for b in range(len(HOLE_BANDS)):
            res.by_band[b] += line.total * row.values[b]
    for s in project.sections:  # keep empty sections visible
        results.setdefault(s.name, SectionResult(s.name))
    ordered = sorted(results.values(), key=lambda r: order.get(r.section, 1e9))
    return Results(ordered, issues, dict(not_counted))


def item_issue_ids(results: Results) -> set[str]:
    return {i.item_id for i in results.issues if i.item_id}


def count_by_class(items: list[Item]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for i in items:
        out[i.cls] += i.count
    return dict(out)
