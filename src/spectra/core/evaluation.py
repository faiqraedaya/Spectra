"""Detection quality on whole drawings, in page coordinates.

Evaluation runs after tile merging, on the boxes a user would see. Besides
per-class precision, recall and AP at IoU 0.5, it reports the acceptance
target agreed for Spectra: the share of proposed items that need no edit
(correct class and a box tight enough to keep, IoU >= 0.75), and the share
of real items the tool found.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from .geometry import Box, iou

NO_EDIT_IOU = 0.75


@dataclass
class Det:
    page_key: str  # e.g. "<sha256>:<page>"
    box: Box
    cls: str
    score: float = 1.0


@dataclass
class ClassStats:
    n_true: int = 0
    n_pred: int = 0
    tp50: int = 0
    tp_no_edit: int = 0
    ap50: float = 0.0
    count_error: float = 0.0  # mean |pred - true| / true over pages with items

    @property
    def precision(self) -> float:
        return self.tp50 / self.n_pred if self.n_pred else 0.0

    @property
    def recall(self) -> float:
        return self.tp50 / self.n_true if self.n_true else 0.0


@dataclass
class Report:
    per_class: dict[str, ClassStats] = field(default_factory=dict)
    no_edit_rate: float = 0.0  # proposals usable as they are / all proposals
    found_rate: float = 0.0  # real items found (IoU >= 0.5, right class) / all real items
    map50: float = 0.0

    def table(self) -> str:
        lines = [f"{'class':24s} {'true':>5s} {'pred':>5s} {'P':>6s} {'R':>6s} {'AP50':>6s} {'no-edit':>8s} {'count err':>9s}"]
        for c, s in sorted(self.per_class.items()):
            ne = s.tp_no_edit / s.n_pred if s.n_pred else 0.0
            lines.append(f"{c:24s} {s.n_true:5d} {s.n_pred:5d} {s.precision:6.3f} {s.recall:6.3f} {s.ap50:6.3f} {ne:8.3f} {s.count_error:9.3f}")
        lines.append(f"no-edit rate {self.no_edit_rate:.3f} (target 0.90), found {self.found_rate:.3f}, mAP50 {self.map50:.3f}")
        return "\n".join(lines)


def _ap(scores: list[float], hits: list[bool], n_true: int) -> float:
    """All-point interpolated average precision (PASCAL VOC 2010+)."""
    if n_true == 0 or not scores:
        return 0.0
    order = np.argsort(-np.array(scores), kind="stable")
    h = np.array(hits)[order]
    tp = np.cumsum(h)
    fp = np.cumsum(~h)
    rec = tp / n_true
    prec = tp / np.maximum(tp + fp, 1)
    mrec = np.concatenate([[0.0], rec, [1.0]])
    mpre = np.concatenate([[0.0], prec, [0.0]])
    for i in range(len(mpre) - 2, -1, -1):
        mpre[i] = max(mpre[i], mpre[i + 1])
    idx = np.nonzero(mrec[1:] != mrec[:-1])[0]
    return float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))


def evaluate(truth: list[Det], preds: list[Det], iou_threshold: float = 0.5) -> Report:
    classes = sorted({d.cls for d in truth} | {d.cls for d in preds})
    report = Report()
    total_pred = total_no_edit = total_true = total_found = 0
    for c in classes:
        t_by_page: dict[str, list[Det]] = defaultdict(list)
        for d in truth:
            if d.cls == c:
                t_by_page[d.page_key].append(d)
        p_sorted = sorted((d for d in preds if d.cls == c), key=lambda d: -d.score)
        used: dict[str, set[int]] = defaultdict(set)
        stats = ClassStats(n_true=sum(len(v) for v in t_by_page.values()), n_pred=len(p_sorted))
        scores, hits = [], []
        for p in p_sorted:
            cands = t_by_page.get(p.page_key, [])
            best, best_iou = -1, 0.0
            for k, t in enumerate(cands):
                if k in used[p.page_key]:
                    continue
                v = iou(p.box, t.box)
                if v > best_iou:
                    best, best_iou = k, v
            hit = best >= 0 and best_iou >= iou_threshold
            if hit:
                used[p.page_key].add(best)
                stats.tp50 += 1
                stats.tp_no_edit += best_iou >= NO_EDIT_IOU
            scores.append(p.score)
            hits.append(hit)
        stats.ap50 = _ap(scores, hits, stats.n_true)
        errs = []
        pred_counts: dict[str, int] = defaultdict(int)
        for p in p_sorted:
            pred_counts[p.page_key] += 1
        for page, ts in t_by_page.items():
            errs.append(abs(pred_counts[page] - len(ts)) / len(ts))
        stats.count_error = float(np.mean(errs)) if errs else 0.0
        report.per_class[c] = stats
        total_pred += stats.n_pred
        total_no_edit += stats.tp_no_edit
        total_true += stats.n_true
        total_found += stats.tp50
    report.no_edit_rate = total_no_edit / total_pred if total_pred else 0.0
    report.found_rate = total_found / total_true if total_true else 0.0
    aps = [s.ap50 for s in report.per_class.values() if s.n_true]
    report.map50 = float(np.mean(aps)) if aps else 0.0
    return report
