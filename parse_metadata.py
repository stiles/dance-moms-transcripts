#!/usr/bin/env python3
"""Parse Wikipedia episodes tables into structured data.

Reads an HTML file saved from Wikipedia that contains one or more
episodes tables (typically classed as "wikiepisodetable" / "wikitable"),
extracts rows, strips footnotes/references, and writes clean data.

Default output is CSV to the given --out path. You can also request JSON.

Example:
  python parse_wikipedia_episodes.py \
    data/metadata/wikipedia_episodes_tables.html \
    --out data/metadata/episodes.csv \
    --format csv
"""

import argparse
import copy
import csv
import json
import os
import re
import sys
from typing import Dict, List, Optional

try:
    from bs4 import BeautifulSoup
except Exception as ex:  # pragma: no cover
    print("BeautifulSoup (bs4) is required: pip install beautifulsoup4", file=sys.stderr)
    raise


REFERENCE_PAT = re.compile(r"\[[^\]]+\]")
WHITESPACE_PAT = re.compile(r"\s+")


def clean_cell_text(html_cell) -> str:
    """Return readable text for a cell, removing footnotes and junk.

    - Removes <sup> references and any element with class containing 'reference'
    - Removes bracketed references like [1], [a], [note 1]
    - Collapses whitespace
    """
    if html_cell is None:
        return ""

    # Work on a shallow copy of the Tag to avoid mutating the original tree
    try:
        cell = copy.copy(html_cell)
    except Exception:
        cell = html_cell

    # Remove footnotes, reference anchors/spans, and noteref links
    for node in cell.find_all(["sup", "span", "a"], recursive=True):
        try:
            classes = node.get("class", []) if hasattr(node, "get") else []
            href = node.get("href", "") if hasattr(node, "get") else ""
            role = node.get("role", "") if hasattr(node, "get") else ""
            if (
                node.name == "sup"
                or "reference" in " ".join(classes)
                or (node.name == "a" and ("cite_ref" in href or role == "doc-noteref"))
            ):
                node.decompose()
        except Exception:
            # If any odd node lacks expected attrs, skip it
            continue

    # Get raw text then strip bracketed references lingering in text
    text = cell.get_text(" ", strip=True)
    text = REFERENCE_PAT.sub("", text)
    text = WHITESPACE_PAT.sub(" ", text).strip()
    return text


def normalize_header(text: str) -> str:
    t = text.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = WHITESPACE_PAT.sub(" ", t).strip()
    return t


def map_header_to_field(header_text: str) -> Optional[str]:
    h = normalize_header(header_text)
    if not h:
        return None
    if "overall" in h:
        return "overall_episode"
    if ("no" in h or "number" in h) and "season" in h:
        return "episode_in_season"
    if "title" in h:
        return "title"
    if "direct" in h:
        return "directed_by"
    if "writ" in h:
        return "written_by"
    if "air" in h and "date" in h:
        return "original_air_date"
    if "view" in h and "million" in h:
        return "us_viewers_millions"
    if "prod" in h and "code" in h:
        return "production_code"
    if "notes" in h:
        return "notes"
    return None


def find_season_context(table) -> Dict[str, Optional[str]]:
    """Return season number and title context based on nearest heading above the table."""
    season_number: Optional[int] = None
    season_title: Optional[str] = None

    prev = table
    while prev is not None:
        prev = prev.find_previous(["h2", "h3"])  # closest section heading
        if prev is None:
            break
        title_text = prev.get_text(" ", strip=True)
        if not title_text:
            continue
        season_title = title_text
        m = re.search(r"season\s*(\d+)", title_text, flags=re.I)
        if m:
            try:
                season_number = int(m.group(1))
            except Exception:
                pass
        # Stop at the first heading found
        break

    return {"season": season_number, "season_title": season_title}


def parse_tables(soup: BeautifulSoup) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []

    tables = soup.find_all("table", class_=lambda c: c and ("wikiepisodetable" in c or "wikitable" in c))
    fallback_tables = soup.find_all("table") if not tables else []
    candidate_tables = tables or fallback_tables

    inferred_season_counter = 0

    for table in candidate_tables:
        # Identify header cells
        header_cells = table.find("tr")
        if header_cells is None:
            continue
        header_cells = header_cells.find_all(["th", "td"], recursive=False)
        if not header_cells:
            continue

        header_map: List[Optional[str]] = [map_header_to_field(clean_cell_text(h)) for h in header_cells]
        if not any(header_map):
            # Not an episodes table
            continue

        season_ctx = find_season_context(table)
        season_num = season_ctx.get("season")
        season_title = season_ctx.get("season_title")
        if season_num is None:
            inferred_season_counter += 1
            season_num = inferred_season_counter

        body_rows = table.find_all("tr")[1:]
        for tr in body_rows:
            # Skip subheaders or totals
            if tr.find("th") and not tr.find("td"):
                continue
            if "sortbottom" in (tr.get("class") or []):
                continue

            cells = tr.find_all(["td", "th"])  # include row headers
            if not cells:
                continue

            values: Dict[str, str] = {
                "season": str(season_num),
                "season_title": season_title or "",
            }

            for i, cell in enumerate(cells):
                field = header_map[i] if i < len(header_map) else None
                if not field:
                    continue
                text = clean_cell_text(cell)
                values[field] = text

            # Keep only rows that at least have a title
            if not values.get("title"):
                continue

            results.append(values)

    return results


def write_csv(rows: List[Dict[str, str]], out_path: str) -> None:
    # Collect all keys across rows for a stable header
    keys: List[str] = [
        "season",
        "season_title",
        "episode_in_season",
        "overall_episode",
        "title",
        "directed_by",
        "written_by",
        "original_air_date",
        "us_viewers_millions",
        "production_code",
        "notes",
    ]
    seen = set(keys)
    for r in rows:
        for k in r.keys():
            if k not in seen:
                keys.append(k)
                seen.add(k)

    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_json(rows: List[Dict[str, str]], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html", default="data/metadata/episodes.html", help="path to saved Wikipedia HTML")
    ap.add_argument("--out", default="data/metadata/episodes.json", help="output file path")
    ap.add_argument("--format", choices=["csv", "json"], default="json", help="output format")
    args = ap.parse_args()

    with open(args.html, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    rows = parse_tables(soup)
    if not rows:
        print("No episode rows found.", file=sys.stderr)
        sys.exit(1)

    if args.format == "csv":
        write_csv(rows, args.out)
    else:
        write_json(rows, args.out)

    print(f"Wrote {args.out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()


