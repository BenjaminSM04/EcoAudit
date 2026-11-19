"""Entrena un localizador experimental con las particiones de desarrollo del protocolo v3."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn

SIZE = 96


def dataset(root, splits, names):
    images, masks = [], []
    for name in names:
        with (splits / f"{name}_manifest.csv").open(encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                assert row["partition"] == name
                with Image.open(root / row["image_path"]) as image:
                    images.append(
                        np.asarray(
                            image.convert("L").resize(
                                (SIZE, SIZE), Image.Resampling.BILINEAR
                            )
                        )
                        / 255
                    )
                regions = []
                for path in (row.get("mask_paths") or row["mask_path"]).split("|"):
                    with Image.open(root / path) as mask:
                        regions.append(
                            np.asarray(
                                mask.convert("L").resize(
                                    (SIZE, SIZE), Image.Resampling.NEAREST
                                )
                            )
                            > 0
                        )
                masks.append(np.logical_or.reduce(regions))
    return tuple(
        torch.tensor(np.array(a), dtype=torch.float32)[:, None] for a in (images, masks)
    )


def block(a, b):
    return nn.Sequential(
        nn.Conv2d(a, b, 3, padding=1),
        nn.BatchNorm2d(b),
        nn.ReLU(),
        nn.Conv2d(b, b, 3, padding=1),
        nn.BatchNorm2d(b),
        nn.ReLU(),
    )


class Segmenter(nn.Module):
    def __init__(self):
        super().__init__()
        self.first = block(1, 12)
        self.second = block(12, 24)
        self.bottom = block(24, 48)
        self.decode2 = block(72, 24)
        self.decode1 = block(36, 12)
        self.output = nn.Conv2d(12, 1, 1)
        self.pool = nn.MaxPool2d(2)
        self.up = nn.Upsample(scale_factor=2, mode="nearest")

    def forward(self, x):
        a = self.first(x)
        b = self.second(self.pool(a))
        c = self.bottom(self.pool(b))
        d = self.decode2(torch.cat((self.up(c), b), 1))
        return self.output(self.decode1(torch.cat((self.up(d), a), 1)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("root", "splits", "out"):
        parser.add_argument(f"--{key}", type=Path, required=True)
    args = parser.parse_args()
    torch.manual_seed(42)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    x, y = dataset(args.root, args.splits, ["source_train", "target_adapt"])
    vx, vy = dataset(args.root, args.splits, ["source_val"])
    model = Segmenter().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001)
    for epoch in range(24):
        for batch in torch.randperm(len(x)).split(24):
            inputs, target = x[batch].to(device), y[batch].to(device)
            if torch.rand(()) < 0.5:
                inputs, target = inputs.flip([-1]), target.flip([-1])
            logits = model(inputs)
            p = logits.sigmoid()
            dice = (2 * (p * target).sum((2, 3)) + 1) / ((p + target).sum((2, 3)) + 1)
            loss = (
                nn.functional.binary_cross_entropy_with_logits(logits, target)
                + 1
                - dice.mean()
            )
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    model.cpu().eval()
    with torch.no_grad():
        masks = model(vx) > 0
        dice = 2 * (masks * vy).sum((2, 3)) / (masks + vy).sum((2, 3)).clamp_min(1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model,
        vx[:1],
        str(args.out),
        opset_version=17,
        input_names=["image"],
        output_names=["logits"],
    )
    print(
        json.dumps(
            dict(
                train=len(x),
                validation=len(vx),
                mean_dice=dice.mean().item(),
                empty=int((masks.sum((2, 3)) == 0).sum()),
            )
        )
    )


if __name__ == "__main__":
    main()
