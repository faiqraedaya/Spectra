"""Object classes, their frequency categories and counting conventions.

A class is what the detector and the reviewer assign to a symbol. Each class
maps to one IOGP 434-01 equipment category (or none, for symbols that are
not leak sources). Implied components capture conventions such as "two
flanged joints per valve"; they are project settings because conventions
differ between clients and studies.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


@dataclass
class ObjectClass:
    key: str
    name: str
    category: str | None  # IOGP 434-01 category, None if not counted
    colour: str
    implied: dict[str, float] = field(default_factory=dict)  # category -> count per item
    keywords: list[str] = field(default_factory=list)  # for label matching (regex fragments)
    hotkey: str = ""
    # Size used when the item has none, ahead of the section's line size. For
    # instrument connections the tapping size matters, not the pipe size.
    default_size_mm: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ObjectClass:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


_TWO_FLANGES = {"Flanged Joints": 2.0}

DEFAULT_CLASSES: list[ObjectClass] = [
    ObjectClass("manual_valve", "Manual valve", "Manual Valves", "#2563eb", dict(_TWO_FLANGES),
                [r"manual", r"gate", r"globe", r"ball", r"butterfly", r"plug", r"needle", r"\bhv\b", r"valve", r"\bvlv\b", r"\bmv\b"], "1"),
    ObjectClass("check_valve", "Check valve", "Manual Valves", "#0891b2", dict(_TWO_FLANGES),
                [r"check", r"\bnrv\b", r"non.?return"], "2"),
    ObjectClass("actuated_valve", "Actuated valve", "Actuated Valves", "#dc2626", dict(_TWO_FLANGES),
                [r"actuat", r"esd", r"\bsdv\b", r"\bxv\b", r"\bbdv\b", r"control", r"\bmov\b", r"motor", r"pneumatic", r"solenoid", r"\b[fpltc]cv\b", r"\b[fplt]v\b", r"\bav\b"], "3"),
    ObjectClass("relief_valve", "Relief valve", "Actuated Valves", "#ea580c", dict(_TWO_FLANGES),
                [r"relief", r"\bpsv\b", r"\bprv\b", r"\btsv\b", r"safety"], "4"),
    ObjectClass("flange", "Flanged joint", "Flanged Joints", "#7c3aed", {},
                [r"flange", r"\bflg\b", r"\bfj\b"], "5"),
    ObjectClass("instrument", "Instrument connection", "Instrument Connection", "#059669", {},
                [r"instrument", r"\binst\b", r"\bic\b", r"transmitter", r"gauge", r"tapping"], "6", 25.0),
    ObjectClass("vessel", "Pressure vessel", "Process Pressure Vessel", "#4b5563", {},
                [r"vessel", r"separator", r"drum", r"scrubber", r"knock.?out", r"column"], "7"),
    ObjectClass("pump_centrifugal", "Centrifugal pump", "Centrifugal Pumps", "#b45309", {}, [r"centrifugal pump", r"pump"]),
    ObjectClass("pump_reciprocating", "Reciprocating pump", "Reciprocating Pumps", "#b45309", {}, [r"recip\w* pump"]),
    ObjectClass("compressor_centrifugal", "Centrifugal compressor", "Centrifugal Compressor", "#9d174d", {}, [r"centrifugal compressor", r"compressor"]),
    ObjectClass("compressor_reciprocating", "Reciprocating compressor", "Reciprocating Compressor", "#9d174d", {}, [r"recip\w* compressor"]),
    ObjectClass("hx_shell_side", "Shell & tube HX (shell HC)", "Shell & Tube (Shell HC)", "#0f766e", {}, [r"shell.?side", r"shell hc"]),
    ObjectClass("hx_tube_side", "Shell & tube HX (tube HC)", "Shell & Tube (Tube HC)", "#0f766e", {}, [r"tube.?side", r"tube hc", r"exchanger", r"\bhx\b"]),
    ObjectClass("hx_plate", "Plate HX / PCHE", "Plate & Frame / PCHE", "#0f766e", {}, [r"plate", r"pche"]),
    ObjectClass("air_cooler", "Air cooler", "Air Cooler", "#0f766e", {}, [r"air.?cool", r"fin.?fan"]),
    ObjectClass("filter", "Filter", "Filters", "#65a30d", {}, [r"filter"]),
    ObjectClass("pig_trap", "Pig trap", "Pig Traps", "#65a30d", {}, [r"\bpig"]),
    ObjectClass("flexible_hose", "Flexible pipe", "Flexible Piping", "#a16207", {}, [r"flexible", r"hose"]),
    ObjectClass("expander", "Turbo-expander", "Expanders", "#6b7280", {}, [r"turbo.?expander", r"expander"]),
    ObjectClass("xmas_tree", "Xmas tree", "Xmas Tree", "#6b7280", {}, [r"xmas", r"christmas"]),
    ObjectClass("turbine", "Turbine", "Turbine", "#6b7280", {}, [r"turbine"]),
    ObjectClass("ssiv", "SSIV assembly", "SSIV Assembly", "#6b7280", {}, [r"ssiv"]),
    ObjectClass("degasser", "Degasser", "Degasser", "#6b7280", {}, [r"degasser"]),
    ObjectClass("other_vessel", "Pressure vessel (other)", "Pressure Vessel (Other)", "#6b7280", {}, [r"other vessel"]),
    ObjectClass("spectacle_blind", "Spectacle blind", None, "#94a3b8", {}, [r"spectacle", r"blind", r"spade", r"spacer"]),
    ObjectClass("reducer", "Reducer", None, "#94a3b8", {}, [r"reducer", r"expander fitting", r"swage"]),
    ObjectClass("strainer", "Strainer", None, "#94a3b8", dict(_TWO_FLANGES), [r"strainer"]),
    ObjectClass("off_page_connector", "Off-page connector", None, "#94a3b8", {}, [r"off.?page", r"continuation", r"connector"]),
    ObjectClass("other", "Other", None, "#94a3b8", {}, []),
]  # fmt: skip


class Taxonomy:
    def __init__(self, classes: list[ObjectClass] | None = None):
        self.classes: list[ObjectClass] = [ObjectClass.from_dict(c.to_dict()) for c in (classes or DEFAULT_CLASSES)]

    def __iter__(self):
        return iter(self.classes)

    def __len__(self) -> int:
        return len(self.classes)

    @property
    def keys(self) -> list[str]:
        return [c.key for c in self.classes]

    def get(self, key: str) -> ObjectClass:
        for c in self.classes:
            if c.key == key:
                return c
        return self.get("other") if key != "other" else ObjectClass("other", "Other", None, "#94a3b8")

    def name(self, key: str) -> str:
        return self.get(key).name

    def match_label(self, text: str) -> str | None:
        """Best class for a free-text label such as 'Manual Valve 6in' or 'ESDV'.

        Classes are tried most specific first: a class whose keyword matches
        later in a longer phrase wins over the generic 'valve' keyword, so
        'Check Valve' maps to check_valve, not manual_valve.
        """
        t = text.lower()
        for c in self.classes:  # exact name or category match first
            if t.strip() in (c.name.lower(), c.key, (c.category or "").lower()):
                return c.key
        best: tuple[int, int, str] | None = None
        for order, c in enumerate(self.classes):
            for kw in c.keywords:
                m = re.search(kw, t)
                if m:
                    specificity = len(kw) if kw not in (r"valve", r"pump", r"compressor") else 0
                    cand = (specificity, -order, c.key)
                    if best is None or cand > best:
                        best = cand
        return best[2] if best else None

    def to_list(self) -> list[dict]:
        return [c.to_dict() for c in self.classes]

    @classmethod
    def from_list(cls, data: list[dict]) -> Taxonomy:
        return cls([ObjectClass.from_dict(d) for d in data])
