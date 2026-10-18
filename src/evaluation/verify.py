# 샘플 해시·선택 점수·영상 재생·AI 인용·평가 수치를 함께 검사한다.
# 검사 통과는 자료와 실행의 일관성을 뜻하며 설명 내용의 독립적인 정답 검증은 아니다.

"""Verify sample integrity, latest-rule selections, citations and playable media."""

import subprocess
from src.pipeline import load_packages
from src.analysis.visual import latest_analysis, verify_inputs
from src.retrieval.v7 import predict, intervals
from src.media.clips import duration
from src.evaluation.reproduce import reproduce


# 출력: 검증 상태, 사례별 프레임·설명 개수, 평가 수치 재현 여부.
# 모델을 새로 호출하지 않고 검색 계산·실제 영상 디코딩·인용 일관성을 확인한다.
def verify():
    cases = []
    for package in load_packages():
        # 저장된 특징으로 검색을 다시 계산해 선택 ID와 점수가 같은지 확인한다.
        selected, scores = predict(package["bins"])
        if selected != package["methods"]["proposed"]:
            raise ValueError("Retrieval selection mismatch")
        if any(abs(r["score"] - s) > 1e-10 for r, s in zip(package["bins"], scores)):
            raise ValueError("Retrieval score mismatch")
        frames = verify_inputs(package)
        report = latest_analysis(package)
        if report is None:
            raise ValueError("AI report missing; run poc analyze for generated cases")
        # 화면에서 강조한 사진도 실제 AI가 인용한 사진이어야 한다.
        if package.get("presentation"):
            focus = package["presentation"]
            finding = next(f for f in report["findings"] if f["bin_id"] == focus["featured_bin_id"])
            if focus["evidence_frame_id"] not in finding["evidence_frame_ids"]:
                raise ValueError("Featured image must be cited by the actual analysis")
        # 두 방식이 정한 원본 구간과 실제 영상의 원본 구간이 같고 길이도 각각 12초인지 확인한다.
        for method, clips in [
            ("proposed", package["context"]),
            ("fixed", package["fixed_context"]),
        ]:
            expected = intervals(package["bins"], package["methods"][method])
            actual = [(c["start_s"], c["end_s"]) for c in clips]
            if actual != expected:
                raise ValueError("Comparison video does not match selected intervals: " + method)
            if abs(sum(duration(c["path"]) for c in clips) - 12) > 0.06:
                raise ValueError("Comparison must use the same 12-second budget")
        # FFmpeg로 끝까지 디코딩해 헤더만 정상인 깨진 영상을 걸러낸다.
        for clip in [package["anchor"], *package["context"], *package["fixed_context"]]:
            if abs(duration(clip["path"]) - clip["actual_duration_s"]) > 0.06:
                raise ValueError("Media duration mismatch")
            subprocess.run(
                ["ffmpeg", "-v", "error", "-i", clip["path"], "-f", "null", "-"],
                check=True,
                capture_output=True,
            )
        seconds = sum(duration(c["path"]) for c in package["context"])
        if seconds > 12 + 1e-5:
            raise ValueError("Context budget exceeded")
        cases.append(
            dict(
                case_id=package["case"]["case_id"],
                input_frames=len(frames),
                ai_findings=len(report["findings"]),
                extra_seconds=seconds,
            )
        )
    evaluation = reproduce()
    return dict(
        status="PASS",
        cases=cases,
        evaluation=evaluation["status"],
        note="Integrity and metric reproducibility only, not independent semantic verification",
    )
