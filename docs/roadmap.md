## Project plan

This doc outlines concrete improvements to acquisition, cleaning, structure and analysis.

## Current state

- Acquisition script `dump_transcripts.py` merges WebVTT segments per episode and writes `SxxExx.vtt`, optional `SxxExx.txt`, plus `sxx_index.csv`
- Season data exists for s01 and s02 under `data/processed/`
- Episode metadata from Wikipedia is parsed into `data/metadata/episodes.json` via `parse_metadata.py`

## Objectives

1. Acquire all seasons as VTT and text
2. Clean transcripts to remove caption artifacts and sentence breaks
3. Structure transcripts into utterances with speaker labels
4. Join episode metadata to per‑episode indices
5. Build analysis‑ready datasets and simple tooling
6. Add optional summarization over transcripts

## Milestones and tasks

### 1) Acquisition (all seasons)
- Status: in progress

- Add support to pass multiple HAR files in one run; name outputs by detected season (done: `dump_transcripts.py` now accepts a directory or auto-scans `data/raw/`)
- Add a small helper to verify episode counts per season against metadata
- Write a combined repository‑level `episodes_index.csv` that concatenates all `sxx_index.csv` (done: written as `episodes_index_enriched.csv`)
- Save fetch logs alongside outputs to help retry failed segments
- Optional: support re‑hydrating `.txt` from `.vtt` later so `--text` isn’t required during capture

Deliverables:
- `data/processed/s01..s08/{vtt,txt}/SxxExx.*`
- `data/processed/sxx/sxx_index.csv` for each season
- `data/processed/episodes_index.csv` (all seasons) (done as enriched: `data/processed/episodes_index_enriched.csv`)

### 2) Cleaning (sentence and token normalization)
- Status: done

- Normalize quotes, dashes, ellipses, stray HTML tags from captions
- Remove hearing‑impaired cues in brackets where desired (e.g., “(cheering)”) but keep a flag if retained
- Merge artificial line breaks caused by segmenting; reflow to sentences
- De‑duplicate repeated lines across segment joins

Implementation:
- New script `clean_transcripts.py` that reads `SxxExx.vtt`, applies rules, and writes: (done)
  - `data/processed/sxx/clean/SxxExx.txt` (paragraph form)
  - `data/processed/sxx/clean/SxxExx.sentences.txt` (one sentence per line)

### 3) Structuring (utterance‑level data with speakers)
- Status: done

- Parse speakers from ALL‑CAPS prefixes like `HOLLY:` `ABBY:` `KELLY:` and variants (`HOLLY (whispers):` → `HOLLY`)
- Keep non‑dialogue caption notes as `is_caption_note=true`
- Preserve timing by parsing from `.vtt` (start/end) for each cue before cleaning
- Emit one record per cue or merged utterance

Data model (JSONL per episode):
- `season` (int), `episode` (int), `episode_id` (e.g., `S02E01`)
- `start` (seconds), `end` (seconds)
- `speaker_raw` (string from caption), `speaker` (normalized), `speaker_role` (mom, dancer, instructor, other)
- `text` (cleaned), `is_caption_note` (bool)
- Optional derived: `sentence_index`, `token_count`

Implementation:
- New script `structure_transcripts.py` that reads `.vtt` directly and writes: (done)
  - `data/processed/sxx/structured/SxxExx.jsonl`

### 4) Metadata join (titles, air dates)
- Status: done (basic); specials matching pending

- Join `data/metadata/episodes.json` to each season’s `sxx_index.csv` on `(season, episode)`
- Handle specials where `episode_in_season` is `-` by best‑effort matching (title or overall number) and mark `is_special=true` (pending)
- Emit enriched indices with `title`, `original_air_date`, `overall_episode`, `notes`

Implementation:
- New script `merge_metadata.py` that writes: (done)
  - `data/processed/sxx/sxx_index_enriched.csv`
  - `data/processed/episodes_index_enriched.csv`

### 5) Speaker map and normalization
- Status: in progress

- Create `data/metadata/speakers.csv` with columns: `speaker`, `canonical`, `role`, `aliases`
- Add normalization rules: slash‑joined names (`KELLY/CHRISTI`), parentheticals, unknowns
- Provide a report for unmapped speakers to update the map iteratively

Implementation:
- `normalize_speaker.py` library used by structuring and analysis scripts
- `report_unknown_speakers.py` to list frequencies of unmapped speakers

### 6) Summaries (optional)
- Status: done (keyword/bigram + frequency‑based blurb)

- Run a summarizer over each episode or scene to produce short, medium and long summaries
- Store outputs with provenance and prompts to allow reproducibility

Implementation:
- `summarize.py` with CLI:
  - Inputs: `SxxExx.jsonl` (utterances), max tokens per chunk, model name
  - Outputs: `data/processed/sxx/summaries/SxxExx.summary.json`
- Caching layer (hash of input + params) to avoid re‑runs

### 7) Analysis datasets and simple tooling
- Status: pending

- Build aggregated CSVs for quick analysis:
  - `utterances.csv` (all seasons) with normalized speakers
  - `speaker_turns.csv` per episode
  - `entity_counts.csv` (basic dictionary match for key names)
- Provide notebook or CLI examples:
  - Frequency of mentions by episode/season
  - Complaint vs praise classifier baseline over utterances
  - Theme trendlines over time

### 8) Packaging and repo hygiene
- Status: pending

- Add `requirements.txt` and pin minimal versions (`requests`, `bs4`, `pandas`, `regex`)
- Add `Makefile` targets (`make s01`, `make clean`, `make structure`, `make enrich`)
- Add light tests for metadata parsing and VTT→utterance conversion
- Document environment variables for summarization keys (kept optional)

## Edge cases to handle

- Specials, reunions and multi‑title cells in metadata
- Overlapping cues and mid‑cue speaker changes in VTT
- Hearing‑impaired cues that interleave with dialogue
- Duplicate or missing segments in a HAR capture

## Quick execution outline

1. Capture HAR per season under `data/raw/`
2. Run `dump_transcripts.py --out data/processed --text` (auto‑scans `data/raw/`), or specify a single season: `dump_transcripts.py data/raw/sXX.har --out data/processed --text`
3. Run `clean_transcripts.py --season sXX` (or all seasons)
4. Run `structure_transcripts.py --season sXX --speaker-map data/metadata/speakers.csv`
5. Run `merge_metadata.py`
6. Run `aggregate_speaker_counts.py` (optional but useful)
7. Run `report_unknown_speakers.py` to expand `speakers.csv` (optional)
8. Run `summarize.py --season sXX` (optional)

## Definitions of done

- All seasons present in `data/processed/` with VTT and text
- Clean, sentence‑level text generated
- Structured utterance JSONL with speaker labels and timing
- Enriched indices joined with metadata for all seasons
- Basic aggregate CSVs and one or two example analyses
- Optional summaries produced and cached

## More analysis ideas

- Speaker network graphs by episode and season (who talks to/about whom)
- Sentiment per speaker over time and per conflict arc
- Topic modeling per season; track topic prevalence across episodes
- Keyword‑in‑context concordances for recurring themes (e.g., favoritism)
- Quote mining: most characteristic lines per speaker (e.g., tf‑idf by speaker)
- Turn‑taking metrics: average utterance length, interruptions, dominance
- Episode beat detection: segment episodes into scenes by silence gaps or topic shift
- Cross‑season alignment: compare similar episodes (premieres, nationals) via text similarity
- Named entity normalization for people, studios, competitions and locations
- Toxicity and profanity scoring trends (with careful caveats)
- Retrieval for “find episodes where X confronts Y about Z” using semantic search


