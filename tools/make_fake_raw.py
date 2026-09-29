"""편집된 레퍼런스 영상으로 '편집 전 원본' 같은 테스트 영상을 만든다.

- 말 덩어리 사이마다 0.8초 쉬는 구간을 넣고
- 몇 군데는 NG를 흉내 낸다: 앞부분만 말하다 멈춤 → 쉼 → 처음부터 다시 말함

사용법: python tools/make_fake_raw.py <레퍼런스.mp4> <출력.mp4> [NG 개수]
결과 영상을 프로그램에 넣으면 쉬는 구간과 NG가 잘려서 원래 길이 근처로 돌아와야 한다.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reels_auto.media import load_audio  # noqa: E402
from reels_auto.paths import ffmpeg_path  # noqa: E402
from reels_auto.transcribe import transcribe  # noqa: E402

PAUSE = 0.8


def chunks_from_words(words, max_words: int = 6) -> list[tuple[float, float]]:
    """단어들을 짧은 말 덩어리(시작, 끝)로 묶는다."""
    out, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or w.text.strip().endswith((".", "?", "!", ",")):
            out.append((cur[0].start, cur[-1].end))
            cur = []
    if cur:
        out.append((cur[0].start, cur[-1].end))
    return out


def main(src: str, dst: str, ng_count: int = 3) -> None:
    audio = load_audio(src)
    print(f"편집본 길이: {len(audio) / 16000:.1f}초")
    words = transcribe(audio)
    chunks = chunks_from_words(words)
    # NG를 넣을 덩어리: 충분히 긴 것 중 고르게
    long_ones = [i for i, (a, b) in enumerate(chunks) if b - a > 1.5]
    step = max(1, len(long_ones) // max(1, ng_count))
    ng_at = set(long_ones[::step][:ng_count])

    pieces: list[tuple[float, float, bool]] = []  # (시작, 끝, 소리 있음)
    for i, (a, b) in enumerate(chunks):
        a, b = max(0.0, a - 0.05), b + 0.05
        if i in ng_at:
            mid = a + (b - a) * 0.55
            pieces += [(a, mid, True), (mid, mid + PAUSE, False)]  # 말하다 멈춤
        pieces += [(a, b, True), (b, b + PAUSE, False)]

    parts, labels = [], []
    n = len(pieces)
    parts.append(f"[0:v]split={n}" + "".join(f"[v{k}]" for k in range(n)))
    parts.append(f"[0:a]asplit={n}" + "".join(f"[a{k}]" for k in range(n)))
    for k, (a, b, sound) in enumerate(pieces):
        d = b - a
        parts.append(f"[v{k}]trim=start={a:.3f}:duration={d:.3f},setpts=PTS-STARTPTS[pv{k}]")
        vol = "" if sound else ",volume=0"
        parts.append(f"[a{k}]atrim=start={a:.3f}:duration={d:.3f},asetpts=PTS-STARTPTS{vol}[pa{k}]")
        labels.append(f"[pv{k}][pa{k}]")
    parts.append("".join(labels) + f"concat=n={n}:v=1:a=1[v][a]")
    with tempfile.TemporaryDirectory() as tmp:
        graph = Path(tmp) / "g.txt"
        graph.write_text(";\n".join(parts), encoding="utf-8")
        subprocess.run([ffmpeg_path(), "-v", "error", "-y", "-i", src, "-/filter_complex", str(graph),
                        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                        "-c:a", "aac", dst], check=True)
    total = sum(b - a for a, b, _ in pieces)
    print(f"원본 흉내 영상: {dst} · 덩어리 {len(chunks)}개 · NG {len(ng_at)}곳 · 길이 {total:.1f}초")
    for i in sorted(ng_at):
        a, b = chunks[i]
        text = " ".join(w.text for w in words if a <= w.start < b)
        print(f"  NG 넣음: {text}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 3)
