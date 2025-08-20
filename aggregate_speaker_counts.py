#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
from collections import defaultdict
from typing import Dict, List, Tuple


def iter_structured_files(root: str) -> List[str]:
    files: List[str] = []
    if not os.path.isdir(root):
        return files
    for name in sorted(os.listdir(root)):
        if not re.match(r"^s\d{2}$", name):
            continue
        p = os.path.join(root, name, "structured")
        if not os.path.isdir(p):
            continue
        for n in sorted(os.listdir(p)):
            if n.lower().endswith(".jsonl"):
                files.append(os.path.join(p, n))
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed-root", default="data/processed")
    ap.add_argument("--out", default="data/processed/speaker_counts.csv")
    args = ap.parse_args()

    counts: Dict[Tuple[int, int, str], int] = defaultdict(int)
    roles: Dict[str, str] = {}

    for fp in iter_structured_files(args.processed_root):
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                season = obj.get("season")
                episode = obj.get("episode")
                speaker = (obj.get("speaker") or obj.get("speaker_raw") or "").strip().upper()
                role = (obj.get("speaker_role") or "").strip()
                if not season or not episode or not speaker:
                    continue
                counts[(int(season), int(episode), speaker)] += 1
                if speaker and role and speaker not in roles:
                    roles[speaker] = role

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["season", "episode", "speaker", "role", "utterance_count"])
        for (season, episode, speaker), cnt in sorted(counts.items()):
            w.writerow([season, episode, speaker, roles.get(speaker, ""), cnt])

    print(f"Wrote {args.out} ({len(counts)} rows)")


if __name__ == "__main__":
    main()


