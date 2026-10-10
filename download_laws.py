"""국가법령정보센터 Open API로 노동 관계 법령을 내려받아 조문 단위로 저장한다.

사용법:
    python download_laws.py --oc 내인증키
    python download_laws.py --oc 내인증키 --law 근로기준법 --law 최저임금법

결과(laws/ 폴더):
    <법령명>.xml   API 원본 응답
    <법령명>.json  조문 단위로 정리한 데이터
    articles.csv   전체 조문 목록 (엑셀에서 바로 열림)
    versions/<법령명>/  --since 이후 시행된 과거 버전들 (법 개정 비교용)
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
    """법령명으로 검색해 현행 법령의 (법령명, 법령일련번호, 시행일자, 법령ID)를 돌려준다."""
    root = ET.fromstring(fetch("lawSearch.do", {
        "OC": oc, "target": "law", "type": "XML", "query": name, "display": 100,
    }))
    if root.findtext("resultCode") not in (None, "00"):
        raise RuntimeError(root.findtext("resultMsg") or "검색 실패")

    candidates = []
    for law in root.iter("law"):
        title = (law.findtext("법령명한글") or "").strip()
        candidates.append((title, law.findtext("법령일련번호"), law.findtext("시행일자"), law.findtext("법령ID")))
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


def is_html(data):
    head = data[:200].lstrip().lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html")


def fetch_versions(oc, law_id):
    """법령ID의 모든 시행 버전(연혁·현행·시행예정)을 시행일 오름차순으로 돌려준다."""
    rows, page = [], 1
    while True:
        data = fetch("lawSearch.do", {
            "OC": oc, "target": "eflaw", "type": "XML", "LID": law_id,
            "nw": "1,2,3", "display": 100, "page": page,
        })
        if is_html(data):
            raise RuntimeError("연혁 목록 대신 안내 페이지가 왔습니다")
        root = ET.fromstring(data)
        total = int(root.findtext("totalCnt") or 0)
        if total > 1000:  # LID가 무시되고 전체 법령 목록이 온 경우
            raise RuntimeError(f"연혁 목록이 비정상적으로 큽니다({total}건)")
        for law in root.iter("law"):
            if int(text_of(law, "법령ID") or -1) != int(law_id):
                continue
            ef, mst = text_of(law, "시행일자"), text_of(law, "법령일련번호")
            if not re.fullmatch(r"\d{8}", ef) or not mst or "폐지" in text_of(law, "제개정구분명"):
                continue
            rows.append({
                "시행일자": ef, "법령일련번호": mst,
                "공포일자": text_of(law, "공포일자"),
                "공포번호": int(text_of(law, "공포번호") or 0),
                "제개정구분": text_of(law, "제개정구분명"),
                "현행연혁": text_of(law, "현행연혁코드"),
            })
        if page * 100 >= total or page >= 10:
            break
        page += 1

    rows.sort(key=lambda r: (r["시행일자"], r["공포일자"], r["공포번호"]))
    # 같은 날 시행되는 공포본이 여럿이면 나중 공포본이 앞 공포본을 반영한 통합본이다
    by_date = {}
    for r in rows:
        kinds = by_date[r["시행일자"]]["제개정구분"].split("·") if r["시행일자"] in by_date else []
        by_date[r["시행일자"]] = {**r, "제개정구분": "·".join(dict.fromkeys(kinds + [r["제개정구분"]]))}
    return [by_date[d] for d in sorted(by_date)]


def fetch_version_articles(oc, version):
    """특정 시행 버전의 조문. 과거본은 법령일련번호와 그 버전의 시행일자를 함께 줘야 받을 수 있다."""
    data = fetch("lawService.do", {
        "OC": oc, "target": "eflaw", "type": "XML",
        "MST": version["법령일련번호"], "efYd": version["시행일자"],
    })
    if is_html(data):
        raise RuntimeError("본문 대신 안내 페이지가 왔습니다")
    articles = parse_articles(data)
    if not articles:
        raise RuntimeError("조문이 없습니다")
    return articles, data


def download_history(oc, title, law_id, out, since):
    """since(YYYYMMDD) 이후 시행된 버전과, 그 직전 버전의 조문을 versions/<법령명>/에 받는다.
    이미 받은 버전은 건너뛴다."""
    versions = fetch_versions(oc, law_id)
    before = [v for v in versions if v["시행일자"] < since]
    keep = before[-1:] + [v for v in versions if v["시행일자"] >= since]

    folder = out / "versions" / safe_filename(title)
    folder.mkdir(parents=True, exist_ok=True)
    new, failed = 0, 0
    for v in keep:
        v["파일"] = f"{v['시행일자']}_{v['법령일련번호']}.json"
        path = folder / v["파일"]
        if path.exists():
            continue
        try:
            articles, _ = fetch_version_articles(oc, v)
        except Exception as e:
            print(f"    [경고] {title} {v['시행일자']} 시행본을 받지 못했습니다: {e}")
            v["파일"] = ""
            failed += 1
            continue
        path.write_text(json.dumps({**v, "법령명": title, "조문": articles},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        new += 1
        time.sleep(0.3)

    (folder / "index.json").write_text(json.dumps({
        "법령명": title, "법령ID": law_id, "버전": [v for v in keep if v["파일"]],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(keep) - failed, new, failed


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
    parser.add_argument("--since", default="20180101",
                        help="이 날짜(YYYYMMDD) 이후의 개정 이력을 받는다 (기본: 20180101)")
    parser.add_argument("--no-history", action="store_true", help="개정 이력은 받지 않는다")
    args = parser.parse_args()

    if not args.oc:
        sys.exit("인증키가 없습니다. --oc 내인증키 로 실행하세요.")

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    rows = []

    for name in args.law or DEFAULT_LAWS:
        try:
            title, mst, effective, law_id = find_law(args.oc, name)
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

        if not args.no_history:
            try:
                total, new, failed = download_history(args.oc, title, law_id, out, args.since)
                print(f"    개정 이력: {args.since[:4]}년 이후 시행본 {total}개 (새로 받음 {new}개"
                      + (f", 실패 {failed}개" if failed else "") + ")")
            except Exception as e:
                print(f"    [경고] 개정 이력을 받지 못했습니다: {e}")

    if rows:
        # utf-8-sig: 엑셀에서 한글이 깨지지 않게
        with open(out / "articles.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["법령명", "조문", "제목", "시행일자", "내용"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n저장 위치: {out.resolve()}  (전체 조문 {len(rows)}개 → articles.csv)")


if __name__ == "__main__":
    main()
