# UI가 쓸 영상과 실제 분석 기록을 한 사건 단위로 준비한다.
# 고정 방식과 자동 검색은 같은 12초 예산으로 비교한다.

"""Submission flow: one case, selected context, actual AI report and evidence."""

import json
import hashlib
import subprocess
import tempfile
from pathlib import Path

from src.config import OUTPUTS
from src.ingestion.io import sha
from src.media.clips import duration
from src.ingestion.io import write_json
from src.analysis import visual as ai
from src.analysis.interpretation import summarize

MODEL = "gpt-6.1-sol"
DEFAULT_CASE = "7a5b762e8daf15bcffd5"
ROOT = OUTPUTS / "demo"


# 입력: 사건 package와 비교 방식. 출력: UI용 단일 영상 경로·길이·원본 구간 목록.
# 여러 조각은 시간순으로 연결하고, 입력 해시가 같은 연결 영상만 재사용한다.
def combined_context(package, method="proposed"):
    """Join already-selected clips chronologically without altering frozen media."""
    if method not in ("proposed", "fixed"):
        raise ValueError("Unknown comparison method")
    segments = sorted(
        package["context"] if method == "proposed" else package["fixed_context"],
        key=lambda c: c["start_s"],
    )
    if not segments:
        raise ValueError("No context video is available for this case")
    # 조각의 원본 시각·경로·내용 해시를 연결 영상의 재사용 키에 포함한다.
    input_segments = [
        dict(
            start_s=segment["start_s"],
            end_s=segment["end_s"],
            path=segment["path"],
            sha256=sha(segment["path"]),
        )
        for segment in segments
    ]
    expected_seconds = sum(segment["actual_duration_s"] for segment in segments)
    if expected_seconds > 12 + 1e-5:
        raise ValueError("Selected context exceeds the video budget")
    # 이미 연속된 한 영상이면 불필요하게 다시 연결하지 않는다.
    if len(segments) == 1:
        actual_seconds = duration(segments[0]["path"])
        if abs(actual_seconds - expected_seconds) > 0.06:
            raise ValueError("Context duration changed")
        return dict(
            path=segments[0]["path"], actual_duration_s=actual_seconds, segments=input_segments
        )
    cache_key = hashlib.sha256(json.dumps(input_segments, sort_keys=True).encode()).hexdigest()
    cache_dir = ROOT / package["case"]["case_id"] / cache_key
    cache_dir.mkdir(parents=True, exist_ok=True)
    target_path = cache_dir / "context.mp4"
    manifest_path = cache_dir / "context.json"
    if target_path.is_file() and manifest_path.is_file():
        saved = json.loads(manifest_path.read_text())
        if saved["segments"] != input_segments or saved["sha256"] != sha(target_path):
            raise ValueError("Combined context cache mismatch")
        return saved
    with tempfile.TemporaryDirectory(prefix="caer-demo-") as folder:
        listing = Path(folder) / "clips.txt"
        # JSON is not shell escaping. This file uses ffmpeg concat's own quoting.
        listing.write_text(
            "".join(
                "file '" + str(Path(segment["path"]).resolve()).replace("'", "'\\''") + "'\n"
                for segment in segments
            )
        )
        temp_video = Path(folder) / "context.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(temp_video),
            ],
            check=True,
            capture_output=True,
        )
        actual_seconds = duration(temp_video)
        if abs(actual_seconds - expected_seconds) > 0.06:
            raise ValueError("Joined context duration mismatch")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(temp_video), "-f", "null", "-"],
            check=True,
            capture_output=True,
        )
        # Same filesystem is not guaranteed for the temporary directory.
        target_path.write_bytes(temp_video.read_bytes())
    saved = dict(
        path=str(target_path.resolve()),
        actual_duration_s=actual_seconds,
        segments=input_segments,
        sha256=sha(target_path),
    )
    write_json(manifest_path, saved)
    return saved


# 입력: 한 사건 package. 출력: 사건·비교 영상·분석과 재사용 여부를 담은 UI 결과.
# 유효한 실제 분석이 없을 때만 새 분석을 호출하므로 준비된 샘플 시연은 모델 호출이 없다.
def run_case(package):
    """Reuse a current real report; otherwise invoke the fixed configured provider."""
    ai.verify_inputs(package)
    context = combined_context(package)
    fixed = combined_context(package, "fixed")
    report = ai.latest_analysis(package)
    reused = report is not None
    if report is None:
        report = ai.analyze_case(package["case"]["case_id"], provider="codex", model=MODEL)
    return dict(
        case_id=package["case"]["case_id"],
        context=context,
        fixed=fixed,
        report=report,
        report_sha256=sha(report["report_path"]),
        reused_analysis=reused,
        package_sha256=sha(package["package_path"]),
        interpretation=summarize(package, report),
    )


# 입력: 분석 보고서와 선택적인 사건 package. 출력: 화면에서 강조할 실제 finding.
# 샘플의 시연 지정은 표시 순서만 정하며 AI가 생성한 관찰·관련성·불확실성을 바꾸지 않는다.
def featured_finding(report, package=None):
    """Show a cited, checked observation; keep uncertain/unsupported claims explicit."""
    findings = report["findings"]
    if not findings:
        raise ValueError("AI analysis has no findings")
    # 시연용 강조 구간을 지정해도 아래 AI의 관찰과 관련성 판정 자체는 그대로 둔다.
    if package and "presentation" in package:
        bid = package["presentation"]["featured_bin_id"]
        return next(f for f in findings if f["bin_id"] == bid)

    # 근거가 뒷받침된 설명, 관련성, 고정 영상 밖 여부, 발사 장면 여부, 시각 순서로 우선순위를 정한다.
    # supported는 설명이 사진과 부합한다는 AI 응답이며 사건 관련성 확정과는 다르다.
    def rank(f):
        supported = f["crosscheck"]["verdict"] == "supported"
        additional = package is not None and f["bin_id"] not in package["methods"]["fixed"]
        return (
            not supported,
            {"relevant": 0, "uncertain": 1, "irrelevant": 2}[f["scene_relevance"]],
            not additional,
            f["category"] != "firing_visible",
            f["start_s"],
        )

    return min(findings, key=rank)
