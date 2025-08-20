#!/usr/bin/env python3
"""
Generate per-season summaries from structured utterances.

Outputs per season under data/processed/sXX/summaries/:
- season_summary.json
- season_summary.md
"""

import argparse
import json
import math
import os
import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Tuple


STOPWORDS = set(
    """
    the a an and or of to in on for with at by from as is are was were be been being this that these those it its it's
    i you he she we they them us our your his her their not do does did done have has had having will would can could
    should may might must if then than so such but about over under out up down off into within without also just like
    get got going go went come came make makes made takes took say says said one two three four five six seven eight nine ten
    there's i'm you're we're they're it's don't can't won't didn't isn't aren't wasn't weren't
    """.split()
)


WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-']+")


def list_structured_files(processed_root: str, season_dir: str) -> List[str]:
    vdir = os.path.join(processed_root, season_dir, "structured")
    if not os.path.isdir(vdir):
        return []
    return [os.path.join(vdir, n) for n in sorted(os.listdir(vdir)) if n.lower().endswith(".jsonl")]


def tokenize(text: str) -> List[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


def top_bigrams(tokens: List[str], k: int = 25) -> List[Tuple[str, int]]:
    counts: Counter = Counter()
    for i in range(len(tokens) - 1):
        a, b = tokens[i], tokens[i + 1]
        if a in STOPWORDS or b in STOPWORDS:
            continue
        counts[f"{a} {b}"] += 1
    return counts.most_common(k)


def generate_summary_text(season: int, episodes: int, utterances: int, top_speakers: List[Tuple[str, int]], top_terms: List[Tuple[str, int]]) -> str:
    top_spk_text = ", ".join([f"{s} ({c})" for s, c in top_speakers[:5]])
    top_kw_text = ", ".join([t for t, _ in top_terms[:10]])
    return (
        f"Season {season} summary: {episodes} episodes, {utterances} utterances. "
        f"Most active speakers: {top_spk_text}. "
        f"Prominent keywords: {top_kw_text}."
    )


def write_json(path: str, obj: Dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def write_md(path: str, obj: Dict) -> None:
    lines: List[str] = []
    lines.append(f"# Season {obj['season']} summary")
    lines.append("")
    lines.append(f"Episodes: {obj['episodes']}")
    lines.append(f"Utterances: {obj['utterances']}")
    lines.append("")
    lines.append("## Top speakers")
    for s in obj.get("top_speakers", [])[:10]:
        lines.append(f"- {s['speaker']} ({s['count']})")
    lines.append("")
    lines.append("## Top keywords")
    lines.append(", ".join([t["term"] for t in obj.get("top_keywords", [])[:25]]))
    lines.append("")
    lines.append("## Top bigrams")
    lines.append(", ".join([t["term"] for t in obj.get("top_bigrams", [])[:25]]))
    lines.append("")
    lines.append("## Generated summary")
    lines.append(obj.get("generated_summary", ""))
    lines.append("")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def summarize_season(processed_root: str, season_dir: str) -> Tuple[str, str]:
    files = list_structured_files(processed_root, season_dir)
    if not files:
        return "", ""
    season_num = int(season_dir[1:])
    episodes_seen = set()
    utterances = 0
    tokens: List[str] = []
    speaker_counts: Counter = Counter()

    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                episodes_seen.add(obj.get("episode"))
                text = (obj.get("text") or "").strip()
                if not text:
                    continue
                utterances += 1
                speaker = (obj.get("speaker") or obj.get("speaker_raw") or "").strip().upper()
                if speaker:
                    speaker_counts[speaker] += 1
                tokens.extend([t for t in tokenize(text) if t not in STOPWORDS])

    top_terms = Counter(tokens).most_common(100)
    top_spk = speaker_counts.most_common(50)
    bigrams = top_bigrams(tokens, 100)

    obj = {
        "season": season_num,
        "episodes": len([e for e in episodes_seen if e is not None]),
        "utterances": utterances,
        "top_speakers": [{"speaker": s, "count": c} for s, c in top_spk],
        "top_keywords": [{"term": t, "count": c} for t, c in top_terms],
        "top_bigrams": [{"term": t, "count": c} for t, c in bigrams],
        "generated_summary": generate_summary_text(season_num, len(episodes_seen), utterances, top_spk, top_terms),
    }

    out_dir = os.path.join(processed_root, season_dir, "summaries")
    json_path = os.path.join(out_dir, "season_summary.json")
    md_path = os.path.join(out_dir, "season_summary.md")
    write_json(json_path, obj)
    write_md(md_path, obj)
    return json_path, md_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed-root", default="data/processed")
    ap.add_argument("--season", action="append", help="limit to specific seasons like s01; can repeat")
    args = ap.parse_args()

    seasons: List[str]
    if args.season:
        seasons = [s.lower() for s in args.season]
    else:
        seasons = [n for n in sorted(os.listdir(args.processed_root)) if re.match(r"^s\d{2}$", n)]

    wrote = []
    for sdir in seasons:
        j, m = summarize_season(args.processed_root, sdir)
        if j:
            wrote.append((sdir, j, m))
            print(f"[{sdir}] wrote {j} and {m}")


if __name__ == "__main__":
    main()


