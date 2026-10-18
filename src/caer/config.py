# 공개 데이터 버전, 고정 분석 모델, 실행 경로를 한곳에서 관리한다.
# 제출 샘플(sample)과 실행 중 생기는 파일(.work)을 분리한다.

from pathlib import Path
import os

# CAER_HOME을 지정하지 않으면 src/caer에서 두 단계 위인 프로젝트 루트를 사용한다.
ROOT = Path(os.environ.get("CAER_HOME", Path(__file__).resolve().parents[2])).resolve()
REPO = "blanchon/opencs2_dataset"
# 공개 원본을 특정 커밋으로 고정해 재실행 때 자료가 달라지는 것을 줄인다.
REVISION = "8d7deddcd30c081fb197b75f58b4a0fba1117b9d"
SAMPLE = ROOT / "sample"
OUTPUTS = ROOT / ".work"
DATA = OUTPUTS / "data"
RUNTIME = OUTPUTS / "runtime"
# 새 분석도 시연 기록과 같은 모델로만 실행한다. 준비된 시연에는 모델 호출이 필요 없다.
MODEL = "gpt-6.1-sol"
