#!/usr/bin/env python3
# har_subs_dump_seq.py
# Assumes: one season per HAR, episodes captured in order (1..N).
# Names outputs sequentially: S{season:02d}E{idx:02d}.vtt / .txt

import argparse, json, os, re, sys, csv, urllib.parse
from collections import defaultdict
from datetime import datetime, timezone
import concurrent.futures as cf
import requests

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (subs-dl)"})

UUID_RE = re.compile(r"/ps01/[^/]+/([0-9a-f-]{36})/r/")
PSID_RE = re.compile(r"~psid=([0-9a-f-]{36})")
TS_RE = re.compile(r"\d\d:\d\d:\d\d\.\d{3}\s+-->\s+\d\d:\d\d:\d\d\.\d{3}")

def parse_season_from_filename(path, default=1):
    m = re.search(r"s(\d{1,2})", os.path.basename(path), re.I)
    return int(m.group(1)) if m else default

def load_har(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def iter_m3u8_entries(har):
    for e in har.get("log", {}).get("entries", []):
        url = e.get("request", {}).get("url", "")
        if url.lower().endswith(".m3u8"):
            yield e

def started_dt(entry):
    # RFC3339-ish to datetime
    s = entry.get("startedDateTime")
    if not s:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)

def fetch_text(url, timeout=30):
    r = SESSION.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text

def m3u8_vtts(text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return [ln for ln in lines if ln.endswith(".vtt")]

def resolve(base_m3u8, rel):
    base = base_m3u8.rsplit("/", 1)[0] + "/"
    return urllib.parse.urljoin(base, rel)

def merge_vtts(vtts_texts):
    out, header = [], False
    for v in vtts_texts:
        if not v: continue
        lines = v.splitlines()
        if not lines: continue
        if not header:
            out.extend(lines)
            header = True
        else:
            i = 0
            while i < len(lines) and not TS_RE.search(lines[i]):
                i += 1
            out.append("")
            out.extend(lines[i:])
    return "\n".join(out) + "\n"

def vtt_to_text(vtt):
    out, skip = [], False
    for line in vtt.splitlines():
        if line.startswith(("STYLE", "NOTE")):
            skip = True; continue
        if skip and not line.strip():
            skip = False; continue
        if skip: continue
        if line.startswith("WEBVTT") or "line:" in line or TS_RE.search(line):
            continue
        if line.strip():
            out.append(re.sub(r"</?(i|b|u)>", "", line))
    return "\n".join(out).strip() + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("har")
    ap.add_argument("--out", default="data/processed")
    ap.add_argument("--lang", default="en", help="language hint; used only to prefer relevant playlists if present")
    ap.add_argument("--text", action="store_true", help="also emit plain text")
    ap.add_argument("--max-workers", type=int, default=16)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    season = parse_season_from_filename(args.har, default=1)
    # Season-specific directories
    season_dir = os.path.join(args.out, f"s{season:02d}")
    vtt_dir = os.path.join(season_dir, "vtt")
    txt_dir = os.path.join(season_dir, "txt")
    os.makedirs(vtt_dir, exist_ok=True)
    if args.text:
        os.makedirs(txt_dir, exist_ok=True)
    har = load_har(args.har)

    # 1) collect candidate playlists with timing and IDs
    candidates = []
    for e in iter_m3u8_entries(har):
        url = e.get("request", {}).get("url", "")
        t0 = started_dt(e)
        try:
            txt = fetch_text(url)
        except Exception:
            continue
        vtts = m3u8_vtts(txt)
        if not vtts:
            continue
        uuid = None
        m = UUID_RE.search(url)
        if m: uuid = m.group(1)
        psid = None
        m = PSID_RE.search(url)
        if m: psid = m.group(1)
        is_sdh = "sdh" in url.lower()
        lang_hit = args.lang and (f"_{args.lang.lower()}_" in url.lower() or f"/{args.lang.lower()}_" in url.lower())
        candidates.append({
            "url": url, "t0": t0, "uuid": uuid or f"nouuid:{url.rsplit('/',3)[0]}",
            "psid": psid or "nopsid", "is_sdh": is_sdh, "lang_hit": bool(lang_hit)
        })

    if not candidates:
        print("No subtitle playlists found. Re-export HAR soon after enabling CC.", file=sys.stderr)
        sys.exit(1)

    # 2) dedupe per episode: group by uuid (or fallback key), pick best (prefer lang_hit, then SDH, then earliest)
    groups = defaultdict(list)
    for c in candidates:
        groups[c["uuid"]].append(c)

    chosen = []
    for key, items in groups.items():
        items.sort(key=lambda x: (not x["lang_hit"], not x["is_sdh"], x["t0"]))  # True>False, so invert booleans
        chosen.append(items[0])

    # 3) order episodes by capture time
    chosen.sort(key=lambda x: x["t0"])

    print(f"Found {len(chosen)} episode playlists (ordered by capture time).")

    # 4) download, merge, write sequential names
    index_rows = []
    for idx, c in enumerate(chosen, start=1):
        url = c["url"]
        try:
            m3u8_txt = fetch_text(url)
        except Exception as ex:
            print(f"[{idx:02d}] playlist fetch failed: {ex}", file=sys.stderr)
            continue
        rels = m3u8_vtts(m3u8_txt)
        abs_urls = [resolve(url, r) for r in rels]

        vtts = [None]*len(abs_urls)
        def grab(iu):
            i,u = iu
            try:
                vtts[i] = fetch_text(u)
            except Exception as ex:
                vtts[i] = ""
                print(f"  seg {i:05d} failed: {ex}", file=sys.stderr)

        with cf.ThreadPoolExecutor(max_workers=args.max_workers) as ex:
            ex.map(grab, enumerate(abs_urls))

        merged = merge_vtts(vtts)
        base = f"S{season:02d}E{idx:02d}"
        vtt_path = os.path.join(vtt_dir, f"{base}.vtt")
        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write(merged)
        print(f"[{base}] wrote {vtt_path} ({len(merged):,} chars)   ({'SDH' if c['is_sdh'] else 'STD'})")

        txt_path = ""
        if args.text:
            txt = vtt_to_text(merged)
            txt_path = os.path.join(txt_dir, f"{base}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(txt)
            print(f"          wrote {txt_path} ({len(txt):,} chars)")

        index_rows.append({
            "season": season,
            "episode": idx,
            "file_vtt": vtt_path,
            "file_txt": txt_path,
            "m3u8": url,
            "uuid": c["uuid"],
            "psid": c["psid"],
            "requested_at_utc": c["t0"].astimezone(timezone.utc).isoformat(),
            "is_sdh": c["is_sdh"],
        })

    # 5) index.csv
    idx_path = os.path.join(season_dir, f"s{season:02d}_index.csv")
    with open(idx_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(index_rows[0].keys()))
        w.writeheader()
        for r in index_rows:
            w.writerow(r)
    print(f"Wrote {idx_path}")

if __name__ == "__main__":
    main()