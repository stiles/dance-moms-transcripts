#!/usr/bin/env python3
"""
Clean and reflow transcripts from VTT (or TXT) into analysis-ready text.

Outputs per episode:
- clean paragraphs: data/processed/sXX/clean/SxxExx.txt
- one sentence per line: data/processed/sXX/clean/SxxExx.sentences.txt

Default source is VTT to avoid depending on prior TXT dumps.
"""

import argparse
import os
import re
import sys
from typing import Iterable, List, Tuple


TS_RE = re.compile(r"\d\d:\d\d:\d\d\.\d{3}\s+-->\s+\d\d:\d\d:\d\d\.\d{3}")


def list_season_dirs(processed_root: str, seasons: List[str] | None) -> List[str]:
    if seasons:
        out = []
        for s in seasons:
            s = s.lower()
            if not s.startswith("s"):
                raise SystemExit(f"Invalid season spec '{s}'. Use like s01")
            path = os.path.join(processed_root, s)
            if os.path.isdir(path):
                out.append(path)
        return out
    # else, auto-discover sXX
    if not os.path.isdir(processed_root):
        return []
    return [
        os.path.join(processed_root, name)
        for name in sorted(os.listdir(processed_root))
        if re.match(r"^s\d{2}$", name)
    ]


def read_vtt_text(vtt_path: str) -> List[str]:
    lines: List[str] = []
    skip = False
    with open(vtt_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.startswith(("STYLE", "NOTE")):
                skip = True
                continue
            if skip and not line.strip():
                skip = False
                continue
            if skip:
                continue
            if not line.strip():
                continue
            if line.startswith("WEBVTT") or "line:" in line or TS_RE.search(line):
                continue
            # strip minimal HTML tags
            text = re.sub(r"</?(i|b|u)>", "", line)
            text = re.sub(r"<[^>]+>", "", text)
            lines.append(text)
    return dedupe_adjacent(lines)


def read_txt_lines(txt_path: str) -> List[str]:
    with open(txt_path, "r", encoding="utf-8") as f:
        raw = [ln.strip() for ln in f if ln.strip()]
    return dedupe_adjacent(raw)


def dedupe_adjacent(lines: List[str]) -> List[str]:
    out: List[str] = []
    prev = None
    for ln in lines:
        if ln != prev:
            out.append(ln)
            prev = ln
    return out


def normalize_text(text: str) -> str:
    # normalize quotes/dashes/ellipses
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace('"', '"')  # no-op for clarity
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2026", "...")
    # collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def remove_caption_notes(text: str) -> str:
    # remove bracketed or parenthetical notes
    # e.g., (cheering), [music], (sighs)
    return re.sub(r"\s*[\[(][^\])]+[\])]\s*", " ", text)


SENT_BOUNDARY = re.compile(r"(?<=[.!?])[\"]?\s+(?=[A-Z\(])")


def split_sentences(text: str) -> List[str]:
    # naive sentence splitter suitable for TV dialogue
    parts = re.split(r"(?<=[.!?])[\”\"']?\s+", text)
    # clean and filter
    out = [p.strip() for p in parts if p.strip()]
    return out


def reflow_to_paragraphs(lines: Iterable[str]) -> str:
    # join lines with spaces then normalize
    para = normalize_text(" ".join(lines))
    return para


def process_episode(src_path: str, remove_notes: bool, is_vtt: bool) -> Tuple[str, List[str]]:
    if is_vtt:
        lines = read_vtt_text(src_path)
    else:
        lines = read_txt_lines(src_path)
    # Normalize each line, optionally remove notes
    clean_lines: List[str] = []
    for ln in lines:
        t = normalize_text(ln)
        t = remove_caption_notes(t) if remove_notes else t
        if t:
            clean_lines.append(t)
    para = reflow_to_paragraphs(clean_lines)
    sents = split_sentences(para)
    return para, sents


def write_outputs(out_dir: str, base: str, paragraph: str, sentences: List[str]) -> None:
    os.makedirs(out_dir, exist_ok=True)
    para_path = os.path.join(out_dir, f"{base}.txt")
    with open(para_path, "w", encoding="utf-8") as f:
        f.write(paragraph + "\n")
    sent_path = os.path.join(out_dir, f"{base}.sentences.txt")
    with open(sent_path, "w", encoding="utf-8") as f:
        for s in sentences:
            f.write(s + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed-root", default="data/processed", help="root directory containing sXX subdirs")
    ap.add_argument("--season", action="append", help="limit to specific season(s) like s01; can repeat")
    ap.add_argument("--source", choices=["vtt", "txt"], default="vtt", help="input source to read")
    ap.add_argument("--remove-notes", action="store_true", help="remove bracketed/parenthetical caption notes like (cheering)")
    args = ap.parse_args()

    seasons = list_season_dirs(args.processed_root, args.season)
    if not seasons:
        print("No season directories found to clean.", file=sys.stderr)
        sys.exit(1)

    is_vtt = args.source == "vtt"

    for sdir in seasons:
        season_name = os.path.basename(sdir)
        src_dir = os.path.join(sdir, "vtt" if is_vtt else "txt")
        if not os.path.isdir(src_dir):
            print(f"[{season_name}] missing source dir: {src_dir}", file=sys.stderr)
            continue
        out_dir = os.path.join(sdir, "clean")

        files = [n for n in sorted(os.listdir(src_dir)) if n.lower().endswith(".vtt" if is_vtt else ".txt")]
        if not files:
            print(f"[{season_name}] no source files found in {src_dir}")
            continue
        for name in files:
            base = os.path.splitext(name)[0]
            src_path = os.path.join(src_dir, name)
            try:
                para, sents = process_episode(src_path, args.remove_notes, is_vtt)
                write_outputs(out_dir, base, para, sents)
                print(f"[{season_name}] cleaned {name} -> {out_dir}/{base}.*")
            except Exception as ex:
                print(f"[{season_name}] failed {name}: {ex}", file=sys.stderr)


if __name__ == "__main__":
    main()


