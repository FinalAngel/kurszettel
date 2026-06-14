#!/usr/bin/env python3
"""Wait until Yahoo stops rate-limiting this IP, then generate the issues.
Used once for the initial seed; day-to-day you just run generate.py directly."""
import sys, time, subprocess, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

def probe():
    req = urllib.request.Request(
        "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=5d&interval=1d",
        headers=UA)
    try:
        return urllib.request.urlopen(req, timeout=10).status == 200
    except Exception:
        return False

ready = False
for i in range(80):  # up to ~40 min
    if probe():
        print(f"[ready after {i} polls]", flush=True)
        ready = True
        break
    print(f"[throttled — poll {i}, waiting 30s]", flush=True)
    time.sleep(30)

if not ready:
    print("[gave up waiting for rate-limit to clear]", flush=True)
    sys.exit(1)

for cmd in ("daily", "weekly", "monthly"):
    print(f"=== generate {cmd} ===", flush=True)
    r = subprocess.run([sys.executable, "generate.py", cmd])
    print(f"=== {cmd} exit {r.returncode} ===", flush=True)
    time.sleep(3)
print("ALL DONE", flush=True)
