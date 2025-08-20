#!/usr/bin/env python3
import argparse
import json
import os
import re
from collections import Counter
from typing import List


def iter_structured_files(root: str, seasons: List[str] | None) -> List[str]:
    sdirs: List[str]
    if seasons:
        sdirs = [os.path.join(root, s.lower()) for s in seasons]
    else:
        sdirs = [
            os.path.join(root, name)
            for name in sorted(os.listdir(root))
            if re.match(r"^s\d{2}$", name)
        ]
    files: List[str] = []
    for sdir in sdirs:
        p = os.path.join(sdir, "structured")
        if not os.path.isdir(p):
            continue
        for n in sorted(os.listdir(p)):
            if n.lower().endswith(".jsonl"):
                files.append(os.path.join(p, n))
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed-root", default="data/processed")
    ap.add_argument("--season", action="append")
    args = ap.parse_args()

    files = iter_structured_files(args.processed_root, args.season)
    counts = Counter()
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                spk = (obj.get("speaker") or obj.get("speaker_raw") or "").strip().upper()
                if spk:
                    counts[spk] += 1

    # Print top 50 unknown speaker tags not in the mapping (approx by heuristic: ALL CAPS)
    for spk, cnt in counts.most_common(200):
        print(f"{spk},{cnt}")


if __name__ == "__main__":
    main()


