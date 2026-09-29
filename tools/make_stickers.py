"""Fluent 3D 이모지(MIT, Microsoft)에서 스티커를 골라 assets/stickers/ 에 PNG로 저장한다.

사용법: npm pack @lobehub/fluent-emoji-3d 로 받은 패키지를 풀고
        python tools/make_stickers.py <풀린 package 폴더>
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reels_auto.paths import app_dir, ffmpeg_path  # noqa: E402

# 이름: (이모지 코드, 이 말이 자막에 나오면 스티커를 띄움)
STICKERS: dict[str, tuple[str, list[str]]] = {
    "시계": ("23f0", ["근무시간", "근로시간", "근로 시간", "근무 시간", "출근", "퇴근", "야근", "연장근로", "시급", "몇 시간", "시간"]),
    "달력": ("1f4c5", ["연차", "휴가", "입사", "366일", "365일", "364일", "1년", "일수", "기간", "날짜"]),
    "주간달력": ("1f4c6", ["주휴", "매주", "일주일", "주 15시간", "주 40시간"]),
    "돈주머니": ("1f4b0", ["퇴직금", "수당", "급여", "월급", "임금", "연봉", "보상", "정산", "실업급여", "돈"]),
    "지폐": ("1f4b5", ["만원", "금액", "최저임금", "받을 돈", "챙길 돈"]),
    "은행": ("1f3e6", ["지급일", "입금", "통장", "계좌"]),
    "계약서": ("1f4dd", ["근로계약서", "계약서", "서명", "작성"]),
    "서류": ("1f4c4", ["서류", "증명서", "문서", "규정", "취업규칙"]),
    "체크리스트": ("1f4cb", ["조건", "기준", "요건", "체크"]),
    "확인": ("2705", ["가능해", "받을 수 있어", "할 수 있어", "보호받을 수", "보호 받을 수", "맞아", "당연히"]),
    "금지": ("274c", ["안 돼", "안돼", "불가능", "안 나와", "못 받", "안 줘", "사라지지"]),
    "경고": ("26a0-fe0f", ["주의", "조심", "위반", "불법", "위법", "불이익", "불리하게"]),
    "확성기": ("1f4e2", ["신고", "진정", "고발", "노동청"]),
    "경찰": ("1f46e", ["경찰", "형사", "고소", "처벌"]),
    "저울": ("2696-fe0f", ["근로기준법", "노동법", "법적", "법으로", "판례", "법"]),
    "회사": ("1f3e2", ["사업장", "회사", "직장", "사무실", "본사", "지점"]),
    "사람들": ("1f465", ["상시근로자", "5명", "직원들", "동료", "근로자 수", "사람들"]),
    "사장님": ("1f468-200d-1f4bc", ["사장", "대표", "상급자", "상사", "관리자", "회사 측"]),
    "직원": ("1f64b", ["알바", "아르바이트", "직장인", "근로자", "직원"]),
    "화남": ("1f621", ["괴롭힘", "폭언", "모욕", "갑질", "욕설", "폭행", "협박"]),
    "속상": ("1f622", ["억울", "스트레스", "힘들", "상처"]),
    "휴대폰": ("1f4f1", ["카톡", "카카오톡", "문자", "연락", "메시지", "휴대폰"]),
    "녹음": ("1f399-fe0f", ["녹음", "녹취"]),
    "돋보기": ("1f50d", ["증거", "조사", "확인해야", "살펴"]),
    "문": ("1f6aa", ["퇴사", "그만두", "사직", "나가"]),
    "서류가방": ("1f4bc", ["이직", "취업", "업무", "일을"]),
    "병원": ("1f3e5", ["병원", "산재", "다쳐", "부상", "아프"]),
    "커피": ("2615", ["휴게", "휴식", "쉬는 시간", "쉬는"]),
    "전구": ("1f4a1", ["꿀팁", "방법", "팁", "정리해", "알려줄게", "결론"]),
    "물음표": ("2753", ["궁금", "질문", "어떻게 될까", "있을까"]),
    "차트": ("1f4ca", ["80%", "비율", "계산", "퍼센트"]),
    "해고": ("1f6ab", ["해고", "잘리", "잘려", "근무 시간을 줄"]),
    "선물": ("1f381", ["보너스", "상여", "성과급"]),
}

MIT_NOTICE = """Fluent Emoji — https://github.com/microsoft/fluentui-emoji
(3D 이미지는 @lobehub/fluent-emoji-3d 패키지에서 가져와 PNG로 변환)

MIT License

Copyright (c) Microsoft Corporation.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def main(pkg: str) -> None:
    src = Path(pkg) / "assets"
    out = app_dir() / "assets" / "stickers"
    out.mkdir(parents=True, exist_ok=True)
    table = {}
    for name, (code, keywords) in STICKERS.items():
        webp = src / f"{code}.webp"
        if not webp.exists():
            print("없음:", name, code)
            continue
        subprocess.run([ffmpeg_path(), "-v", "error", "-y", "-i", str(webp), "-frames:v", "1",
                        "-pix_fmt", "rgba", str(out / f"{name}.png")], check=True)
        table[name] = keywords
    (out / "stickers.json").write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "LICENSE-FluentEmoji.txt").write_text(MIT_NOTICE, encoding="utf-8")
    print(f"{len(table)}개 저장:", out)


if __name__ == "__main__":
    main(sys.argv[1])
