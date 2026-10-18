# 실제 AI 응답을 화면에서 과장 없이 설명하기 위한 해석 계층이다.
# 장면을 선택했다는 사실, 설명에 대한 AI 재검토, 사건 관련성 판단을 분리한다.
# 원본 모델 응답을 수정하거나 정상·치팅 정답으로 바꾸지 않는다.

"""Separate retrieval coverage, model grounding and scene-link judgments."""

from caer.retrieval.v7 import WEIGHTS


def summarize(package, report):
    """입력: 사건 자료와 실제 분석. 출력: 표시용 판단과 비교 상태.

    supported는 설명이 사진에 부합한다는 재검토 응답이다. 불확실하다는
    설명도 supported일 수 있으므로 이 값만으로 사건 관련성을 올리지 않는다.
    """
    extra_ids = set(package["methods"]["proposed"]) - set(package["methods"]["fixed"])
    # 최근성만으로도 영상은 선택된다. 비최근성 단서의 유무를 관련성 판정과 따로 남긴다.
    selected_ids = set(package["methods"]["proposed"])
    selected_bins = [row for row in package.get("bins", []) if row["bin_id"] in selected_ids]
    known_features = (
        bool(selected_ids)
        and len(selected_bins) == len(selected_ids)
        and all(set(WEIGHTS) <= set(row.get("features", {})) for row in selected_bins)
    )
    signal_ids = [
        row["bin_id"]
        for row in selected_bins
        if any(row.get("features", {}).get(key, 0) > 0 for key in WEIGHTS if key != "recency")
    ]
    selection_basis = (
        "action_candidates" if signal_ids else "recency_only" if known_features else "unknown"
    )
    rows = []
    for finding in report["findings"]:
        review = finding["crosscheck"]["verdict"]
        relation = finding["scene_relevance"]
        # 미지원·불확실 재검토가 있는 설명은 화면에서도 관련 후보로 확정해 표시하지 않는다.
        display_relation = relation if review == "supported" else "uncertain"
        rows.append(
            dict(
                bin_id=finding["bin_id"],
                additional=finding["bin_id"] in extra_ids,
                description_review=review,
                scene_relation=display_relation,
                original_scene_relation=relation,
            )
        )
    linked_extra = [
        row for row in rows if row["additional"] and row["scene_relation"] == "relevant"
    ]
    if linked_extra:
        state = "model_linked_candidate"
    elif extra_ids:
        state = "additional_action_only"
    else:
        state = "same_selection"
    return dict(
        state=state,
        selection_basis=selection_basis,
        signal_bin_ids=sorted(signal_ids),
        additional_ids=sorted(extra_ids),
        model_linked_additional_ids=[row["bin_id"] for row in linked_extra],
        rows=rows,
        human_relevance_verified=False,
        cheating_assessed=False,
    )
