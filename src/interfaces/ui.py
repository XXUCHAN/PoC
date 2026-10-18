# 제출 시연 화면이다. 사건·고정 영상·자동 검색 영상을 비교하고 근거를 설명한다.
# 기록된 실제 분석은 재사용임을 표시하며, 검색 수치와 치팅 판정 정확도를 구분한다.
# Streamlit은 선택이 바뀔 때 파일 전체를 다시 실행한다.

"""Submission demonstration: event, equal-budget comparison, cited new context."""

import streamlit as st
from src.interfaces import workflow as demo
from src import pipeline
from src.analysis.visual import latest_analysis
from src.evaluation.reproduce import reproduce

st.set_page_config(
    page_title="PoC · 이전 행동과 근거 확인", layout="wide", initial_sidebar_state="collapsed"
)
st.title("킬 이전의 행동 후보를 근거로 검토합니다")
st.caption(
    "PoC · 킬 30초 전~6초 전의 시각적 행동 후보 검색 → AI 설명·연결 판단 → 사람이 근거 확인"
)
# 준비된 두 사례와 로컬에서 새로 생성한 사건을 읽는다. 기본 사례는 이전 행동 추가를 보여준다.
packages = pipeline.load_packages()
if not packages:
    st.info("시연 사례를 준비해 주세요.")
    st.stop()
by_id = {p["case"]["case_id"]: p for p in packages}
ids = sorted(by_id, key=lambda cid: (cid != demo.DEFAULT_CASE, cid))


# 입력: 사건 ID. 출력: 각 사례의 시연 목적이 드러나는 선택 상자 문구.
def case_label(cid):
    name = by_id[cid]["case"]["map_name"].removeprefix("de_").title()
    if cid == demo.DEFAULT_CASE:
        return "① 고정 영상에 없던 이전 행동 찾기 · " + name
    if cid == "9ef21e25146cb3c4fd25":
        return "② AI 설명을 실제 근거로 확인하기 · " + name
    return name + " · Round " + str(by_id[cid]["case"]["round"])


case_id = st.selectbox("시연 사례", ids, format_func=case_label)
package = by_id[case_id]
try:
    # 저장된 실제 분석은 즉시 불러온다. 새 생성 사건에 분석이 없을 때만 실행 버튼을 보인다.
    cached = latest_analysis(package)
    if cached is None:
        st.info("이 사건은 새 AI 분석이 필요합니다.")
        if not st.button("사건 분석", type="primary"):
            st.stop()
    result = demo.run_case(package)
except Exception as exc:
    st.error(f"사건을 준비하지 못했습니다: {exc}")
    st.stop()
report = result["report"]
# 검색 결과 중 고정 방식에 없는 2초 구간을 구한다. 새 구간이라는 사실과 관련성 확정은 구분한다.
new_ids = set(package["methods"]["proposed"]) - set(package["methods"]["fixed"])
interpretation = result["interpretation"]
finding = demo.featured_finding(report, package)
review_row = next(row for row in interpretation["rows"] if row["bin_id"] == finding["bin_id"])
relation_labels = {"relevant": "관련 후보", "uncertain": "불확실", "irrelevant": "비관련"}
review_labels = {
    "supported": "설명이 사진에 부합한다고 응답",
    "uncertain": "설명 근거 불확실",
    "unsupported": "설명 근거 미지원",
}
if interpretation["selection_basis"] == "recency_only":
    st.warning(
        "선택된 구간에는 검색 규칙의 행동·가림 단서가 없어 최근성에 따른 영상을 제공합니다. "
        "행동이 없었다는 뜻은 아니며, 의미 있는 맥락을 발견한 결과로 해석하지 않습니다."
    )
elif interpretation["state"] == "model_linked_candidate":
    st.info(
        "고정 영상에 없는 행동을 AI가 사건과 연결된 후보로 분류했습니다. 아래에서 두 장면의 근거를 확인하세요. 정상 플레이나 치팅 여부를 확인한 결과는 아닙니다."
    )
elif interpretation["state"] == "same_selection":
    st.info(
        "두 방식의 선택이 같습니다. 이 사례에서는 검색 차이가 아니라 AI 설명과 인용 근거를 확인합니다."
    )
else:
    st.info(
        "고정 영상 밖의 이전 행동 후보를 추가로 제시합니다. 사건에 도움이 되는 정보인지, 어떤 영향을 줬는지는 아직 확인되지 않았습니다."
    )
st.caption(
    "선택된 구간이라는 사실은 관련성을 뜻하지 않습니다. 설명 재검토와 사건 연결 판단을 아래에서 따로 표시합니다."
)


# 입력: 영상 조각 목록. 출력: 원본 영상의 시작·종료 시각을 연결한 표시 문자열.
def times(segments):
    return " / ".join(f"{s['start_s']:.1f}–{s['end_s']:.1f}초" for s in segments)


# 세 영상을 나란히 표시한다. 원본 시각과 이어 붙인 영상의 재생 시각은 서로 다르다.
cols = st.columns(3)
with cols[0]:
    st.subheader("1. 사건 영상")
    c = package["case"]
    st.write(
        f"{c['map_name'].removeprefix('de_').title()} · {c['round']}라운드 · "
        + ("연막 관통 킬" if c["through_smoke"] else "벽 관통 킬")
    )
    st.video(package["anchor"]["path"])
    st.caption(f"킬 시각 {c['event_seconds']:.1f}초 · 전후 6초씩")
with cols[1]:
    st.subheader("2. 고정 방식")
    st.write("사건 영상 앞의 12초를 연속 선택")
    st.video(result["fixed"]["path"])
    st.caption("원본 " + times(result["fixed"]["segments"]))
with cols[2]:
    st.subheader("3. 자동 검색")
    st.write(
        "행동 단서 없음 · 최근 구간 대체 제공"
        if interpretation["selection_basis"] == "recency_only"
        else "행동 후보 우선 선택 · 같은 추가 영상 12초"
    )
    st.video(result["context"]["path"])
    st.caption("원본 " + times(result["context"]["segments"]) + " · 시간순 연결")

# 실제 보고서의 강조 설명으로 시각 비교·관찰·불확실성·재검토를 순서대로 설명한다.
additional = finding["bin_id"] in new_ids
st.subheader(
    "4. 이전 행동을 찾아서 무엇을 알 수 있나?"
    if new_ids
    else "4. AI 설명이 맞는지 어떻게 확인하나?"
)
event = package["case"]["event_seconds"]
if additional:
    st.write(
        f"킬은 원본 영상의 {event:.1f}초에 발생했습니다. 고정 방식은 그 앞의 {times(result['fixed']['segments'])}만 보여주므로, "
        f"{finding['start_s']:.1f}–{finding['end_s']:.1f}초의 아래 행동은 포함하지 않습니다."
    )
    st.write(
        "자동 검색은 더 이전까지 살펴보고 이 장면을 골랐습니다. 검토자는 킬 순간뿐 아니라, 그 전에 어떤 행동이 있었는지도 확인할 수 있습니다."
    )
elif not new_ids:
    st.write(
        "이 사건에서는 두 방식이 같은 이전 영상을 골랐습니다. 따라서 여기서는 검색의 차이가 아니라, AI가 한 설명을 실제 영상 근거로 확인하는 과정을 봅니다."
    )
else:
    st.write(
        "아래 설명은 두 방식이 공통으로 선택한 구간입니다. 고정 영상 밖의 추가 구간 판단은 아래 전체 목록에서 확인합니다."
    )
text, image = st.columns([1.2, 1])


# 입력: 저장된 AI 설명 문자열. 출력: 화면용 용어로 풀어 쓴 문자열.
# 원본 AI 응답은 바꾸지 않고 앵커·프레임 ID를 독자가 이해할 장소·시각 표현으로 바꾼다.
def plain(value):
    value = (
        value.replace("앵커 계단 통로", "킬이 일어난 계단 통로")
        .replace("앵커", "킬 장면")
        .replace("표본", "추출한 사진")
    )
    for e in finding["evidence"]:
        value = value.replace(e["frame_id"], f"원본 {e['time_s']:.2f}초 사진")
    return value


with text:
    st.markdown("**① AI는 사진에서 어떤 행동을 관찰했나?**")
    st.markdown(
        f"원본 **{finding['start_s']:.1f}–{finding['end_s']:.1f}초** · 킬 약 {event-(finding['start_s']+finding['end_s'])/2:.0f}초 전"
    )
    st.write(plain(finding["observation"]))
    st.markdown(f"**② 사건과의 연결: {relation_labels[review_row['scene_relation']]} · AI 판단**")
    st.write(plain(finding["scene_link"]))
    st.markdown("**③ 무엇은 아직 알 수 없나?**")
    st.write(plain(finding["uncertainty"]) or "샘플 프레임 밖의 행동은 확인할 수 없습니다.")
    if review_row["scene_relation"] == "uncertain":
        st.info(
            "여기서 확인한 것은 이전 행동의 모습입니다. 그 행동 때문에 킬이 가능했는지, 상대를 미리 알았는지는 이 자료만으로 판단할 수 없습니다."
        )
    elif review_row["scene_relation"] == "relevant":
        st.info(
            "AI는 킬 장소와 연결되는 행동 후보로 보았습니다. 같은 상대인지, 맞혔는지, 이 행동이 킬의 원인이었는지는 확인하지 않았습니다."
        )
    st.markdown("**④ 설명 재검토와 사건 관련성은 별개입니다**")
    st.caption("설명 재검토: " + review_labels[finding["crosscheck"]["verdict"]])
    if finding["crosscheck"]["verdict"] == "supported":
        st.write(
            "같은 모델의 별도 호출은 이 설명이 사진에 부합한다고 답했습니다. ‘킬과의 연결을 모른다’는 설명도 부합 판정을 받을 수 있습니다. 이것을 사건 관련성 확인이나 독립 정답으로 해석하지 않습니다."
        )
    else:
        st.warning(
            "별도 AI 재검토에서도 설명을 확정하지 못했습니다. 원본 영상을 직접 확인해야 합니다."
        )
with image:
    st.markdown("**설명의 근거가 된 실제 프레임**")
    preferred = package.get("presentation", {}).get("evidence_frame_id")
    evidence = finding["evidence"]
    # 시연에 지정된 사진은 AI가 인용한 목록 안에서만 고른다. 가능하면 앞뒤 두 사진을 함께 보인다.
    if preferred:
        own = [e for e in evidence if e["bin_id"] == finding["bin_id"]]
        chosen = sorted(own, key=lambda e: e["time_s"])[:2]
        if preferred not in {e["frame_id"] for e in chosen}:
            chosen = chosen[:1] + [next(e for e in evidence if e["frame_id"] == preferred)]
    else:
        chosen = evidence[:2]
    for e in chosen:
        role = "킬 주변 장면" if e["bin_id"] is None else "이전 행동"
        st.image(
            e["path"],
            caption=f"{role} · 원본 {e['time_s']:.2f}초 · AI가 실제 인용한 프레임",
            width="stretch",
        )
    st.caption(
        "시각은 모두 원본 영상 기준입니다. 자동 검색 영상은 여러 구간을 이어 붙였으므로 재생기의 시각과 다릅니다."
    )

st.markdown("**선택된 모든 구간의 모델 판단**")
findings_by_id = {item["bin_id"]: item for item in report["findings"]}
st.table(
    [
        {
            "원본 시각": f"{findings_by_id[row['bin_id']]['start_s']:.1f}–{findings_by_id[row['bin_id']]['end_s']:.1f}초",
            "고정 영상에 없는 선택": "예" if row["additional"] else "아니요",
            "사건 연결 · AI 판단": relation_labels[row["scene_relation"]],
            "설명 재검토 · AI 응답": review_labels[row["description_review"]],
        }
        for row in interpretation["rows"]
    ]
)

st.divider()
st.subheader("5. 이번 PoC에서 확인한 범위")
st.write(
    "이 PoC는 같은 12초 분량에서 다른 이전 행동 후보를 제시하고, 실제 사진 인용과 사건 연결의 불확실성을 함께 표시하는 흐름을 보여줍니다. 관련성 정확도나 사람의 치팅 오탐률 감소를 입증한 실험은 아닙니다."
)
st.markdown("**보조 기록: 기존 AI 참조로 계산한 40건의 검색 비교**")
try:
    evaluation = reproduce()
    fixed = evaluation["scores"]["fixed"]
    proposed = evaluation["scores"]["proposed"]
    st.table(
        [
            {
                "방식": name,
                "기존 관련 표시 중 선택": f"{score['true_positive']} / {score['gold_positive']}구간",
                "기존 참조 기준 포함 비율": f"{score['micro_recall']:.1%}",
            }
            for name, score in [("고정 12초", fixed), ("행동 후보 검색 12초", proposed)]
        ]
    )
    consistency = evaluation["reference_consistency"]
    st.warning(
        f"다시 확인한 후보 {consistency['candidate_cases']}건·{consistency['compared_bins']}구간에서 기존에는 {consistency['previous_relevant']}구간이 관련으로 표시됐지만, "
        f"새 분석에서 관련으로 재확인된 구간은 {consistency['previous_relevant_reconfirmed']}개였습니다. "
        "입력 범위나 판단 절차의 차이도 있을 수 있어 어느 쪽을 정답으로 확정할 수 없습니다. 따라서 위 숫자는 기존 기록의 재계산이며 성능 개선의 확증으로 사용하지 않습니다."
    )
except (ValueError, OSError, KeyError) as exc:
    st.error(f"평가 자료를 검증하지 못했습니다: {exc}")
st.caption(
    "40건은 탐색적 비교이고 시연 사례는 결과를 본 뒤 골랐습니다. 정상·치팅 정답과 사람의 판정 실험은 없습니다."
)
if result["reused_analysis"]:
    st.caption(
        "실제 모델로 실행한 저장 분석을 불러옵니다. 사례를 고를 때 새 모델을 호출하지 않습니다."
    )
st.caption(
    "장기 가설: 근거가 있는 이전 맥락이 사람의 치팅 오탐을 줄일 수 있는가? 현재는 이 가설을 시험할 검토 도구를 구현한 단계입니다."
)
