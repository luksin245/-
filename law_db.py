"""download_laws.py로 내려받은 laws/*.json 법령 데이터를 읽는다."""

import json
import re
from pathlib import Path


def _key(name):
    return re.sub(r"[\s·ㆍ・]", "", name or "")


class LawDB:
    def __init__(self, folder="laws"):
        self.laws = {}
        for path in sorted(Path(folder).glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if "법령명" in data and "조문" in data:
                self.laws[_key(data["법령명"])] = data

    def summary(self):
        return [(d["법령명"], d.get("시행일자", ""), len(d["조문"])) for d in self.laws.values()]

    def article(self, law, label):
        """법령명과 조문 번호("제95조", "제18조의2")로 조문을 찾는다. 없으면 None."""
        data = self.laws.get(_key(law))
        if not data:
            return None
        for a in data["조문"]:
            if a["조문"] == label:
                return {**a, "법령명": data["법령명"], "법령시행일자": data.get("시행일자", "")}
        return None
