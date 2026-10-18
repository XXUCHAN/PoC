# 한 사건의 전체 처리 흐름을 연결한다.
# 원본 확인 → 시간 동기화 → 2초 구간의 특징 계산 → 구간 선택 → 비교 영상·프레임 저장 순서다.
# 이 단계는 AI를 호출하지 않는다. 생성된 자료의 AI 분석은 analysis/visual.py가 담당한다.

"""Current ingestion -> v7 retrieval -> media pipeline, without experiment files."""

import json
import random
from pathlib import Path
import pandas as pd
from caer.config import ROOT, DATA, RUNTIME, OUTPUTS, REPO, REVISION
from caer.ingestion.source import download, relative_path
from caer.ingestion.schema import read_ticks, validate_asset_identity, validate_time
from caer.ingestion.io import sha, write_json, log
from caer.ingestion.catalog import load_samples
from caer.selection.cases import mine
from caer.retrieval.v7 import bins, intervals, features, predict, WEIGHTS
from caer.media.clips import duration, export, frame_interval
from caer.media.frames import sample_frames

ALGORITHM = "persistent_balanced"


# 입력: 원본의 공개 경로와 다운로드 허용 여부. 출력: 검증된 로컬 파일 경로.
# 로컬 모드에서는 버전·해시·바이트가 일치하는 기존 파일만 사용한다.
def source_asset(value, fetch=True):
    if fetch:
        return download(value)
    path = DATA / "source" / relative_path(value)
    manifest = path.with_suffix(path.suffix + ".source.json")
    if not path.is_file() or not manifest.is_file():
        raise ValueError("Local source is missing; run without --local to download selected assets")
    info = json.loads(manifest.read_text())
    if (
        info["revision"] != REVISION
        or info["sha256"] != sha(path)
        or info["bytes"] != path.stat().st_size
    ):
        raise ValueError("Local source provenance mismatch")
    return path


# 입력: 공격자 POV를 포함한 사건 메타데이터. 출력: 생성 자료를 설명하는 package 딕셔너리.
# 사건의 실제 원본을 검사한 뒤 검색과 영상 생성을 수행하며, AI 판단은 여기서 실행하지 않는다.
def case_run(case, fetch=True):
    case_dir = RUNTIME / "cases" / case["case_id"]
    case_dir.mkdir(parents=True, exist_ok=True)
    for value in [case["pov"]["preview_video"]["path"], case["pov"]["ticks_parquet_path"]]:
        validate_asset_identity(value, case, case["attacker_player_slot"])
    source_video = source_asset(case["pov"]["preview_video"]["path"], fetch)
    attacker_ticks_path = source_asset(case["pov"]["ticks_parquet_path"], fetch)
    # 사건 틱과 영상 시각을 먼저 맞춘 뒤 프레임을 뽑는다.
    synchronization = validate_time(
        case, read_ticks(attacker_ticks_path), duration(source_video), frame_interval(source_video)
    )
    candidate_bins = [
        dict(bin_id=i, start_s=a, end_s=b)
        for i, (a, b) in enumerate(bins(float(case["event_seconds"])))
    ]
    package = dict(
        version="0.2.0",
        algorithm="v7",
        variant=ALGORITHM,
        source=dict(repo=REPO, revision=REVISION),
        case=case,
        source_video=str(source_video.resolve()),
        attacker_ticks=str(attacker_ticks_path.resolve()),
        synchronization=synchronization,
        bins=candidate_bins,
    )
    # 전체 후보 사진은 검색 특징 계산에 사용하고, AI에는 선택된 구간과 사건 주변 사진만 보낸다.
    frames = sample_frames(package, case_dir / "frames")
    candidate_rows = features(package, case_dir / "frames") if candidate_bins else []
    selected_ids, candidate_scores = predict(candidate_rows)
    weights = WEIGHTS
    # 관측 장비·입력과 추정한 공간·가림을 구분해 남긴다. supported는 이 규칙의 단서 유무다.
    for row, value in zip(candidate_rows, candidate_scores):
        feature_values = row["features"]
        row.update(
            score=value,
            weights=weights,
            observed=[
                key
                for key in (
                    "smoke_state",
                    "fire_state",
                    "flash_state",
                    "he_state",
                    "firearm_attack",
                )
                if feature_values[key] > 0
            ],
            inferred=[
                key
                for key in ("anchor_scene_proximity_candidate", "strong_obscuration")
                if feature_values[key] > 0
            ],
            confidence_label="candidate",
            supported=any(feature_values[key] > 0 for key in weights if key != "recency"),
        )
    candidate_ids = [b["bin_id"] for b in candidate_bins]
    budget = min(6, len(candidate_ids))
    # 고정 방식은 검색 영역의 마지막 6조각이다. 무작위 비교 ID는 사건별 시드로 재현한다.
    methods = dict(
        proposed=selected_ids,
        anchor_only=[],
        fixed=candidate_ids[-budget:] if budget else [],
        random=sorted(random.Random("caer-v7:" + case["case_id"]).sample(candidate_ids, budget)),
        full_round=candidate_ids,
    )
    anchor = float(case["event_seconds"])
    anchor_clip = export(
        source_video,
        max(0.0, anchor - 6),
        min(duration(source_video), anchor + 6),
        case_dir / "anchor.mp4",
    )
    comparison_clips = {}
    # 실제 비교용 영상은 자동 검색과 고정 방식만 만들며, 두 방식 모두 추가 길이를 12초로 제한한다.
    for method in ("proposed", "fixed"):
        comparison_clips[method] = [
            export(source_video, a, b, case_dir / f"{method}_{i}.mp4")
            for i, (a, b) in enumerate(intervals(candidate_bins, methods[method]))
        ]
        if sum(c["actual_duration_s"] for c in comparison_clips[method]) > 12 + 1e-5:
            raise ValueError("Encoded context exceeds 12 seconds")
    # 원본과 구현의 해시를 남겨 다른 실행 결과와 섞여 재사용되는 것을 추적한다.
    source_hashes = {
        name: sha(ROOT / name)
        for name in [
            "src/caer/pipeline.py",
            "src/caer/retrieval/v7.py",
            "src/caer/ingestion/schema.py",
            "src/caer/media/frames.py",
            "src/caer/media/clips.py",
        ]
    }
    package.update(
        bins=candidate_rows,
        methods=methods,
        anchor=anchor_clip,
        clips=comparison_clips,
        context=comparison_clips["proposed"],
        fixed_context=comparison_clips["fixed"],
        frames=frames,
        status="ready" if selected_ids else "insufficient_context",
        reason=None if selected_ids else "No complete two-second context bins before anchor",
        extra_clip_seconds=sum(c["actual_duration_s"] for c in comparison_clips["proposed"]),
        evaluation="NOT_EVALUATED",
        ai_analysis="NOT_RUN",
        source_hashes=source_hashes,
        source_video_sha256=sha(source_video),
        attacker_ticks_sha256=sha(attacker_ticks_path),
    )
    write_json(case_dir / "package.json", package)
    pd.DataFrame(
        [
            dict(
                bin_id=b["bin_id"],
                start_s=b["start_s"],
                end_s=b["end_s"],
                score=b["score"],
                selected=b["bin_id"] in selected_ids,
                **b["features"],
            )
            for b in candidate_rows
        ]
    ).to_csv(case_dir / "timeline.csv", index=False)
    log(
        "runtime_v7_case_success",
        case_id=case["case_id"],
        extra_clip_seconds=package["extra_clip_seconds"],
    )
    return package


# 출력: UI에서 사용할 준비된 샘플과 새로 생성한 사건 목록.
# 같은 사건 ID로 새 자료가 생성되면 기본 샘플보다 새 자료를 우선한다.
def load_packages():
    packages = {package["case"]["case_id"]: package for package in load_samples()}
    for package_path in sorted((RUNTIME / "cases").glob("*/package.json")):
        package = json.loads(package_path.read_text())
        package["package_path"] = str(package_path.resolve())
        packages[package["case"]["case_id"]] = package
    return list(packages.values())


# 입력: 처리 개수, 원본 다운로드 허용 여부, 선택적인 사건 ID. 출력: 처리 요약.
# 준비된 샘플 ID는 샘플 메타데이터를 재사용하고, 그 외에는 원본 목록에서 후보를 찾는다.
def run(limit=1, fetch=True, case_id=None):
    if not 1 <= limit <= 30:
        raise ValueError("Choose 1..30 explicitly selected cases")
    samples = {p["case"]["case_id"]: p for p in load_samples()}
    # 샘플 재생성은 대규모 메타데이터를 다시 받지 않고 포함된 사건 정보를 사용한다.
    if case_id in samples:
        cases = [samples[case_id]["case"]]
    else:
        files = {
            k: source_asset(rel, fetch)
            for k, rel in [
                ("kills", "events/kills.parquet"),
                ("pov_rounds", "index/pov_rounds.parquet"),
            ]
        }
        cases = mine(files["kills"], files["pov_rounds"], 1000 if case_id else limit)
        if case_id:
            cases = [c for c in cases if c["case_id"] == case_id]
            if not cases:
                raise ValueError("Case ID is not an eligible event")
    results = []
    for case in cases:
        package = case_run(case, fetch)
        results.append(dict(case_id=case["case_id"], context_seconds=package["extra_clip_seconds"]))
    return dict(status="COMPLETED", cases=results, ai_analysis="NOT_RUN")
