# 고정한 OpenCS2 원본에서 실제 확인한 필드와 시간축을 검사한다.
# 다른 사람의 POV나 잘못 맞춘 영상 시각을 근거로 사용하지 않도록 먼저 실패시킨다.

"""Strict adapter for the observed OpenCS2 revision."""

import math
import re
import numpy as np
import pyarrow.parquet as pq

# 사건과 POV를 연결할 공통 키와 실제 원본에서 필요한 필드를 명시한다.
KEYS = ["match_id", "map_name", "round"]
KILL_REQUIRED = KEYS + [
    "kill_id",
    "tick",
    "event_seconds",
    "attacker_player_slot",
    "victim_player_slot",
    "through_smoke",
    "wallbang",
]
POV_REQUIRED = KEYS + [
    "player_slot",
    "media_id",
    "duration_s",
    "preview_video",
    "ticks_parquet_path",
    "capture_start_tick",
    "capture_end_tick",
    "preview_video_bytes",
    "death_tick",
]
TICK_REQUIRED = ["tick", "t", "active", "yaw", "pitch", "x", "y", "z", "is_alive"]


# 입력: 원본 경로, 사건, 플레이어 슬롯. 출력: 일치한 경기·맵·라운드 키.
# 경로에 기록된 신원이 사건의 공격자와 다르면 다른 POV일 수 있으므로 중단한다.
def validate_asset_identity(path, case, slot):
    from caer.ingestion.source import relative_path

    rel = relative_path(path)
    match = re.fullmatch(
        r"rounds/match_id=(\d+)/map_name=([^/]+)/round=(\d+)/player=(\d+)/(ticks\.parquet|video\.preview\.mp4)",
        rel,
    )
    if not match:
        raise ValueError("Unsupported POV asset layout")
    found = (int(match[1]), match[2], int(match[3]), int(match[4]))
    expected = (case["match_id"], case["map_name"], case["round"], slot)
    if found != expected:
        raise ValueError(f"POV asset identity mismatch: {found} != {expected}")
    return found[:3]


# 입력: 실제 필드 목록과 필수 필드 목록. 누락된 필드가 있으면 예외를 발생시킨다.
def require_columns(columns, required):
    missing = set(required) - set(columns)
    if missing:
        raise ValueError(f"Missing actual source columns: {sorted(missing)}")


# 입력: 공격자 틱 Parquet 경로. 출력: 시각순으로 검증된 DataFrame.
# 빈 자료, 중복 틱, 역순 시각, 유한하지 않은 시각은 허용하지 않는다.
def read_ticks(path):
    # ParquetFile avoids Hive path inference (round=03 etc) creating fake fields.
    table = pq.ParquetFile(path).read()
    require_columns(table.column_names, TICK_REQUIRED)
    df = table.to_pandas()
    if df.empty or df.tick.duplicated().any() or not df.tick.is_monotonic_increasing:
        raise ValueError("Empty, duplicate or unordered ticks")
    if not np.isfinite(df.t).all() or not df.t.is_monotonic_increasing:
        raise ValueError("Invalid tick time axis")
    return df


# 입력: 사건, 틱 자료, 영상 길이, 허용 오차. 출력: 수치 동기화 검사 기록.
# 사건의 정확한 틱이 영상의 사건 시각과 맞아야 하며, 앞선 30초 맥락도 존재해야 한다.
def validate_time(case, ticks, duration, tolerance=1 / 32):
    anchor = float(case["event_seconds"])
    if not math.isfinite(duration) or not 0 <= anchor < duration:
        raise ValueError("Event outside actual video")
    # 가장 가까운 틱으로 대신하지 않고 킬의 정확한 틱 한 행을 요구한다.
    event_rows = ticks[ticks.tick == int(case["tick"])]
    if len(event_rows) != 1:
        raise ValueError("Exact event tick missing in attacker POV")
    tick_t = float(event_rows.iloc[0].t)
    delta = abs(tick_t - anchor)
    if delta > tolerance:
        raise ValueError(f"Time alignment failed: {delta} > {tolerance}")
    if float(ticks.t.max()) > duration + tolerance:
        raise ValueError("Tick timeline longer than actual video")
    if float(ticks.t.min()) > max(0, anchor - 30) + tolerance:
        raise ValueError("Prior context unavailable")
    return dict(
        status="PASS_NUMERIC",
        event_tick=int(case["tick"]),
        event_seconds=anchor,
        tick_t=tick_t,
        absolute_error_s=delta,
        tolerance_s=tolerance,
        tick_min_s=float(ticks.t.min()),
        tick_max_s=float(ticks.t.max()),
        actual_video_duration_s=duration,
    )
