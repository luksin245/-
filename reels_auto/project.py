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
class Sticker:
    start: float
    end: float
    name: str  # assets/stickers/<name>.png


@dataclass
class QuizItem:
    start: float  # 문제 카드가 나타나는 시점
    reveal: float  # 정답 표시(O/X)가 나타나는 시점
    end: float  # 카드가 사라지는 시점
    answer: str  # "O" 또는 "X"
    image: str  # 스티커 이름 또는 사진 파일 경로


@dataclass
class TierItem:
    tier: str  # "S" / "A" / "B" / "C"
    time: float  # 항목이 나타나는 시점
    text: str


@dataclass
class Project:
    source: str
    segments: list[tuple[float, float]]  # 원본 기준 남길 구간
    duration: float  # 최종 영상 길이
    words: list[Word] = field(default_factory=list)
    captions: list[Caption] = field(default_factory=list)
    title: str = ""
    title_font: str = "프리텐다드"  # 제목 글꼴 (ass.TITLE_FONTS 의 이름)
    list_style: str = "none"  # "rank"(TOP N, 아래부터) / "ordinal"(N가지, 위부터) / "quiz"(O/X 퀴즈) / "tier"(티어리스트) / "none"
    list_count: int = 0  # 목록 줄 수 (2~7)
    items: list[RankItem] = field(default_factory=list)  # rank = 목록의 몇 번째 줄인지 (1이 맨 위)
    bgm: str | None = None
    bgm_volume: float = 0.18
    face_box: list[int] | None = None  # 출력 화면 기준 얼굴 상자 [x, y, w, h]
    retouch: str = "약하게"  # 피부 보정: 끄기/약하게/보통/강하게
    slim: str = "약하게"  # 얼굴형 갸름하게: 끄기/약하게/보통/강하게
    stickers: list[Sticker] = field(default_factory=list)  # 말에 맞춰 잠깐 튀어나오는 그림
    quiz: list[QuizItem] = field(default_factory=list)  # 퀴즈형일 때 문제별 카드와 정답
    tiers: list[TierItem] = field(default_factory=list)  # 티어리스트형일 때 등급별 항목
    hook_type: str = ""  # 도입부 후킹 유형 (docs/hook-patterns.md)
    ng_removed: list[str] = field(default_factory=list)  # 자동으로 뺀 NG 조각 설명 (원본 시점 · 이유 · 말)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Project":
        d = json.loads(text)
        d["segments"] = [tuple(s) for s in d["segments"]]
        d["words"] = [Word(**w) for w in d["words"]]
        d["captions"] = [Caption(**c) for c in d["captions"]]
        d["items"] = [RankItem(**i) for i in d["items"]]
        d["stickers"] = [Sticker(**x) for x in d.get("stickers", [])]
        d["quiz"] = [QuizItem(**x) for x in d.get("quiz", [])]
        d["tiers"] = [TierItem(**x) for x in d.get("tiers", [])]
        if "top_mode" in d:  # 예전 형식
            d["list_style"], d["list_count"] = ("rank", 5) if d.pop("top_mode") else ("none", 0)
        return cls(**d)
