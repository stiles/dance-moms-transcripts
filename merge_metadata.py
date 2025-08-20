#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import sys
from typing import Dict, List, Tuple


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def iter_season_index_paths(processed_root: str) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    if not os.path.isdir(processed_root):
        return out
    for name in sorted(os.listdir(processed_root)):
        if not re.match(r"^s\d{2}$", name):
            continue
        season_num = int(name[1:])
        idx_path = os.path.join(processed_root, name, f"s{season_num:02d}_index.csv")
        if os.path.isfile(idx_path):
            out.append((season_num, idx_path))
    return out


def build_metadata_map(episodes: List[Dict]) -> Dict[Tuple[int, int], Dict]:
    mp: Dict[Tuple[int, int], Dict] = {}
    for row in episodes:
        try:
            season = int(str(row.get("season", "")).strip())
        except Exception:
            continue
        epi_raw = str(row.get("episode_in_season", "")).strip()
        if not epi_raw.isdigit():
            # skip specials without in-season number
            continue
        episode = int(epi_raw)
        mp[(season, episode)] = row
    return mp


ENRICH_COLS = [
    "season_title",
    "overall_episode",
    "title",
    "original_air_date",
    "us_viewers_millions",
    "production_code",
    "notes",
]


def enrich_index(index_path: str, season: int, meta_map: Dict[Tuple[int, int], Dict], out_path: str) -> int:
    with open(index_path, "r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
    for r in rows:
        try:
            episode = int(str(r.get("episode", "")).strip())
        except Exception:
            episode = None
        md = meta_map.get((season, episode)) if episode is not None else None
        for col in ENRICH_COLS:
            r[col] = md.get(col, "") if md else ""
        # mark whether metadata was matched
        r["metadata_matched"] = bool(md)

    fieldnames = list(rows[0].keys()) if rows else []
    # ensure enrich columns are present and in a stable order at the end
    for col in ENRICH_COLS + ["metadata_matched"]:
        if col not in fieldnames:
            fieldnames.append(col)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return sum(1 for r in rows if r.get("metadata_matched"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", default="data/metadata/episodes.json", help="path to parsed Wikipedia metadata json")
    ap.add_argument("--processed-root", default="data/processed", help="root of processed seasons")
    ap.add_argument("--out-overall", default="data/processed/episodes_index_enriched.csv", help="path for concatenated enriched index")
    args = ap.parse_args()

    episodes = read_json(args.episodes)
    meta_map = build_metadata_map(episodes)

    season_indices = iter_season_index_paths(args.processed_root)
    if not season_indices:
        print("No season indices found to enrich.", file=sys.stderr)
        sys.exit(1)

    enriched_paths: List[str] = []
    total_matched = 0
    for season, idx_path in season_indices:
        out_path = os.path.join(os.path.dirname(idx_path), f"s{season:02d}_index_enriched.csv")
        matched = enrich_index(idx_path, season, meta_map, out_path)
        enriched_paths.append(out_path)
        total_matched += matched
        print(f"Enriched s{season:02d}: matched {matched} rows -> {out_path}")

    # Concatenate to overall
    headers = None
    rows: List[Dict] = []
    for p in enriched_paths:
        with open(p, "r", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            if headers is None:
                headers = rdr.fieldnames
            for r in rdr:
                rows.append(r)

    if headers is None:
        print("No enriched rows found.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(args.out_overall), exist_ok=True)
    with open(args.out_overall, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"Wrote {args.out_overall} ({len(rows)} rows). Total matched: {total_matched}")


if __name__ == "__main__":
    main()


