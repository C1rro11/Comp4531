#!/usr/bin/env python3
"""
trainer.py  —  CLI tool for managing XGBoost seat-detection training data.

All commands talk to the running Flask server (localhost:5000).
Run ``python server.py`` first, then use this CLI.

Usage:
  python trainer.py collect <empty|occupied|hoarded> [count]
      Start auto-collecting <count> windows (default 30).
      Each window is labelled with the given class.

  python trainer.py stop
      Stop the active collection and save results.

  python trainer.py status
      Show collection progress and class distribution.

  python trainer.py train
      Train the XGBoost model on all collected data.

  python trainer.py clear
      Delete all training data and the saved model.

  python trainer.py model
      Show model status (trained? sample count? distribution).
"""

import sys
import time

import requests

SERVER_URL = "http://localhost:5000"


def collect(label, count):
    resp = requests.post(
        f"{SERVER_URL}/api/collect/start",
        json={"class": label, "count": count},
        timeout=5,
    )
    data = resp.json()
    if resp.status_code == 200:
        print(f"  {data['message']}")
    else:
        print(f"  Error: {data['message']}")
        sys.exit(1)


def stop():
    resp = requests.post(f"{SERVER_URL}/api/collect/stop", timeout=5)
    print(f"  {resp.json()['message']}")


def status():
    resp = requests.get(f"{SERVER_URL}/api/collect/status", timeout=5)
    data = resp.json()
    if data["active"]:
        print(f"  Collecting '{data['class']}': {data['collected']}/{data['target']}")
    else:
        print("  No active collection.")
    print(f"  Total samples: {data['total_samples']}")
    dist = data.get("distribution", {})
    for cls, cnt in sorted(dist.items()):
        bar = "#" * min(cnt // 2, 30)
        print(f"    {cls:10s}  {cnt:4d}  {bar}")


def train():
    resp = requests.post(f"{SERVER_URL}/api/train", timeout=30)
    data = resp.json()
    if resp.status_code == 200:
        print(f"  {data['message']}")
        dist = data.get("distribution", {})
        for cls, cnt in sorted(dist.items()):
            print(f"    {cls}: {cnt}")
    else:
        print(f"  Error: {data['message']}")
        sys.exit(1)


def clear():
    ans = input("  Delete all training data & model? (yes/no): ").strip().lower()
    if ans != "yes":
        print("  Aborted.")
        return
    resp = requests.post(f"{SERVER_URL}/api/clear", timeout=5)
    print(f"  {resp.json()['message']}")


def model():
    resp = requests.get(f"{SERVER_URL}/api/model/status", timeout=5)
    data = resp.json()
    print(f"  Model trained: {data['trained']}")
    print(f"  Total samples: {data['total_samples']}")
    dist = data.get("distribution", {})
    for cls, cnt in sorted(dist.items()):
        print(f"    {cls:10s}: {cnt}")


USAGE = """Usage:
  python trainer.py collect <empty|occupied|hoarded> [count]
  python trainer.py stop
  python trainer.py status
  python trainer.py train
  python trainer.py clear
  python trainer.py model"""

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(USAGE)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "collect":
        if len(sys.argv) < 3:
            print("  Usage: python trainer.py collect <empty|occupied|hoarded> [count]")
            sys.exit(1)
        label = sys.argv[2].lower()
        if label not in ("empty", "occupied", "hoarded"):
            print("  Label must be: empty, occupied, or hoarded")
            sys.exit(1)
        n = int(sys.argv[3]) if len(sys.argv) >= 4 else 30
        collect(label, n)

    elif cmd == "stop":
        stop()

    elif cmd == "status":
        status()

    elif cmd == "train":
        train()

    elif cmd == "clear":
        clear()

    elif cmd == "model":
        model()

    else:
        print(f"  Unknown command: '{cmd}'")
        print(USAGE)
        sys.exit(1)
