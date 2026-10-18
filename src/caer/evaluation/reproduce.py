# 저장된 40건의 AI 참조와 선택 구간으로 Precision·Recall·F1을 다시 계산한다.
# 새 영상을 주석하거나, 치팅 오탐률 감소 또는 사람의 시간 절감을 입증하는 코드는 아니다.

"""Recalculate the submitted latest retrieval result from locked exported bin data."""

import json
from caer.config import SAMPLE
from caer.ingestion.io import sha


def reference_consistency(data):
    """기존 참조와 후보 재분석의 판단 차이를 센다. 어느 쪽도 정답으로 승격하지 않는다.

    입력 범위·판단 절차가 같다는 전제가 없으므로 모델의 일반 일치율로 해석하지 않는다.
    이 확인은 사후 선택한 후보에 한정되며 전체 40건을 다시 평가한 결과가 아니다.
    """
    compared = previous_relevant = reconfirmed = 0
    new_labels = dict(relevant=0, uncertain=0, irrelevant=0)
    for check in data["checks"]:
        reference = check["frozen_reference_labels"]
        for finding in check["new_analysis"]["findings"]:
            previous = reference[str(finding["bin_id"])]
            current = finding["scene_relevance"]
            compared += 1
            new_labels[current] += 1
            if previous == "relevant":
                previous_relevant += 1
                reconfirmed += current == "relevant"
    return dict(
        candidate_cases=len(data["checks"]),
        compared_bins=compared,
        previous_relevant=previous_relevant,
        previous_relevant_reconfirmed=reconfirmed,
        new_labels=new_labels,
        independent_ground_truth=False,
        same_input_protocol_verified=False,
    )


# 입력: 구간 ID별 AI 참조와 선택한 ID. 출력: 맞게 포함한 수(tp), 관련 참조 수, 선택 수.
# 불확실 참조는 모든 방식에서 동일하게 제외하며, 이는 치팅 분류의 TP가 아니다.
def metrics(labels, selected):
    if any(label not in ("relevant", "irrelevant", "uncertain") for label in labels.values()):
        raise ValueError("Invalid reference labels")
    if not set(selected) <= set(labels):
        raise ValueError("Selection outside reference bins")
    # 불확실은 분모에서 제외한다. 관련이 없는 구간을 선택한 수는 Precision 계산에 남는다.
    valid_ids = {bin_id for bin_id, label in labels.items() if label != "uncertain"}
    relevant_ids = {bin_id for bin_id in valid_ids if labels[bin_id] == "relevant"}
    chosen_ids = set(selected) & valid_ids
    return dict(
        tp=len(relevant_ids & chosen_ids),
        positive=len(relevant_ids),
        selected=len(chosen_ids),
        uncertain=len(labels) - len(valid_ids),
    )


# 출력: 기존 40경기 기록의 검색 지표와 사건별 개선·동률·악화 개수.
# 파일 해시·경기 중복·12초 예산을 확인하고 저장된 예상값과 재계산 결과를 대조한다.
def reproduce():
    manifest = json.loads((SAMPLE / "manifest.json").read_text())
    if sha(SAMPLE / "evaluation.json") != manifest["evaluation_sha256"]:
        raise ValueError("Evaluation snapshot checksum mismatch")
    if sha(SAMPLE / "reanalysis.json") != manifest["reanalysis_sha256"]:
        raise ValueError("Candidate reanalysis snapshot checksum mismatch")
    data = json.loads((SAMPLE / "evaluation.json").read_text())
    cases = data["cases"]
    if len(cases) != 40 or len({case_entry["match_id"] for case_entry in cases}) != 40:
        raise ValueError("Incomplete or duplicate evaluation cohort")
    scores = {}
    case_recall = {}
    for method in ["fixed", "random", "proposed"]:
        rows = []
        case_recall[method] = {}
        for case in cases:
            labels = {int(k): v for k, v in case["labels"].items()}
            ids = case["methods"][method]
            if len(ids) != len(set(ids)) or len(ids) * 2 != 12:
                raise ValueError("Invalid evaluation budget")
            row = metrics(labels, ids)
            rows.append(row)
            case_recall[method][case["case_id"]] = (
                row["tp"] / row["positive"] if row["positive"] else None
            )
        # 전체 사건의 구간 수를 먼저 합쳐 micro 지표를 계산한다.
        # Precision=선택 중 관련 비율, Recall=관련 중 선택 비율, F1=두 비율의 조화평균이다.
        true_positives = sum(r["tp"] for r in rows)
        relevant_count = sum(r["positive"] for r in rows)
        selected_count = sum(r["selected"] for r in rows)
        precision = true_positives / selected_count if selected_count else 0.0
        recall = true_positives / relevant_count if relevant_count else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        scores[method] = dict(
            cases=len(rows),
            true_positive=true_positives,
            gold_positive=relevant_count,
            selected_evaluable=selected_count,
            micro_precision=precision,
            micro_recall=recall,
            micro_f1=f1,
        )
        expected = data["expected_scores"][method]
        for key, value in scores[method].items():
            if abs(value - expected[key]) > 1e-10:
                raise ValueError("Submitted metric mismatch: " + method + "/" + key)
    # 관련 참조가 하나도 없는 사건은 사건별 Recall 차이에서 분리해 집계한다.
    differences = [
        case_recall["proposed"][cid] - r for cid, r in case_recall["fixed"].items() if r is not None
    ]
    return dict(
        status="REPRODUCED_AI_REFERENCE_ONLY",
        cases=40,
        scores=scores,
        paired=dict(
            improved=sum(d > 0 for d in differences),
            tied=sum(d == 0 for d in differences),
            worse=sum(d < 0 for d in differences),
            zero_relevant=40 - len(differences),
        ),
        independent_human_gold=False,
        human_efficiency="NOT_EVALUATED",
        reference_consistency=reference_consistency(
            json.loads((SAMPLE / "reanalysis.json").read_text())
        ),
        note="Recalculates exported labels and selections; original full-media 40-case collection is not bundled.",
    )
