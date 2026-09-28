"""OCR 엔진 추상 인터페이스.

로컬 OCR(Tesseract)을 기본으로 사용하되, 나중에 다른 엔진(상용 API 등)으로
교체하거나 나란히 추가할 수 있도록 인터페이스를 분리한다.
외부 API를 쓰게 되는 경우에도 API 키는 코드에 하드코딩하지 않고
환경변수로만 전달한다 (local_ocr.py는 API 키가 필요 없다).
"""
from abc import ABC, abstractmethod

# 표준 거래 후보 구조. 값이 불확실하면 절대 추정하지 않고 None + status='확인필요'로 둔다.
CANDIDATE_TEMPLATE = {
    "date": None,
    "time": None,
    "description": "",
    "income": None,
    "expense": None,
    "balance": None,
    "confidence": None,
    "status": "확인필요",
}

STATUS_OK = "정상"
STATUS_NEEDS_REVIEW = "확인필요"
STATUS_SUSPECTED_DUPLICATE = "중복의심"


class OCREngine(ABC):
    @abstractmethod
    def extract_candidates(self, file_path: str, file_type: str) -> list[dict]:
        """파일(이미지 또는 PDF) 1개에서 거래 후보 목록을 추출한다.

        각 항목은 CANDIDATE_TEMPLATE와 동일한 키를 갖는 dict여야 한다.
        """
        raise NotImplementedError
