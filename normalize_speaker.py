#!/usr/bin/env python3
import csv
import os
import re
from typing import Dict, Optional


class SpeakerNormalizer:
    def __init__(self, mapping_path: str):
        self.alias_to_canonical: Dict[str, str] = {}
        self.canonical_role: Dict[str, str] = {}
        self._load(mapping_path)

    def _load(self, path: str) -> None:
        if not os.path.isfile(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                canonical = (r.get("canonical") or "").strip().upper()
                if not canonical:
                    continue
                role = (r.get("role") or "").strip()
                speaker = (r.get("speaker") or canonical).strip().upper()
                aliases = (r.get("aliases") or "").strip()
                self.alias_to_canonical[speaker] = canonical
                if role:
                    self.canonical_role[canonical] = role
                if aliases:
                    for a in re.split(r"[;,]\s*", aliases):
                        a = a.strip().upper()
                        if a:
                            self.alias_to_canonical[a] = canonical

    def normalize(self, raw: str) -> (str, str):
        key = (raw or "").strip().upper()
        if not key:
            return "", ""
        canonical = self.alias_to_canonical.get(key, key)
        role = self.canonical_role.get(canonical, "")
        return canonical, role


