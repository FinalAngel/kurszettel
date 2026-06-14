#!/usr/bin/env python3
"""
Ledger's self-improvement loop.

Every time a command runs in this repo, this engine is launched in the
background and spends its time budget (default 5 minutes) trying to make the
tool *measurably* better — then keeps a change only if it both improves the
back-test and leaves the test suite green. Everything it touches is backed up
first and rolled back on any failure, so a bad idea can never degrade the repo.

What it actually does, in order:

  1. Self-heal — if the test suite is red (e.g. a hand-edit or a previous bad
     tune), try to restore a good state before doing anything else.
  2. Tune — back-test the scoring weights against what prices actually did
     next, search for a weight set that separates winners from losers better,
     and adopt it only on a material, test-passing improvement.
  3. (optional) LLM code pass — if, and only if, you opt in twice
     (config flag + LEDGER_ALLOW_LLM=1) and the `claude` CLI is present, let an
     agent propose code improvements, each gated by the same green-tests rule.

Run manually:  python3 improve.py --seconds 300
"""

import os
import sys
import json
import time
import errno
import random
import shutil
import argparse
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from lib import backtest, signals  # noqa: E402

DATA = os.path.join(ROOT, "data")
SNAP = os.path.join(DATA, "snapshots")
WEIGHTS = os.path.join(ROOT, "weights.json")
LOG = os.path.join(DATA, "improvements.log")
LOCK = os.path.join(DATA, ".improve.lock")
BK = os.path.join(DATA, "backups")
LENS_KEYS = ["trend", "momentum", "analyst", "position"]


# ---- infra -----------------------------------------------------------
def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    try:
        os.makedirs(DATA, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError as e:
        return e.errno == errno.EPERM


def acquire_lock():
    os.makedirs(DATA, exist_ok=True)
    if os.path.exists(LOCK):
        try:
            if _alive(int(open(LOCK).read().strip())):
                return False
        except Exception:
            pass
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))
    return True


def release_lock():
    try:
        os.remove(LOCK)
    except OSError:
        pass


def run_tests():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tests.py")],
                       capture_output=True, text=True,
                       env=dict(os.environ, LEDGER_NO_IMPROVE="1"))
    return r.returncode == 0, (r.stdout + r.stderr)


def backup(paths):
    d = os.path.join(BK, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(d, exist_ok=True)
    saved = {}
    for p in paths:
        if os.path.exists(p):
            dst = os.path.join(d, os.path.relpath(p, ROOT).replace(os.sep, "__"))
            shutil.copy2(p, dst)
            saved[p] = dst
        else:
            saved[p] = None  # remember it was absent
    return saved


def restore(saved):
    for p, src in saved.items():
        if src is None:
            if os.path.exists(p):
                os.remove(p)
        else:
            shutil.copy2(src, p)


# ---- self-heal -------------------------------------------------------
def self_heal():
    ok, _ = run_tests()
    if ok:
        return True
    log("baseline tests are RED — attempting self-heal")
    if os.path.exists(WEIGHTS):
        saved = backup([WEIGHTS])
        os.remove(WEIGHTS)
        ok2, _ = run_tests()
        if ok2:
            log("self-heal: removed a bad weights.json — tests green again")
            return True
        restore(saved)
    log("self-heal could not green the tests; leaving repo untouched this run")
    return False


# ---- weight tuning ---------------------------------------------------
def _random_w(rng):
    return {k: rng.uniform(2.0, 50.0) for k in LENS_KEYS}


def _perturb(lw, rng, scale=6.0):
    return {k: max(1.0, lw[k] + rng.gauss(0, scale)) for k in LENS_KEYS}


def _normed(lw):
    s = sum(lw.values()) or 1.0
    return {k: round(v / s * 100, 2) for k, v in lw.items()}


def tune(snaps, end, rng):
    base_w = signals.load_weights()
    base_obj, n = backtest.objective(snaps, base_w)
    if base_obj is None:
        return None
    best_lw, best_obj, cur, iters = dict(base_w["lenses"]), base_obj, \
        dict(base_w["lenses"]), 0
    while time.monotonic() < end:
        iters += 1
        cand = _random_w(rng) if iters % 25 == 0 else _perturb(cur, rng)
        obj, _ = backtest.objective(
            snaps, {"lenses": cand, "thresholds": base_w["thresholds"]})
        if obj is None:
            continue
        if obj > best_obj + 1e-9:
            best_obj, best_lw, cur = obj, cand, cand
        elif obj >= best_obj - abs(best_obj) * 0.05:
            cur = cand  # wander across near-equal plateaus
    return {"base_obj": base_obj, "best_obj": best_obj, "best_lw": best_lw,
            "iters": iters, "n": n, "thresholds": base_w["thresholds"]}


def adopt(res):
    gain = res["best_obj"] - res["base_obj"]
    rel = gain / (abs(res["base_obj"]) + 1e-12)
    if not (gain > 1e-5 and rel > 0.02):  # ignore noise-level "wins"
        log(f"tuning: no material gain after {res['iters']} candidates "
            f"(spread {res['base_obj']:.5f}; best {res['best_obj']:.5f}) — "
            f"current weights kept")
        return False
    saved = backup([WEIGHTS])
    out = {
        "lenses": _normed(res["best_lw"]),
        "thresholds": res["thresholds"],
        "_meta": {
            "tuned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "objective": round(res["best_obj"], 6),
            "prev_objective": round(res["base_obj"], 6),
            "samples": res["n"], "candidates_tried": res["iters"],
        },
    }
    with open(WEIGHTS, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    ok, tout = run_tests()
    if ok:
        log(f"ADOPTED new weights: forward-return spread "
            f"{res['base_obj']:.5f} -> {res['best_obj']:.5f} "
            f"(+{rel*100:.1f}%, {res['n']} samples) {_normed(res['best_lw'])}")
        return True
    restore(saved)
    tail = (tout.strip().splitlines() or ["?"])[-1]
    log(f"tuned weights FAILED tests — reverted ({tail})")
    return False


# ---- optional LLM code pass -----------------------------------------
def llm_enabled(cfg):
    return (cfg.get("llm_code_improve") and
            os.environ.get("LEDGER_ALLOW_LLM") == "1" and
            shutil.which("claude"))


PROMPT = (
    "You are improving the Ledger repo (a Python static-site stock digest). "
    "Make ONE small, safe improvement to code quality, correctness, robustness "
    "or docs WITHOUT changing the CLI or output format. Do not add network "
    "calls or dependencies. After editing, the suite `python3 tests.py` MUST "
    "still pass. Keep the change minimal and self-contained."
)


def llm_pass(end, cfg):
    budget = max(30, int(end - time.monotonic()))
    py = [p for p in _py_files()]
    saved = backup(py + [WEIGHTS])
    log(f"LLM pass: invoking claude (budget ~{budget}s) on {len(py)} files")
    try:
        subprocess.run(
            ["claude", "-p", PROMPT, "--permission-mode", "acceptEdits"],
            cwd=ROOT, timeout=budget,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=dict(os.environ, LEDGER_NO_IMPROVE="1"))
    except Exception as e:
        log(f"LLM pass aborted ({type(e).__name__}) — restoring")
        restore(saved)
        return
    ok, out = run_tests()
    if ok:
        log("LLM pass: change kept (tests green)")
    else:
        restore(saved)
        log("LLM pass: tests went red — fully reverted")


def _py_files():
    out = []
    for base in (ROOT, os.path.join(ROOT, "lib")):
        for fn in os.listdir(base):
            if fn.endswith(".py"):
                out.append(os.path.join(base, fn))
    return out


# ---- main ------------------------------------------------------------
def load_cfg():
    try:
        with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
            return json.load(f).get("self_improve", {}) or {}
    except Exception:
        return {}


def main():
    if os.environ.get("LEDGER_NO_IMPROVE") == "1":
        return  # recursion guard: never improve from inside an improvement
    cfg = load_cfg()
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=cfg.get("seconds", 300))
    args = ap.parse_args()

    if not acquire_lock():
        log("another self-improve run is active — skipping")
        return
    try:
        end = time.monotonic() + max(10, args.seconds)
        log(f"── self-improve start (budget {args.seconds}s, pid {os.getpid()})")
        if not self_heal():
            return
        snaps = backtest.load_history(SNAP)
        if not backtest.evaluatable(snaps):
            log(f"insufficient price history to back-test "
                f"({len(snaps)} snapshot(s)) — tuning will begin once a few "
                f"daily runs have accumulated. Nothing changed this run.")
        else:
            res = tune(snaps, end, random.Random(int(time.time() * 1000) & 0xFFFFFFFF))
            if res:
                adopt(res)
        if llm_enabled(cfg) and time.monotonic() < end:
            llm_pass(end, cfg)
        log("── self-improve done")
    finally:
        release_lock()


if __name__ == "__main__":
    main()
