"""부가세(10%) 계산 도우미.

통장/카드에 찍힌 금액은 절대 바꾸지 않는다 (잔액이 틀어지므로). 부가세 여부가 '과세'인
거래에 대해서만 화면·집계·내보내기에서 공급가액과 부가세를 나눠서 보여줄 때 사용한다.
float를 쓰지 않고 정수 연산만 사용한다.
"""
VAT_INCLUDED_STATUS = "과세"


def split_vat(amount: int) -> tuple[int, int]:
    """부가세 포함 금액을 (공급가액, 부가세)로 나눈다.

    공급가액 = 금액 ÷ 1.1 (원 미만 반올림), 부가세 = 금액 - 공급가액.
    예) 110,000 -> (100,000, 10,000), 329,725 -> (299,750, 29,975)
    취소·환불(음수)도 같은 규칙으로 부호만 유지한다.
    """
    amount = int(amount)
    sign = -1 if amount < 0 else 1
    total = abs(amount)
    # round(total * 10 / 11)을 정수로: floor((20 * total + 11) / 22)
    supply = (total * 20 + 11) // 22
    return sign * supply, sign * (total - supply)


def vat_of(amount: int, vat_status: str) -> int:
    """부가세 여부가 '과세'면 부가세액, 아니면 0."""
    return split_vat(amount)[1] if vat_status == VAT_INCLUDED_STATUS else 0


def looks_vat_included(amount: int) -> bool:
    """금액이 11로 나누어떨어지면(= 공급가액의 정확히 110%로 보이면) True.

    '부가세 포함처럼 보인다'는 약한 신호일 뿐이다 - 예: 이자 418원도 11로 나누어떨어진다.
    그래서 이 값만으로 확정하지 않고, 회계구분이 매출·비용인 거래에 '추천'할 때만 쓴다.
    """
    amount = abs(int(amount))
    return amount > 0 and amount % 11 == 0
