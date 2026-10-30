"""Train an RF-DETR symbol detector on a Spectra dataset and package it for Spectra.

Runs in its own environment (this folder's pyproject.toml) so the Spectra app
never depends on PyTorch. Typical use on a Windows laptop with an RTX 3070
(8 GB):

    cd training
    uv sync
    uv run train_rfdetr.py --dataset D:\\spectra\\datasets\\v1 --out D:\\spectra\\models\\v1

The dataset is the folder written by "Spectra > Training > Export dataset" (or
`spectra-cli export-dataset`). The output folder holds model.onnx and
model_card.json; point Spectra at it under Detect > Model.

The first run downloads RF-DETR's COCO-pretrained weights from the internet.
No drawing data leaves the machine.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import time
from pathlib import Path

SIZES = {"nano": "RFDETRNano", "small": "RFDETRSmall", "medium": "RFDETRMedium"}
LARGE_CLASSES = {
    "vessel", "pump_centrifugal", "pump_reciprocating", "compressor_centrifugal", "compressor_reciprocating",
    "hx_shell_side", "hx_tube_side", "hx_plate", "air_cooler", "filter", "pig_trap", "expander", "turbine",
    "degasser", "other_vessel", "xmas_tree",
}  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, type=Path, help="Spectra dataset export folder")
    ap.add_argument("--out", required=True, type=Path, help="output model folder")
    ap.add_argument("--size", choices=SIZES, default="small", help="model size (small fits an 8 GB GPU at 512 px)")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch", type=int, default=4, help="images per step; 4 fits 8 GB for small at 512 px")
    ap.add_argument("--accum", type=int, default=4, help="gradient accumulation; effective batch = batch x accum")
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--device", default="cuda", help="cuda, cuda:0 or cpu (cpu is very slow)")
    ap.add_argument("--resume", type=Path, help="checkpoint to resume from")
    args = ap.parse_args()

    meta = json.loads((args.dataset / "dataset.json").read_text(encoding="utf-8"))
    classes: list[str] = meta["classes"]
    resolution = int(meta["tile"])

    import rfdetr  # imported late so --help works without the training stack

    model_cls = getattr(rfdetr, SIZES[args.size])
    model = model_cls(resolution=resolution)
    work = args.out / "work"
    work.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    model.train(
        dataset_dir=str(args.dataset),
        output_dir=str(work),
        epochs=args.epochs,
        batch_size=args.batch,
        grad_accum_steps=args.accum,
        lr=args.lr,
        seed=args.seed,
        device=args.device,
        early_stopping=True,
        early_stopping_patience=12,
        class_names=classes,
        **({"resume": str(args.resume)} if args.resume else {}),
    )
    minutes = (time.time() - t0) / 60

    onnx_path = Path(model.export(output_dir=str(work / "export"), format="onnx"))
    if onnx_path.is_dir():
        onnx_path = next(onnx_path.glob("*.onnx"))
    shutil.copy(onnx_path, args.out / "model.onnx")

    card = {
        "name": args.out.name,
        "classes": classes,
        "resolution": resolution,
        "dpi": meta["dpi"],
        "overlap": meta["overlap"],
        "large_classes": [c for c in classes if c in LARGE_CLASSES],
        "background_class_id": -1,
        "trained_on": meta.get("hash", ""),
        "metrics": {},
        "training": {
            "detector": f"rfdetr {rfdetr.__version__ if hasattr(rfdetr, '__version__') else ''} {args.size}",
            "epochs": args.epochs,
            "batch": args.batch,
            "accum": args.accum,
            "lr": args.lr,
            "seed": args.seed,
            "minutes": round(minutes, 1),
            "machine": platform.node(),
            "device": args.device,
        },
    }
    (args.out / "model_card.json").write_text(json.dumps(card, indent=1), encoding="utf-8")
    print(f"Model written to {args.out} after {minutes:.0f} min. Evaluate it with:")
    print(f"  spectra-cli evaluate --model {args.out} --project <test project>.spectra.json")


if __name__ == "__main__":
    main()
