# 제출본에서 사용하는 v7 검색 규칙이다. 학습 모델 대신 고정 가중치를 쓴다.
# 공격자의 장비·입력·좌표와 화면의 단순 통계로 후보를 점수화한다.
# 장비 보유는 투척 확정이 아니며, 화면 가림 후보는 연막 정답이 아니다.

"""The latest v7 rules only: attacker state, scene statistics, exact 12s selection."""

import itertools
from pathlib import Path
import numpy as np
from PIL import Image
from src.ingestion.schema import read_ticks

# 공개 원본의 장비 이름을 검색 특징에 대응시킨다. 장비 종류 자체가 치팅 증거는 아니다.
GUNS = frozenset(
    (
        "ssg08 awp mp7 mp9 p90 mp5sd mac10 ump45 elite p250 deagle cz75a revolver glock tec9 "
        "hkp2000 usp_silencer uspsilenceroff fiveseven m4a1_silencer ak47 aug galilar famas "
        "sg556 m4a1 mag7 xm1014 nova m249 negev"
    ).split()
)
UTILITY_STATES = {
    "smoke_state": frozenset(["smokegrenade"]),
    "fire_state": frozenset(["molotov", "incgrenade", "incendiarygrenade"]),
    "flash_state": frozenset(["flashbang"]),
    "he_state": frozenset(["hegrenade", "highexplosivegrenade"]),
}
# 기존 평가에 사용한 고정 가중치다. AI 설명이나 시연 결과를 보고 실행 중 바꾸지 않는다.
WEIGHTS = dict(
    smoke_state=2.5,
    fire_state=1.25,
    flash_state=0.625,
    he_state=0.625,
    spatial_firearm_attack=0.7,
    strong_obscuration=1.0,
    recency=0.5,
)


# 입력: 원본 영상의 킬 시각(초). 출력: 검색할 2초 구간들의 시작·종료 시각.
# 사건 30초 전부터 6초 전까지를 살펴보고, 사건 주변 영상과 검색 영역을 분리한다.
def bins(anchor):
    start, stop = (max(0.0, anchor - 30.0), max(0.0, anchor - 6.0))
    return [(start + 2 * i, start + 2 * i + 2) for i in range(int((stop - start + 1e-09) // 2))]


# 입력: 시작·종료 시각 쌍의 목록. 출력: 겹치거나 맞닿은 구간을 합친 목록.
# 연속 선택된 2초 조각은 하나의 영상으로 내보내기 위해 합친다.
def merge(windows):
    out = []
    for start, end in sorted(windows):
        if end <= start:
            raise ValueError("Invalid interval")
        if out and start <= out[-1][1] + 1e-09:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


# 입력: 전체 후보 구간과 선택한 bin_id. 출력: 영상으로 내보낼 연속 구간 목록.
def intervals(candidates, ids):
    return merge([(b["start_s"], b["end_s"]) for b in candidates if b["bin_id"] in ids])


# 입력: 추출한 사진 경로. 출력: 저질감 가림 후보 비율과 밝은 화면 후보.
# 중앙 영역을 3×5 조각으로 나누며, 통계값만으로 연막·섬광을 확정하지 않는다.
def screen_statistics(path):
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=float)
    height, width, _ = rgb.shape
    # 화면 가장자리의 HUD 영향을 줄이기 위해 중앙 윗부분만 통계에 사용한다.
    rgb = rgb[int(height * 0.1) : int(height * 0.65), int(width * 0.15) : int(width * 0.85)]
    gray = rgb.mean(axis=2)
    low_texture = []
    # 낮은 경계 강도·색 변화·채도인 조각의 비율을 가림 후보로 계산한다.
    for row_tiles in np.array_split(rgb, 3, axis=0):
        for patch in np.array_split(row_tiles, 5, axis=1):
            gray_patch = patch.mean(axis=2)
            edge = (
                abs(np.diff(gray_patch, axis=0)).mean() + abs(np.diff(gray_patch, axis=1)).mean()
            ) / 2
            saturation = ((patch.max(axis=2) - patch.min(axis=2)) / (patch.max(axis=2) + 1)).mean()
            low_texture.append(
                float(
                    edge < 4
                    and gray_patch.std() < 22
                    and (45 < gray_patch.mean() < 220)
                    and (saturation < 0.32)
                )
            )
    return dict(
        partial_obscuration=float(np.mean(low_texture)),
        flash=float(gray.mean() > 200 and gray.std() < 35),
    )


# 입력: 2초 구간별 점수. 출력: 선택된 구간의 인덱스.
# 서로 겹치지 않는 4초 블록 3개를 전수 비교해 총 12초의 점수 합을 최대화한다.
# 점수가 같으면 더 최근 구간의 인덱스 합을 우선하며, 후보가 6개 미만이면 모두 반환한다.
def exact_blocks(scores):
    candidate_count = len(scores)
    if candidate_count < 6:
        return list(range(candidate_count))
    choices = []
    # 2초 조각 두 개를 한 블록으로 보고, 3블록의 모든 시작 위치 조합을 검사한다.
    for block_starts in itertools.combinations(range(candidate_count - 1), 3):
        selected_ids = sorted(
            (bin_index for start in block_starts for bin_index in (start, start + 1))
        )
        if len(set(selected_ids)) != 6:
            continue
        choices.append(
            (
                sum((scores[bin_index] for bin_index in selected_ids)),
                sum(selected_ids),
                selected_ids,
            )
        )
    # 최근성 동점 규칙까지 고정해 같은 입력이면 같은 선택이 나오게 한다.
    return max(choices, key=lambda x: (x[0], x[1]))[2]


# 입력: 한 구간의 살아 있는 공격자 틱 자료. 출력: 장비 보유·총기 공격 입력의 비율.
# 입력 비율은 행동 후보일 뿐 실제 발사·투척·명중의 시각적 증거가 아니다.
def weapon_features(ticks):
    weapon = ticks.input_weapon.astype("string").fillna("")
    attack = ticks.active.apply(lambda x: "attack" in x)
    out = {
        k: float(weapon.isin(names).mean()) if len(ticks) else 0.0
        for k, names in UTILITY_STATES.items()
    }
    out["firearm_attack"] = float((attack & weapon.isin(GUNS)).mean()) if len(ticks) else 0.0
    return out


# 입력: 사건 package와 프레임 폴더. 출력: 각 후보 구간의 특징 딕셔너리 목록.
# 공격자 자신의 사건 위치와의 거리만 사용하며 피해자 위치를 검색 단서로 쓰지 않는다.
def features(package, frame_dir):
    attacker_ticks = read_ticks(package["attacker_ticks"])
    event_row = attacker_ticks.iloc[
        (attacker_ticks.t - package["case"]["event_seconds"]).abs().argmin()
    ]
    candidate_rows = []
    for candidate in package["bins"]:
        window_ticks = attacker_ticks[
            (attacker_ticks.t >= candidate["start_s"])
            & (attacker_ticks.t < candidate["end_s"])
            & attacker_ticks.is_alive
        ]
        # 공격자의 사건 위치에 얼마나 가까웠는지를 게임 좌표 거리로 계산한다.
        distance = np.sqrt(
            (window_ticks.x - event_row.x) ** 2
            + (window_ticks.y - event_row.y) ** 2
            + (window_ticks.z - event_row.z) ** 2
        )
        # 1200은 거리 감쇠의 척도다. 미터나 정답 관련성 확률을 의미하지 않는다.
        scene_proximity = float(np.exp(-distance.median() / 1200)) if len(window_ticks) else 0.0
        frame_statistics = [
            screen_statistics(Path(frame_dir) / f"frame_{candidate['bin_id']*4+frame_index:03}.jpg")
            for frame_index in range(4)
        ]
        window_features = weapon_features(window_ticks)
        # 총기 입력에 공간 근접성을 곱하고, 가림 후보 비율이 0.8을 넘는 부분만 반영한다.
        # 최근성은 검색 구간 안에서 0보다 크고 1 이하인 순서 비율로 계산한다.
        window_features.update(
            anchor_scene_proximity_candidate=scene_proximity,
            spatial_firearm_attack=window_features["firearm_attack"] * scene_proximity,
            strong_obscuration=max(
                0.0,
                (float(np.mean([v["partial_obscuration"] for v in frame_statistics])) - 0.8) / 0.2,
            ),
            recency=(candidate["bin_id"] + 1) / len(package["bins"]),
        )
        candidate_rows.append(
            dict(
                bin_id=candidate["bin_id"],
                start_s=candidate["start_s"],
                end_s=candidate["end_s"],
                features=window_features,
            )
        )
    return candidate_rows


# 입력: 구간별 특징 목록. 출력: 선택한 구간 인덱스와 각 구간의 점수.
# 고정 가중치의 합으로 계산하므로 신경망 학습이나 AI 호출은 일어나지 않는다.
def predict(rows):
    scores = [
        sum(candidate["features"][key] * weight for key, weight in WEIGHTS.items())
        for candidate in rows
    ]
    return exact_blocks(scores), scores
