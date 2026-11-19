"""Comparación exploratoria pareada en validación BUSI. Solo lee source_train y source_val."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import torch
from app.pipeline.localizer import propose
from app.pipeline.runner import resolve_roi
from PIL import Image
from sklearn.metrics import roc_auc_score
from torch import nn

from .export_paper_bundle import MEAN, SEEDS, STD, PaperClassifier


def inputs(root, splits, partition, localizer):
    rows = list(
        csv.DictReader((splits / f"{partition}_manifest.csv").open(encoding="utf-8"))
    )
    batches = {"auto": [], "mask": [], "full": []}
    labels = []
    for row in rows:
        path = root / row["image_path"]
        image = Image.open(path).convert("RGB")
        roi = propose(path.read_bytes(), localizer)
        boxes = {"auto": resolve_roi(roi, *image.size, margin=0.1)}
        if partition == "source_val":
            masks = [
                np.asarray(Image.open(root / m).convert("L")) > 0
                for m in row["mask_paths"].split("|")
            ]
            ys, xs = np.where(np.logical_or.reduce(masks))
            box = dict(x=xs.min(), y=ys.min(), w=np.ptp(xs) + 1, h=np.ptp(ys) + 1)
            boxes.update(
                mask=resolve_roi(box, *image.size, margin=0.1), full=(0, 0, *image.size)
            )
        for name, box in boxes.items():
            crop = image.crop(box).resize((224, 224), Image.Resampling.BILINEAR)
            batches[name].append(np.asarray(crop).copy())
        labels.append(int(row["label_idx"]))
    return {
        k: torch.from_numpy(np.stack(v)).permute(0, 3, 1, 2)
        for k, v in batches.items()
        if v
    }, torch.tensor(labels)


def features(model, images, device):
    mean = torch.tensor(MEAN, device=device)[None, :, None, None]
    std = torch.tensor(STD, device=device)[None, :, None, None]
    with torch.no_grad():
        return torch.cat(
            [
                model.backbone((batch.to(device).float() / 255 - mean) / std)
                for batch in images.split(24)
            ]
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "run", "localizer"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    train, y = inputs(args.root, args.run / "splits", "source_train", args.localizer)
    val, labels = inputs(args.root, args.run / "splits", "source_val", args.localizer)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    predictions = {k: [] for k in ("full", "mask", "auto", "refit")}
    for seed in SEEDS:
        for family in ("main", "roi"):
            path = (
                args.run
                / "checkpoints"
                / "v3"
                / f"{family}_resnet18_seed{seed}_source_only_matched.pt"
            )
            model = PaperClassifier("resnet18").to(device).eval()
            model.load_state_dict(
                torch.load(path, map_location=device, weights_only=False)["model_state"]
            )
            for mode in ["full"] if family == "main" else ["mask", "auto"]:
                feats = features(model, val[mode], device)
                with torch.no_grad():
                    z = model.head(feats)
                    predictions[mode].append((z[:, 1] - z[:, 0]).cpu().numpy())
            if family == "roi":
                train_feat = features(model, train["auto"], device)
                head = model.head[1]
                opt = torch.optim.AdamW(head.parameters(), lr=0.0005)
                for _ in range(40):
                    loss = nn.functional.cross_entropy(head(train_feat), y.to(device))
                    opt.zero_grad()
                    loss.backward()
                    opt.step()
                with torch.no_grad():
                    z = head(feats)
                    predictions["refit"].append((z[:, 1] - z[:, 0]).cpu().numpy())
    scores = {k: np.mean(v, axis=0) for k, v in predictions.items()}
    result = {k: roc_auc_score(labels, v) for k, v in scores.items()}
    rng = np.random.default_rng(42)
    pos, neg = (np.flatnonzero(labels.numpy() == c) for c in (1, 0))
    differences = []
    for _ in range(1000):
        idx = np.r_[rng.choice(pos, len(pos)), rng.choice(neg, len(neg))]
        differences.append(
            roc_auc_score(labels[idx], scores["auto"][idx])
            - roc_auc_score(labels[idx], scores["mask"][idx])
        )
    result["auto_minus_mask_ci95_image"] = np.quantile(
        differences, [0.025, 0.975]
    ).tolist()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
