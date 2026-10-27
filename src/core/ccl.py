"""Connected-component labelling on a True/False picture, with numpy only (no scipy), by joining runs of pixels
row by row. Pure logic; shows nothing."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Components:
    count: int
    boxes: np.ndarray            # (count, 4): x0, y0, x1, y1 (inclusive)
    sizes: np.ndarray            # pixels in each component
    labels: np.ndarray | None    # (h, w) int32, 0 = none, 1..count = component number + 1


def _runs(mask: np.ndarray):
    h, w = mask.shape
    m = np.zeros((h, w + 2), np.int8)
    m[:, 1:-1] = mask
    d = np.diff(m, axis=1)
    ys, xs = np.nonzero(d == 1)
    _, xe = np.nonzero(d == -1)
    return ys, xs, xe


def components(mask: np.ndarray, eight: bool = True, want_labels: bool = False) -> Components:
    """Label the True pixels of `mask`. eight=True joins pixels that touch at a corner too."""
    mask = np.asarray(mask, bool)
    h, w = mask.shape
    ys, xs, xe = _runs(mask)
    n = len(ys)
    if n == 0:
        return Components(0, np.zeros((0, 4), np.int32), np.zeros(0, np.int64),
                          np.zeros((h, w), np.int32) if want_labels else None)
    parent = list(range(n))

    def find(a: int) -> int:
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return root

    first = np.searchsorted(ys, np.arange(h + 1))            # first run of each row
    s_l, e_l = xs.tolist(), xe.tolist()
    first_l = first.tolist()
    for y in range(1, h):
        a0, a1 = first_l[y - 1], first_l[y]
        b0, b1 = a1, first_l[y + 1]
        if a0 == a1 or b0 == b1:
            continue
        i, j = a0, b0
        while i < a1 and j < b1:
            s1, e1, s2, e2 = s_l[i], e_l[i], s_l[j], e_l[j]
            if (s1 <= e2 and s2 <= e1) if eight else (s1 < e2 and s2 < e1):
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[rb] = ra
            if e1 < e2:
                i += 1
            elif e2 < e1:
                j += 1
            else:
                i += 1
                j += 1
    roots = np.fromiter((find(i) for i in range(n)), np.int64, n)
    uniq, lab = np.unique(roots, return_inverse=True)
    count = len(uniq)
    boxes = np.empty((count, 4), np.int32)
    boxes[:, 0] = w
    boxes[:, 1] = h
    boxes[:, 2] = -1
    boxes[:, 3] = -1
    np.minimum.at(boxes[:, 0], lab, xs)
    np.minimum.at(boxes[:, 1], lab, ys)
    np.maximum.at(boxes[:, 2], lab, xe - 1)
    np.maximum.at(boxes[:, 3], lab, ys)
    sizes = np.zeros(count, np.int64)
    np.add.at(sizes, lab, xe - xs)
    labels = None
    if want_labels:
        labels = np.zeros((h, w), np.int32)
        for y, s, e, k in zip(ys.tolist(), s_l, e_l, lab.tolist()):
            labels[y, s:e] = k + 1
    return Components(count, boxes, sizes, labels)


def dilate(mask: np.ndarray, r: int) -> np.ndarray:
    """The mask grown by r pixels in every direction (a square)."""
    if r <= 0:
        return mask.copy()
    h, w = mask.shape
    tmp = mask.copy()
    for d in range(1, r + 1):
        tmp[:, d:] |= mask[:, :w - d]
        tmp[:, :w - d] |= mask[:, d:]
    out = tmp.copy()
    for d in range(1, r + 1):
        out[d:, :] |= tmp[:h - d, :]
        out[:h - d, :] |= tmp[d:, :]
    return out
