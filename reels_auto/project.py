"""분석 결과(편집 정보)를 담는 데이터 구조."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class Word:
    start: float  # 잘린 뒤(최종 영상) 기준 초
    end: float
    text: str


@dataclass
class Caption:
    start: float
    end: float
    text: str


@dataclass
class RankItem:
    rank: int
    time: float | None  # 목록에 글자가 나타나는 시점. None이면 표시 안 함
    text: str


@dataclass
class Project:
    source: str
    segments: list[tuple[float, float]]  # 원본 기준 남길 구간
    duration: float  # 최종 영상 길이
    words: list[Word] = field(default_factory=list)
    captions: list[Caption] = field(default_factory=list)
    title: str = ""
    top_mode: bool = False
    items: list[RankItem] = field(default_factory=list)  # 5위부터 1위 순서
    bgm: str | None = None
    bgm_volume: float = 0.18

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Project":
        d = json.loads(text)
        d["segments"] = [tuple(s) for s in d["segments"]]
        d["words"] = [Word(**w) for w in d["words"]]
        d["captions"] = [Caption(**c) for c in d["captions"]]
        d["items"] = [RankItem(**i) for i in d["items"]]
        return cls(**d)
