# 취업규칙 검토·개정 프로그램

취업규칙 PDF를 올리면 노동 관계 법령을 기준으로 다음을 점검하는 웹 프로그램입니다.
- 필수 기재사항(근로기준법 제93조)이 빠졌는지
- 법령 위반이 의심되는 조항이 있는지

## 처음 한 번: 법령 내려받기

```
python download_laws.py --oc 내인증키
```

- 국가법령정보센터 Open API로 법령을 받아 `laws/` 폴더에 저장합니다.
- Open API 신청 때 등록한 IP의 PC에서만 동작합니다.
- 법령이 개정되면 다시 실행해서 갱신하세요.

## 실행

**`run.bat`를 더블클릭**하면 필요한 패키지를 설치하고, 브라우저에서 http://localhost:8501 을 엽니다.

직접 실행할 때:
```
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## 파일 구성

| 파일 | 역할 |
|---|---|
| `download_laws.py` | 법령 다운로드 |
| `app.py` | 웹 화면 |
| `rule_parser.py` | PDF 텍스트 추출, 조항 분리 |
| `checks.py` | 필수 기재사항·위반 점검 규칙 |
| `law_db.py` | 내려받은 법령 데이터 조회 |

## 주의

- 키워드와 숫자를 기준으로 한 1차 점검이며, 법률 자문이 아닙니다.
- 스캔한 이미지 PDF는 읽을 수 없습니다.

출처: 국가법령정보센터(www.law.go.kr)
