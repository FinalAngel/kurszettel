"""Back-testing for the self-improvement loop.

Ledger stores a daily snapshot of every name's per-lens sub-scores and its
price. Because the sub-scores are persisted, we can *re-score* the whole
history under any candidate set of lens weights without re-fetching anything,
and ask a simple question:

    did the names we scored highest actually go on to outperform the names
    we scored lowest?

The objective is the average, across every snapshot, of the forward-return
*spread* between the top third and the bottom third of names as ranked by the
candidate score. Higher spread = the scoring separated winners from losers
better. improve.py searches the weight space to maximise it.

This is rank-based, so it is unaffected by overall market drift, and it needs
no labels — only the prices the market subsequently printed.
"""

import os
import glob
import json


def load_history(snap_dir):
    """All snapshots, oldest first."""
    snaps = []
    for p in sorted(glob.glob(os.path.join(snap_dir, "*.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                snaps.append(json.load(f))
        except Exception:
            pass
    return snaps


def composite(breakdown, lens_w):
    """Recompute a 0..100 composite from stored per-lens sub-scores."""
    keys = [k for k in lens_w if k in breakdown and breakdown[k] is not None]
    tw = sum(lens_w[k] for k in keys)
    if not tw:
        return 50.0
    return sum(breakdown[k] / 100.0 * lens_w[k] for k in keys) / tw * 100.0


def _spread_for_pair(cur, fut, lens_w, min_names):
    fut_px = {r["symbol"]: r.get("price") for r in fut["recs"]}
    rows = []
    for r in cur["recs"]:
        bd, p0 = r.get("breakdown"), r.get("price")
        p1 = fut_px.get(r["symbol"])
        if not bd or not p0 or not p1:
            continue
        rows.append((composite(bd, lens_w), p1 / p0 - 1.0))
    if len(rows) < min_names:
        return None
    rows.sort(key=lambda x: x[0])
    k = max(1, len(rows) // 3)
    bottom = sum(f for _, f in rows[:k]) / k
    top = sum(f for _, f in rows[-k:]) / k
    return top - bottom


def objective(snaps, weights, horizons=(1, 2, 3), min_names=8):
    """Mean top-vs-bottom forward-return spread over several horizons.
    Returns (value, n_samples); value is None when there is not enough
    history to evaluate."""
    lens_w = weights["lenses"]
    vals = []
    for h in horizons:
        for i in range(len(snaps) - h):
            s = _spread_for_pair(snaps[i], snaps[i + h], lens_w, min_names)
            if s is not None:
                vals.append(s)
    if not vals:
        return None, 0
    return sum(vals) / len(vals), len(vals)


def evaluatable(snaps, min_names=8):
    """Cheap check: is there enough overlapping price history to back-test?"""
    val, n = objective(snaps, {"lenses": {"trend": 1, "momentum": 1,
                        "analyst": 1, "position": 1}}, min_names=min_names)
    return val is not None
