"""국가법령정보센터 Open API로 노동 관계 법령을 내려받아 조문 단위로 저장한다.

사용법:
    python download_laws.py --oc 내인증키
    python download_laws.py --oc 내인증키 --law 근로기준법 --law 최저임금법

결과(laws/ 폴더):
    <법령명>.xml   API 원본 응답
    <법령명>.json  조문 단위로 정리한 데이터
    articles.csv   전체 조문 목록 (엑셀에서 바로 열림)
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = "http://www.law.go.kr/DRF"

# 취업규칙 검토에 주로 쓰는 법령
DEFAULT_LAWS = [
    "근로기준법",
    "근로기준법 시행령",
    "근로기준법 시행규칙",
    "최저임금법",
    "근로자퇴직급여 보장법",
    "남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률",
    "기간제 및 단시간근로자 보호 등에 관한 법률",
    "근로자참여 및 협력증진에 관한 법률",
    "산업안전보건법",
    "고용상 연령차별금지 및 고령자고용촉진에 관한 법률",
]


def fetch(endpoint, params):
    url = f"{BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def normalize(name):
    # "일ㆍ가정", "일·가정" 같은 가운뎃점 차이와 공백을 무시하고 비교
    return re.sub(r"[\s·ㆍ・]", "", name or "")


def find_law(oc, name):
    """법령명으로 검색해 현행 법령의 (법령명, 법령일련번호, 시행일자)를 돌려준다."""
    root = ET.fromstring(fetch("lawSearch.do", {
        "OC": oc, "target": "law", "type": "XML", "query": name, "display": 100,
    }))
    if root.findtext("resultCode") not in (None, "00"):
        raise RuntimeError(root.findtext("resultMsg") or "검색 실패")

    candidates = []
    for law in root.iter("law"):
        title = (law.findtext("법령명한글") or "").strip()
        candidates.append((title, law.findtext("법령일련번호"), law.findtext("시행일자")))
        if normalize(title) == normalize(name):
            return candidates[-1]

    found = ", ".join(c[0] for c in candidates) or "없음"
    raise LookupError(f"'{name}'과 이름이 정확히 같은 법령이 없습니다. 검색 결과: {found}")


def text_of(el, tag):
    value = el.findtext(tag)
    return value.strip() if value else ""


def parse_articles(xml_bytes):
    """lawService.do XML 응답에서 조문 목록을 뽑는다."""
    root = ET.fromstring(xml_bytes)
    articles = []
    for unit in root.iter("조문단위"):
        # '전문'은 장·절 제목이므로 건너뛴다
        if text_of(unit, "조문여부") != "조문":
            continue
        number = text_of(unit, "조문번호")
        branch = text_of(unit, "조문가지번호")
        label = f"제{number}조" + (f"의{branch}" if branch else "")

        lines = [text_of(unit, "조문내용")]
        for para in unit.findall("항"):
            lines.append(text_of(para, "항내용"))
            for item in para.findall("호"):
                lines.append("  " + text_of(item, "호내용"))
                for sub in item.findall("목"):
                    lines.append("    " + text_of(sub, "목내용"))

        articles.append({
            "조문": label,
            "제목": text_of(unit, "조문제목"),
            "시행일자": text_of(unit, "조문시행일자"),
            "내용": "\n".join(line for line in lines if line.strip()),
        })
    return articles


def safe_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def main():
    parser = argparse.ArgumentParser(description="국가법령정보센터 법령 다운로드")
    parser.add_argument("--oc", default=os.environ.get("LAW_OC"),
                        help="Open API 인증키(OC). 환경변수 LAW_OC로도 지정 가능")
    parser.add_argument("--law", action="append",
                        help="내려받을 법령명 (여러 번 지정 가능, 생략하면 기본 목록)")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "laws"),
                        help="저장 폴더 (기본: 이 파일 옆의 laws 폴더)")
    args = parser.parse_args()

    if not args.oc:
        sys.exit("인증키가 없습니다. --oc 내인증키 로 실행하세요.")

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    rows = []

    for name in args.law or DEFAULT_LAWS:
        try:
            title, mst, effective = find_law(args.oc, name)
            xml_bytes = fetch("lawService.do", {
                "OC": args.oc, "target": "law", "type": "XML", "MST": mst,
            })
            articles = parse_articles(xml_bytes)
        except Exception as e:  # 한 법령이 실패해도 나머지는 계속 받는다
            print(f"[실패] {name}: {e}")
            continue

        base = safe_filename(title)
        (out / f"{base}.xml").write_bytes(xml_bytes)
        (out / f"{base}.json").write_text(json.dumps({
            "법령명": title, "법령일련번호": mst, "시행일자": effective, "조문": articles,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        rows += [{"법령명": title, **a} for a in articles]
        print(f"[완료] {title} (시행 {effective}) 조문 {len(articles)}개")
        time.sleep(0.5)  # 서버 부담을 줄이기 위해 잠깐 쉰다

    if rows:
        # utf-8-sig: 엑셀에서 한글이 깨지지 않게
        with open(out / "articles.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["법령명", "조문", "제목", "시행일자", "내용"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n저장 위치: {out.resolve()}  (전체 조문 {len(rows)}개 → articles.csv)")


if __name__ == "__main__":
    main()
