"""OCR 파이프라인 검증용 가짜 통장 이미지/PDF 생성기.

실제 은행 자료나 개인정보는 절대 사용하지 않는다. 여기서 만드는 내용은
전부 테스트를 위해 지어낸 가상의 거래내역이다.

실행:
    python tests/fixtures/generate_fake_bank_statement.py
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "/usr/share/fonts/truetype/nanum/NanumGothicCoding.ttf"
FONT_PATH_BOLD = "/usr/share/fonts/truetype/nanum/NanumGothicCodingBold.ttf"

# (날짜, 시간, 거래내용, 입금 or None, 출금 or None, 잔액)
FAKE_LINES = [
    ("2026-09-01", "09:12:00", "A회사", 1_500_000, None, 5_000_000),
    ("2026-09-02", "14:03:00", "KT", None, 55_000, 4_945_000),
    ("2026-09-03", "10:45:00", "네이버", None, 220_000, 4_725_000),
    ("2026-09-05", "16:20:00", "B거래처 자문료", 800_000, None, 5_525_000),
    ("2026-09-08", "11:00:00", "사무실 임차료", None, 1_000_000, 4_525_000),
]


def _format_amount(v: int | None) -> str:
    return f"{v:,}" if v is not None else None


def build_lines() -> list[str]:
    lines = ["OO은행 사업용통장 거래내역 (테스트용 가짜 자료)", ""]
    for date, time, desc, income, expense, balance in FAKE_LINES:
        parts = [date, time, desc]
        if income is not None:
            parts.append(f"입금 {_format_amount(income)}")
        if expense is not None:
            parts.append(f"출금 {_format_amount(expense)}")
        parts.append(f"잔액 {_format_amount(balance)}")
        lines.append("  ".join(parts))
    return lines


def render_image(lines: list[str], width: int = 1400) -> Image.Image:
    font_title = ImageFont.truetype(FONT_PATH_BOLD, 28)
    font_body = ImageFont.truetype(FONT_PATH, 24)

    line_height = 44
    height = 60 + line_height * len(lines)
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)

    y = 30
    for i, line in enumerate(lines):
        font = font_title if i == 0 else font_body
        draw.text((30, y), line, font=font, fill="black")
        y += line_height
    return img


def main() -> None:
    out_dir = Path(__file__).resolve().parent
    lines = build_lines()
    img = render_image(lines)

    png_path = out_dir / "fake_bank_statement.png"
    img.save(png_path)
    print("생성:", png_path)

    jpg_path = out_dir / "fake_bank_statement.jpg"
    img.convert("RGB").save(jpg_path, quality=90)
    print("생성:", jpg_path)

    # 텍스트 기반 PDF (스캔이 아닌, 인터넷뱅킹에서 바로 내보낸 형태를 흉내).
    # PyMuPDF 기본 폰트는 한글 글리프가 없어 한글이 깨지므로, 한글이 포함된
    # 나눔고딕코딩 폰트를 명시적으로 지정한다.
    try:
        import pymupdf as fitz  # PyMuPDF

        pdf_path = out_dir / "fake_bank_statement.pdf"
        doc = fitz.open()
        page = doc.new_page(width=700, height=60 + 24 * len(lines))
        y = 30
        for line in lines:
            page.insert_text((30, y), line, fontsize=12, fontfile=FONT_PATH, fontname="F0")
            y += 24
        doc.save(pdf_path)
        doc.close()
        print("생성:", pdf_path)
    except ImportError:
        print("PyMuPDF가 없어 PDF 생성은 건너뜁니다.")

    # 스캔 PDF(텍스트 레이어 없이 이미지만 포함) 버전도 하나 만든다.
    try:
        import pymupdf as fitz

        scanned_pdf_path = out_dir / "fake_bank_statement_scanned.pdf"
        img_bytes_path = out_dir / "_tmp_scan_page.png"
        img.save(img_bytes_path)
        doc = fitz.open()
        rect = fitz.Rect(0, 0, img.width, img.height)
        page = doc.new_page(width=img.width, height=img.height)
        page.insert_image(rect, filename=str(img_bytes_path))
        doc.save(scanned_pdf_path)
        doc.close()
        img_bytes_path.unlink(missing_ok=True)
        print("생성:", scanned_pdf_path)
    except ImportError:
        pass

    build_fake_table_pdf(out_dir / "fake_bank_table_statement.pdf")


# (순번, 날짜, 시간, 적요, 입금액 or None, 출금액 or None, 내용, 잔액, 거래점명)
FAKE_TABLE_ROWS = [
    (1, "2026.09.01", "09:12:00", "타행IB", 1_500_000, None, "가짜회사", 5_000_000, "테스트"),
    (2, "2026.09.02", "14:03:00", "카드결", None, 55_000, "가짜통신사", 4_945_000, "테스트"),
    (3, "2026.09.03", "10:45:00", "BZ뱅크", None, 220_000, "가짜포털", 4_725_000, "테스트"),
    (4, "2026.09.05", "16:20:00", "타행IB", 800_000, None, "가짜거래처", 5_525_000, "테스트"),
    (5, "2026.09.08", "11:00:00", "FB자동", None, 1_000_000, "가짜임차료", 4_525_000, "테스트"),
    # 실제 파일처럼 입금/출금이 둘 다 0인(신규 등록 등) 행도 하나 넣어 '확인필요' 처리를 검증한다.
    (6, "2026.09.09", "09:00:00", "신규", None, None, "", 4_525_000, "테스트"),
]

# 실제 은행 PDF처럼 각 열 사이 간격을 넉넉히 두어, 내용이 옆 열로 침범하지 않게 한다.
_TABLE_COLUMN_X = {
    "No": 20,
    "거래일시": 55,
    "적요": 140,
    "입금액": 200,
    "출금액": 270,
    "내용": 340,
    "잔액": 420,
    "거래점명": 500,
}


def build_fake_table_pdf(out_path: Path) -> None:
    """실제 인터넷뱅킹 '계좌별거래내역' 표 형식을 흉내낸 가짜 테스트 PDF를 만든다.

    가짜 회사명/금액만 사용하며 실제 계좌 정보는 전혀 포함하지 않는다. 실제
    은행 PDF처럼 날짜와 시간을 두 줄로 나눠 넣어(줄바꿈), 파서가 이를 다시
    합쳐 인식하는지도 함께 검증한다.
    """
    import pymupdf as fitz

    doc = fitz.open()
    page = doc.new_page(width=600, height=60 + 20 * (len(FAKE_TABLE_ROWS) + 1))
    fontfile = FONT_PATH

    def put(col: str, y: float, text: str) -> None:
        page.insert_text((_TABLE_COLUMN_X[col], y), text, fontsize=9, fontfile=fontfile, fontname="F0")

    header_y = 30
    for col in ("No", "거래일시", "적요", "입금액", "출금액", "내용", "잔액", "거래점명"):
        put(col, header_y, col)

    y = header_y + 20
    for no, date, time, code, income, expense, content, balance, branch in FAKE_TABLE_ROWS:
        put("No", y, str(no))
        # 실제 은행 PDF와 동일하게 날짜(윗줄)/시간(아랫줄)을 살짝 나눠 넣는다.
        put("거래일시", y - 3, date)
        put("거래일시", y + 6, time)
        put("적요", y, code)
        put("입금액", y, f"{income:,}" if income is not None else "0")
        put("출금액", y, f"{expense:,}" if expense is not None else "0")
        if content:
            put("내용", y, content)
        put("잔액", y, f"{balance:,}")
        put("거래점명", y, branch)
        y += 20

    doc.save(out_path)
    doc.close()
    print("생성:", out_path)


if __name__ == "__main__":
    sys.exit(main())
