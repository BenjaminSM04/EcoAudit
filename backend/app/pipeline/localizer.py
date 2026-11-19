from functools import lru_cache
from io import BytesIO

import numpy as np
import onnxruntime as ort
from PIL import Image


@lru_cache(maxsize=1)
def session(path, mtime):
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    return ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])


def propose(data, path):
    with Image.open(BytesIO(data)) as image:
        width, height = image.size
        small = image.convert("L").resize((96, 96), Image.Resampling.BILINEAR)
    x = np.asarray(small, dtype=np.float32)[None, None] / 255
    logits = session(path, path.stat().st_mtime_ns).run(None, {"image": x})[0][0, 0]
    ys, xs = np.where(logits > 0)
    if not xs.size:
        return None
    left, top = int(xs.min() * width // 96), int(ys.min() * height // 96)
    right = int(np.ceil((int(xs.max()) + 1) * width / 96))
    bottom = int(np.ceil((int(ys.max()) + 1) * height / 96))
    if right - left < 8 or bottom - top < 8:
        return None
    return dict(x=left, y=top, w=right - left, h=bottom - top)
