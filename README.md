# CS2 치팅 의심 장면 검토 보조 PoC

의심스러운 킬 장면과 그 이전 행동을 함께 확인하는 PoC입니다. 고정 길이로 자른 영상과 규칙으로 검색한 영상을 비교하고, AI가 작성한 설명과 근거 사진을 보여줍니다. 최종 판단은 사람이 하며, 치팅 판정이나 자동 제재는 수행하지 않습니다.

## 설치·실행

Python 3.11 이상과 FFmpeg/FFprobe가 필요합니다. 프로젝트 폴더에서 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
streamlit run src/interfaces/ui.py
```

Windows에서는 가상환경을 `.venv\Scripts\activate`로 활성화하고, FFmpeg를 설치해 PATH에 추가합니다. 잠금 파일은 Python 3.13/macOS 환경에서 확인한 버전입니다. 다른 환경에서 설치되지 않으면 `python -m pip install -e .`로 설치할 수 있습니다.

**사건 선택 → 사건·고정 영상·검색 영상 비교 → AI 설명과 근거 사진 확인** 순서로 사용합니다. 대표 사례 2건의 영상과 저장된 AI 분석이 포함되어 있어 다운로드나 API 키 없이 시연할 수 있습니다. 화면을 열 때 새 AI 분석을 실행하지 않습니다.

## 폴더 구조

```text
src/
├── ingestion/     공개 데이터 수집·무결성 검사
├── selection/     검토할 킬 사건 선정
├── retrieval/     규칙 기반 이전 행동 구간 검색
├── media/         비교 영상·근거 사진 생성
├── analysis/      AI 설명·재검토·인용 검사
├── evaluation/    샘플 검증·저장된 평가 결과 재계산
├── interfaces/    시연 화면·CLI
├── pipeline.py    전체 처리 흐름
└── config.py      원본 데이터 버전·실행 경로
sample/            대표 사례와 저장된 분석·평가 자료
```

새로 다운로드하거나 생성한 파일은 `.work/`에 저장합니다.

## 주요 명령

```bash
# 대표 사례 목록과 포함된 파일·영상·인용 무결성 검사
poc list
poc verify

# 저장된 AI 참조와 검색 결과로 비교 지표 재계산
poc evaluate

# 대표 사례의 공개 원본 수집·영상 재생성
poc run --case-id 7a5b762e8daf15bcffd5

# 해당 사례를 새로 AI 분석·재검토
poc analyze --case-id 7a5b762e8daf15bcffd5

# 새 검토 후보 1건 수집·처리
poc run --limit 1
```

`poc analyze`는 Codex CLI 설치·로그인과 `gpt-6.1-sol` 접근 권한이 필요하며 계정 사용량을 소비합니다. 나머지 위 명령은 모델을 호출하지 않습니다. `poc run`은 필요한 원본 파일을 다운로드하며, 이미 받은 파일만 사용하려면 `--local`을 추가합니다.

원본 데이터는 [OpenCS2 공개 데이터](https://huggingface.co/datasets/blanchon/opencs2_dataset)의 revision `8d7deddcd30c081fb197b75f58b4a0fba1117b9d`를 사용합니다. 샘플별 `source.json`에 원본 경로와 해시를 기록했습니다. 검증 결과의 해석, 한계와 실제 서비스 적용 방안은 별도 제안서에 정리했습니다.
