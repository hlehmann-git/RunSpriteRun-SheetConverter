"""WebP files and colour clean-up. Pure logic; shows nothing.

A lossless WebP keeps every colour exactly, like a PNG. A lossy WebP is compressed like a JPEG: the edges of pixel art
are smudged into many slightly different colours. Clean-up merges each rare colour into the most common colour that
looks almost the same. It only ever picks colours already in the picture, never a mixed one, and leaves transparent
pixels transparent."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

STRENGTHS = {"Very low": 16, "Low": 24, "Medium-low": 32, "Medium": 40,       # how far apart (RGB distance, 0 to 441)
             "Medium-high": 48, "High": 56, "Very high": 64}                 # two colours may be and still merge
BLENDS = {name: True for name in STRENGTHS}           # whether rare in-between colours (smudged edges) are merged too
EDGE_ONLY = 0.3                                       # a blend has fewer than this share of pixels inside a patch of its colour
RARE = 0.005                                          # a colour on fewer than this share of pixels may be an edge blend
MAX_ROUNDS = 1024                                     # the most extra colours kept as real detail
DEFAULT_STRENGTH = "Medium"


def strength_from_text(text: str) -> str | None:
    """The strength named by `text` ("medium-high", "Very low", "very_low" ...), or None for a name that is not one."""
    want = text.strip().lower().replace("_", " ").replace("-", " ")
    return next((n for n in STRENGTHS if n.lower().replace("-", " ") == want), None)


def webp_kind(source: str | Path | bytes) -> str:
    """'lossy' or 'lossless' for a WebP file (a file with any lossy frame or picture counts as lossy), '' otherwise."""
    if isinstance(source, (str, Path)):
        try:
            with open(source, "rb") as fh:
                data = fh.read()
        except OSError:
            return ""
    else:
        data = source
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return ""
    lossy = lossless = False

    def walk(start: int, end: int, depth: int) -> None:
        nonlocal lossy, lossless
        pos = start
        while pos + 8 <= end:
            tag = data[pos:pos + 4]
            size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
            body = pos + 8
            if tag == b"VP8 ":
                lossy = True
            elif tag == b"VP8L":
                lossless = True
            elif tag == b"ANMF" and depth == 0:
                walk(body + 16, min(end, body + size), 1)     # an animation frame: 16 bytes of header, then its chunks
            pos = body + size + (size & 1)                    # chunks are padded to an even length

    walk(12, len(data), 0)
    if lossy:
        return "lossy"
    return "lossless" if lossless else ""


@dataclass
class CleanResult:
    frames: list[np.ndarray]           # RGBA, the same shapes as given
    before: int                        # solid colours before
    after: int                         # solid colours after


def _pack(rgb: np.ndarray) -> np.ndarray:
    a = rgb.astype(np.int64)
    return (a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]


def colour_count(frames: list[np.ndarray]) -> int:
    """How many different solid colours (alpha 128 or more) the RGBA frames hold together."""
    keys = [_pack(f[..., :3])[f[..., 3] >= 128] for f in frames]
    keys = [k for k in keys if k.size]
    return int(np.unique(np.concatenate(keys)).size) if keys else 0


def _nearest(points: np.ndarray, kept: np.ndarray, chunk: int = 4096) -> tuple[np.ndarray, np.ndarray]:
    """For each point, the index of the nearest kept colour and the squared distance to it."""
    idx = np.empty(len(points), np.int64)
    dist = np.empty(len(points))
    for s in range(0, len(points), chunk):
        d = ((points[s:s + chunk, None, :] - kept[None, :, :]) ** 2).sum(-1)
        idx[s:s + chunk] = d.argmin(1)
        dist[s:s + chunk] = d.min(1)
    return idx, dist


def _blends(points: np.ndarray, kept: np.ndarray, limit: float, chunk: int = 1024) -> np.ndarray:
    """For each point that lies on (or near) the line between two kept colours (a blend of the two, as a smudged edge
    is), the index of the nearer of the two; -1 for a point that is not a blend."""
    out = np.full(len(points), -1, np.int64)
    n = len(kept)
    if n < 2 or not len(points):
        return out
    ia, ib = np.triu_indices(n, 1)
    A, AB = kept[ia], kept[ib] - kept[ia]
    ab2 = np.maximum((AB * AB).sum(1), 1)
    for s in range(0, len(points), chunk):
        p = points[s:s + chunk, None, :]
        t = np.clip(((p - A) * AB).sum(-1) / ab2, 0, 1)
        d = ((A + t[..., None] * AB - p) ** 2).sum(-1)
        k = d.argmin(1)
        rows = np.arange(len(k))
        ok = d[rows, k] <= limit
        near = np.where(t[rows, k] < 0.5, ia[k], ib[k])
        out[s:s + chunk] = np.where(ok, near, -1)
    return out


def _patch_share(keys: list[np.ndarray], solid: list[np.ndarray], values: np.ndarray, rgb: np.ndarray,
                 limit: float) -> np.ndarray:
    """For each colour, the share of its pixels whose four neighbours are all close to it (inside a patch of that
    colour). A real shade fills patches; a smudged edge between two colours is a thin line with few such pixels."""
    inside = np.zeros(len(values))
    total = np.zeros(len(values))
    for k, s in zip(keys, solid):
        idx = np.searchsorted(values, np.where(s, k, values[0]))
        col = rgb[idx]
        ok = s.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nb = np.roll(np.roll(col, dy, 0), dx, 1)
            nbs = np.roll(np.roll(s, dy, 0), dx, 1)
            ok &= nbs & (((col - nb) ** 2).sum(-1) <= limit)
        ok[0, :] = ok[-1, :] = False
        ok[:, 0] = ok[:, -1] = False
        total += np.bincount(idx[s], minlength=len(values))
        inside += np.bincount(idx[ok], minlength=len(values))
    return inside / np.maximum(total, 1)


def clean_up(frames: list[np.ndarray], strength: str = DEFAULT_STRENGTH) -> CleanResult:
    """Merge near-identical colours across all the RGBA frames together, so every frame gets the same palette.
    1. The main colours (each on at least 0.5% of the pixels), most used first, are kept unless they are within the
       strength's distance of a kept colour, which they then join.
    2. Every other colour joins the nearest kept colour within that distance; or, if it lies between two kept colours
       (a smudged edge between them), the nearer of the two.
    3. What is left is real detail. The most used left-over colour is kept and takes its own near colours and blends;
       this repeats until every colour has a place.
    Only colours already in the picture are used. Pixels with alpha under 128 become fully transparent, the rest
    fully solid."""
    limit = float(STRENGTHS[strength] ** 2)
    step = STRENGTHS[strength]
    solid = [f[..., 3] >= 128 for f in frames]
    keys = [_pack(f[..., :3]) for f in frames]
    parts = [k[s] for k, s in zip(keys, solid) if s.any()]
    if not parts:
        return CleanResult([f.copy() for f in frames], 0, 0)
    values, counts = np.unique(np.concatenate(parts), return_counts=True)
    total = int(counts.sum())
    rgb = np.stack([(values >> 16) & 255, (values >> 8) & 255, values & 255], axis=1).astype(np.float64)
    target = np.arange(len(values))
    edge_like = (_patch_share(keys, solid, values, rgb, limit) < EDGE_ONLY) if BLENDS[strength] else \
        np.zeros(len(values), bool)

    kept: list[int] = []                                     # 1. the main colours
    main = np.nonzero(counts >= RARE * total)[0]
    for i in main[np.argsort(-counts[main], kind="stable")]:
        if kept:
            d = ((rgb[kept] - rgb[i]) ** 2).sum(1)
            j = int(np.argmin(d))
            if d[j] <= limit:
                target[i] = kept[j]
                continue
        kept.append(int(i))
    if not kept:                                             # no colour is common: start from the most used one
        kept.append(int(np.argmax(counts)))
    rest = np.setdiff1d(np.arange(len(values)), np.array(kept + [i for i in main if target[i] != i]))

    kr = rgb[kept]                                           # 2. close to a main colour, or a blend of two
    idx, dist = _nearest(rgb[rest], kr)
    close = dist <= limit
    target[rest[close]] = np.array(kept)[idx[close]]
    rest = rest[~close]
    bl = _blends(rgb[rest], kr, limit) if BLENDS[strength] else np.full(len(rest), -1)
    bl[~edge_like[rest]] = -1                                #    (only a thin edge counts as a blend, not a real shade)
    target[rest[bl >= 0]] = np.array(kept)[bl[bl >= 0]]
    rest = rest[bl < 0]

    rounds = 0                                               # 3. real detail, most used first, one per round:
    while len(rest) and rounds < MAX_ROUNDS:                 #    it is kept and takes its own near colours and blends
        rounds += 1
        head = int(rest[np.argmax(counts[rest])])
        kept.append(head)
        others = rest[rest != head]
        p = rgb[others]
        near = ((p - rgb[head]) ** 2).sum(1) <= limit
        blend = np.zeros(len(others), bool)
        to = np.full(len(others), head)
        if len(kept) > 1 and BLENDS[strength]:
            pair_kept = rgb[kept[:-1]]
            A, AB = pair_kept, rgb[head] - pair_kept         # the lines from each kept colour to the new one
            ab2 = np.maximum((AB * AB).sum(1), 1)
            for s0 in range(0, len(p), 1024):
                q = p[s0:s0 + 1024, None, :]
                t = np.clip(((q - A) * AB).sum(-1) / ab2, 0, 1)
                d = ((A + t[..., None] * AB - q) ** 2).sum(-1)
                k = d.argmin(1)
                rows = np.arange(len(k))
                ok = (d[rows, k] <= limit) & edge_like[others[s0:s0 + 1024]]
                blend[s0:s0 + 1024] = ok
                to[s0:s0 + 1024] = np.where(t[rows, k] < 0.5, np.array(kept[:-1])[k], head)
        take = near | blend
        target[others[near]] = head
        target[others[blend & ~near]] = to[blend & ~near]
        rest = others[~take]
    if len(rest):                                            # very many colours (a photo): the nearest kept colour
        idx, _ = _nearest(rgb[rest], rgb[kept])
        target[rest] = np.array(kept)[idx]

    new_values = values[target]
    out = []
    for f, k, s in zip(frames, keys, solid):
        g = np.zeros_like(f)
        if s.any():
            new = new_values[np.searchsorted(values, k[s])]
            g[..., 0][s] = (new >> 16) & 255
            g[..., 1][s] = (new >> 8) & 255
            g[..., 2][s] = new & 255
            g[..., 3][s] = 255
        out.append(g)
    return CleanResult(out, int(len(values)), len(set(kept)))


def clean_note(lossy: bool, before: int, after: int | None, strength: str | None) -> str:
    """The line shown under the Clean up / Reduce colours switch. A lossy WebP's colours are smudged by
    compression; anything else has exact colours, so the wording (and the switch's own label) differs, but
    both merge the same way, with the same strengths, to colours already in the picture."""
    if lossy:
        if after is None:
            return (f"Lossy WebP: {before} colours, many of them smudged edges. Tick Clean up colours to merge "
                    "them back to a small palette.")
        return f"Lossy WebP: {before} colours, cleaned up to {after} ({strength})."
    if after is None:
        return f"{before} colours used. Tick Reduce colours to merge the ones closest in value."
    return f"{before} colours, reduced to {after} ({strength})."
