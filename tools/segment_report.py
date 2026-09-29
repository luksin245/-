"""원본을 쉬는 구간으로 나눈 조각마다 따로 받아 적어서 출력한다 (NG가 어디 있었는지 확인용).

사용법: python tools/segment_report.py <원본.mp4>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reels_auto import cutter  # noqa: E402
from reels_auto.media import load_audio  # noqa: E402
from reels_auto.transcribe import transcribe_text  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
audio = load_audio(sys.argv[1])
for s, e in cutter.detect_speech(audio, 16000):
    text = transcribe_text(audio[int(s * 16000): int(e * 16000)])
    print(f"{s:6.2f}~{e:6.2f}  {text}")
