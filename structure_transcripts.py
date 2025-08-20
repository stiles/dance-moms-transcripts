#!/usr/bin/env python3
"""
Structure transcripts into utterances with speakers and timing.

Reads VTT files and writes one JSONL per episode under:
  data/processed/sXX/structured/SxxExx.jsonl

Each record:
  - season, episode, episode_id (e.g., S02E01)
  - start (seconds), end (seconds)
  - speaker_raw, speaker (normalized), speaker_role (blank for now)
  - text (cleaned)
  - is_caption_note (bool)
"""

import argparse
import json
import os
import re
import sys
from typing import Dict, Iterable, Iterator, List, Optional, Tuple


TS_RE = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d{3})\s+-->\s+(\d\d):(\d\d):(\d\d)\.(\d{3})")


def parse_time_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def normalize_text(text: str) -> str:
    text = re.sub(r"</?(i|b|u)>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2026", "...")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_note_only(text: str) -> bool:
    t = text.strip()
    # note if entire text is within [] or () and contains no letters outside
    if re.fullmatch(r"[\[(].+?[\])]", t):
        return True
    # common cues like (cheering), [music]
    core = re.sub(r"[\[(]|[\])]", "", t).strip()
    if core and re.fullmatch(r"[A-Za-z\s'!-]+", core):
        # still treat as note if wrapped originally
        if (t.startswith("(") and t.endswith(")")) or (t.startswith("[") and t.endswith("]")):
            return True
    return False


SPEAKER_RE = re.compile(r"^([A-Z][A-Z0-9 &'./-]{1,40})(?:\s*\([^)]*\))?\s*:\s*(.*)$")


def extract_speaker(text: str) -> Tuple[Optional[str], Optional[str], str]:
    """Return (speaker_raw, speaker_norm, remainder_text)."""
    m = SPEAKER_RE.match(text)
    if not m:
        return None, None, text
    raw = m.group(1).strip()
    remainder = m.group(2).strip()
    # ensure it's really a shouty speaker tag
    if raw.upper() != raw:
        return None, None, text
    # collapse multiple spaces
    norm = re.sub(r"\s+", " ", raw)
    # remove slashes spaces around ' / '
    norm = norm.replace(" / ", "/")
    return raw, norm, remainder or text


def parse_vtt_cues(vtt_path: str) -> Iterator[Tuple[float, float, List[str]]]:
    with open(vtt_path, "r", encoding="utf-8") as f:
        lines = [ln.rstrip("\n") for ln in f]
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        i += 1
        if not line or line.startswith("WEBVTT") or line.startswith("STYLE") or line.startswith("NOTE"):
            # skip until blank following NOTE/STYLE blocks
            if line.startswith(("STYLE", "NOTE")):
                while i < n and lines[i].strip():
                    i += 1
            continue
        m = TS_RE.match(line)
        if not m:
            continue
        start = parse_time_to_seconds(m.group(1), m.group(2), m.group(3), m.group(4))
        end = parse_time_to_seconds(m.group(5), m.group(6), m.group(7), m.group(8))
        text_lines: List[str] = []
        while i < n and lines[i].strip():
            text_lines.append(lines[i])
            i += 1
        # consume blank separator
        while i < n and not lines[i].strip():
            i += 1
        yield start, end, text_lines


def season_episode_from_filename(filename: str) -> Tuple[Optional[int], Optional[int], str]:
    base = os.path.splitext(os.path.basename(filename))[0]
    m = re.match(r"^S(\d{2})E(\d{2})$", base, flags=re.I)
    season = int(m.group(1)) if m else None
    episode = int(m.group(2)) if m else None
    episode_id = f"S{season:02d}E{episode:02d}" if season and episode else base
    return season, episode, episode_id


def process_episode(vtt_path: str, strip_notes: bool) -> List[Dict]:
    season, episode, episode_id = season_episode_from_filename(vtt_path)
    utterances: List[Dict] = []
    for start, end, raw_lines in parse_vtt_cues(vtt_path):
        # join lines, normalize
        joined = normalize_text(" ".join(raw_lines))
        # remove inline tags fully
        joined = re.sub(r"<[^>]+>", "", joined)
        is_note = is_note_only(joined)
        speaker_raw, speaker_norm, remainder = extract_speaker(joined)
        text = remainder if speaker_norm else joined
        if strip_notes and is_note:
            # skip pure notes
            continue
        utterances.append({
            "season": season,
            "episode": episode,
            "episode_id": episode_id,
            "start": round(start, 3),
            "end": round(end, 3),
            "speaker_raw": speaker_raw or "",
            "speaker": speaker_norm or "",
            "speaker_role": "",
            "text": text,
            "is_caption_note": bool(is_note),
        })
    return utterances


def list_vtt_files(processed_root: str, seasons: List[str] | None) -> List[str]:
    season_dirs: List[str]
    if seasons:
        season_dirs = [os.path.join(processed_root, s.lower()) for s in seasons]
    else:
        season_dirs = [
            os.path.join(processed_root, name)
            for name in sorted(os.listdir(processed_root))
            if re.match(r"^s\d{2}$", name)
        ]
    vtts: List[str] = []
    for sdir in season_dirs:
        vdir = os.path.join(sdir, "vtt")
        if not os.path.isdir(vdir):
            continue
        for name in sorted(os.listdir(vdir)):
            if name.lower().endswith(".vtt"):
                vtts.append(os.path.join(vdir, name))
    return vtts


def write_jsonl(out_path: str, rows: List[Dict]) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed-root", default="data/processed")
    ap.add_argument("--season", action="append", help="limit to specific season(s) like s01; can repeat")
    ap.add_argument("--strip-notes", action="store_true", help="drop note-only cues like (cheering)")
    ap.add_argument("--speaker-map", default="data/metadata/speakers.csv", help="CSV mapping of speakers to canonical + role")
    args = ap.parse_args()

    vtts = list_vtt_files(args.processed_root, args.season)
    if not vtts:
        print("No VTT files found.", file=sys.stderr)
        sys.exit(1)

    # Optional speaker normalization
    normalizer = None
    if args.speaker_map and os.path.isfile(args.speaker_map):
        try:
            from normalize_speaker import SpeakerNormalizer
            normalizer = SpeakerNormalizer(args.speaker_map)
        except Exception:
            normalizer = None
    for vtt in vtts:
        season, episode, episode_id = season_episode_from_filename(vtt)
        if season is None or episode is None:
            print(f"Skipping unrecognized filename: {vtt}", file=sys.stderr)
            continue
        rows = process_episode(vtt, args.strip_notes)
        # Apply normalization if available
        if normalizer is not None:
            for r in rows:
                if r.get("speaker"):
                    canon, role = normalizer.normalize(r.get("speaker") or "")
                    r["speaker"] = canon
                    if role and not r.get("speaker_role"):
                        r["speaker_role"] = role
        out_dir = os.path.join(args.processed_root, f"s{season:02d}", "structured")
        out_path = os.path.join(out_dir, f"{episode_id}.jsonl")
        write_jsonl(out_path, rows)
        print(f"[s{season:02d}] structured {os.path.basename(vtt)} -> {out_path} ({len(rows)} utterances)")


if __name__ == "__main__":
    main()


