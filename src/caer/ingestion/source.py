# 선택한 공개 원본 파일만 내려받고 출처·버전·내용 해시를 기록한다.
# 전체 데이터셋을 무조건 내려받지 않으며, 파일별 전송량을 제한한다.

"""Explicit file downloads only, pinned revision, bounded transfer, provenance."""

import hashlib
import json
import urllib.request
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from caer.config import DATA, REPO, REVISION


# 입력: 고정 데이터셋의 hf 경로 또는 데이터셋 내부 상대 경로. 출력: 안전한 상대 경로.
# 절대 경로·상위 폴더 이동·다른 URL은 거부한다.
def relative_path(value):
    prefix = f"hf://datasets/{REPO}@main/"
    if value.startswith(prefix):
        value = value[len(prefix) :]
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or "://" in value:
        raise ValueError(f"Unsupported source path: {value}")
    return str(p)


# 입력: 원본 경로와 파일별 MiB 상한. 출력: 검증된 다운로드 파일 경로.
# 같은 버전의 캐시가 내용 해시까지 맞으면 재사용하고, 새 파일에는 출처 기록을 남긴다.
def download(value, limit_mb=100):
    rel = relative_path(value)
    path = DATA / "source" / rel
    manifest = path.with_suffix(path.suffix + ".source.json")
    if path.exists() and manifest.exists():
        info = json.loads(manifest.read_text())
        if (
            info["revision"] == REVISION
            and info["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        ):
            return path
    path.parent.mkdir(parents=True, exist_ok=True)
    # 메타데이터의 @main 표기는 해석만 하고 실제 요청은 고정 REVISION으로 보낸다.
    url = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{rel}"
    # 다운로드 중인 파일은 .part로 저장해 미완료 파일을 완성된 원본으로 오인하지 않게 한다.
    part = path.with_suffix(path.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, part.open("wb") as f:
            size = 0
            # 응답의 길이 표시만 믿지 않고 실제 받은 바이트 수로 상한을 검사한다.
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > limit_mb * 1024**2:
                    raise ValueError(f"Transfer exceeds {limit_mb} MB: {rel}")
                f.write(chunk)
        # 전체 수신이 끝나면 최종 파일로 바꾸고 출처·시각·해시를 기록한다.
        part.replace(path)
        manifest.write_text(
            json.dumps(
                dict(
                    repo=REPO,
                    revision=REVISION,
                    path=rel,
                    bytes=size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                ),
                indent=2,
            )
        )
    except Exception:
        part.unlink(missing_ok=True)
        raise
    return path
