## Dance Moms transcripts

## About this project
This project collects, cleans and analyzes transcripts of *Dance Moms* episodes streamed on Disney+. It has two parts:

1. Transcript acquisition – capture closed caption VTT files from playback sessions, merge them and label by season and episode
2. Transcript analysis – turn captions into structured text that you can search, count and compare

This project isn’t about redistributing video content — only studying the language used in the show. 

## Why this matters
Part of the goal is to show my daughter — who loves the show — that programming can be a tool for exploring the things she cares about. Subtitles become data, and data means questions can be tested: who gets mentioned most, when conflicts flare, how themes shift across a season.

**Daughter:** "Holly *always* says Abby is unfair?"
**Me:** "Let's check the numbers!"

## How acquisition works
Disney+ generates a temporary subtitle playlist (`.m3u8`) with short‑lived, signed URLs for `.vtt` segments per playback.

You can capture a season as a HAR, then run a script that finds subtitle playlists, downloads the segments, merges them and writes one `.vtt` per episode. With `--text`, it also writes plain text.

### Capture steps
1. Open Chrome DevTools → Network tab → enable Preserve log
2. Play an episode with captions on (English SDH). Let it run ~10s
3. Step through the season in order so the log contains all episodes you want
4. Save the log as a HAR, for example `data/raw/s01.har`

### Usage
```bash
python dump_transcripts.py data/raw/s01.har --out data/processed --text
```

Flags:
- `--out DIR`: output directory (default `data/processed`)
- `--text`: also write plain text transcripts
- `--lang CODE`: language hint to prefer relevant playlists (default `en`)
- `--max-workers N`: parallel segment downloads (default 16)

What the script does:
- Probe `.m3u8` requests in the HAR
- Collect `.vtt` subtitle segments
- Merge them into `S01E01.vtt`, `S01E02.vtt`, etc
- Optionally write `S01E01.txt`, `S01E02.txt`, etc
- Create an `index.csv` for traceability

### Outputs
Each episode yields:
- `SxxExx.vtt`: merged WebVTT file
- `SxxExx.txt`: plain text transcript (no timecodes or style) when `--text` is set

Files are organized per season with separate subdirectories for types:

```
data/processed/
  s01/
    vtt/
      S01E01.vtt
      S01E02.vtt
      ...
    txt/
      S01E01.txt
      S01E02.txt
      ...
    s01_index.csv
```

`s01_index.csv` lives in the season directory and includes episode number, playlist URL and IDs.

## Analysis directions
With full‑season transcripts, you can explore:
- Entity frequency – count mentions of each dancer, mom or instructor by name
- Complaint tracking – identify utterances where moms criticize treatment of their daughters and quantify frequency
- Theme trends – track motifs like competition prep, favoritism, conflicts, reconciliations
- Episode arcs – compare dialogue tone and focus between the beginning and end of an episode
- Season arcs – compare word usage across seasons to see how storylines evolve

## Episode metadata parsing
There's also a script to parse episode tables saved from Wikipedia into structured data (json or csv).

### Parse Wikipedia episodes HTML
```bash
python parse_metadata.py data/metadata/episodes.html \
  --out data/metadata/episodes.json \
  --format json
```

Output columns (varies by page):
- `season`, `season_title`
- `episode_in_season`, `overall_episode`
- `title`
- `directed_by`, `written_by`
- `original_air_date`, `us_viewers_millions`
- `production_code`, `notes`

Footnotes and bracketed references are removed from cell text.

## Notes
- Uses only caption text available to any subscriber
- Captions are segmented for streaming; the script merges them into continuous transcripts
- Playlist tokens expire quickly, so download transcripts soon after capturing the HAR
- Use is for research and personal analysis, not redistribution