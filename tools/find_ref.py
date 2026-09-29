"""reference/ 에서 이름에 주어진 말이 들어간 영상 경로를 출력한다 (맥에서 올린 한글 파일명도 찾음).

사용법: python tools/find_ref.py 퀴즈
"""
import sys
import unicodedata
from pathlib import Path

# Windows 기본 콘솔 인코딩으로는 한글 경로를 출력하지 못하므로 UTF-8로
sys.stdout.reconfigure(encoding="utf-8")
word = unicodedata.normalize("NFC", sys.argv[1])
for f in sorted(Path(__file__).resolve().parent.parent.glob("reference/*.mp4")):
    if word in unicodedata.normalize("NFC", f.name):
        print(f.relative_to(Path.cwd()) if f.is_relative_to(Path.cwd()) else f)
        break
else:
    sys.exit(f"'{word}' 가 들어간 영상이 없습니다")
