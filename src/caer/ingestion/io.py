# 파일 해시, JSON 저장, 실행 기록에 공통으로 쓰는 입출력 함수다.

import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from caer.config import OUTPUTS


# 입력: 파일 경로. 출력: 내용의 SHA-256 문자열.
# 큰 영상도 한 번에 메모리에 올리지 않도록 1MiB씩 읽는다.
def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


# 입력: 저장 경로와 JSON으로 표현 가능한 값. 상위 폴더를 만들고 저장한다.
# NaN 같은 비표준 숫자를 허용하지 않아 자료의 모호한 기록을 막는다.
def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


# 입력: 사건 이름과 부가 필드. .work/runs.jsonl에 시각과 함께 한 줄씩 기록한다.
def log(event, **fields):
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    with (OUTPUTS / "runs.jsonl").open("a") as f:
        f.write(
            json.dumps(
                dict(time=datetime.now(timezone.utc).isoformat(), event=event, **fields),
                ensure_ascii=False,
            )
            + "\n"
        )
