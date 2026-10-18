# 킬 이벤트를 해당 공격자의 1인칭 영상(POV)과 연결하고 검토 후보를 선정한다.
# 연막 관통·벽 관통이라는 조건은 검토할 이유이며 치팅 정답 라벨이 아니다.

import hashlib
import json
import duckdb
import pyarrow.parquet as pq
from caer.ingestion.schema import require_columns, KILL_REQUIRED, POV_REQUIRED


# 입력: 경기·맵·라운드·킬 ID가 있는 사건 행. 출력: 재현 가능한 20자리 사건 식별자.
# 같은 사건을 다시 처리해도 같은 ID가 나오도록 정해진 키 순서로 해시를 만든다.
def case_id(row):
    identity = [row[k] for k in ["match_id", "map_name", "round", "kill_id"]]
    return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()[:20]


# 입력: 킬·POV 메타데이터 경로와 개수 제한. 출력: 검토 후보 사건 목록.
# 공격자와 피해자 POV의 존재를 확인하되 이후 영상 분석에는 공격자 자료만 전달한다.
def mine(kills_path, pov_path, limit=1):
    for path, fields in [(kills_path, KILL_REQUIRED), (pov_path, POV_REQUIRED)]:
        require_columns(pq.read_schema(path).names, fields)
    con = duckdb.connect()
    con.read_parquet(str(kills_path)).create_view("kills")
    con.read_parquet(str(pov_path)).create_view("povs")
    if con.sql(
        "SELECT count(*) FROM (SELECT match_id,map_name,round,player_slot,count(*) n FROM povs GROUP BY ALL HAVING n>1)"
    ).fetchone()[0]:
        raise ValueError("Ambiguous POV identity")
    # 연막·벽 관통이며 사건 30초 이전 맥락과 이후 6초 영상이 있는 사건만 고른다.
    # 경기별 첫 후보를 먼저 나열해 한 경기의 사건만 앞에 몰리는 것을 줄인다.
    # 피해자 메타데이터의 존재 확인은 수행하지만 피해자 틱·영상은 검색·AI 입력으로 쓰지 않는다.
    result = con.execute(
        """SELECT k.*, struct_pack(
        media_id := p.media_id, player_slot := p.player_slot, duration_s := p.duration_s,
        preview_video := p.preview_video, ticks_parquet_path := p.ticks_parquet_path,
        preview_video_bytes := p.preview_video_bytes) AS pov,
        struct_pack(media_id := v.media_id, player_slot := v.player_slot,
        ticks_parquet_path := v.ticks_parquet_path, death_tick := v.death_tick) AS victim_pov
        FROM kills k JOIN povs p ON k.match_id=p.match_id AND k.map_name=p.map_name
        AND k.round=p.round AND k.attacker_player_slot=p.player_slot
        JOIN povs v ON k.match_id=v.match_id AND k.map_name=v.map_name
        AND k.round=v.round AND k.victim_player_slot=v.player_slot
        WHERE (k.through_smoke OR k.wallbang) AND k.event_seconds >= 30
        AND p.duration_s >= k.event_seconds+6
        ORDER BY row_number() OVER (PARTITION BY k.match_id ORDER BY k.map_name,k.round,k.kill_id),
        k.match_id,k.map_name,k.round,k.kill_id LIMIT ?""",
        [limit],
    )
    names = [d[0] for d in result.description]
    rows = [dict(zip(names, r)) for r in result.fetchall()]
    for row in rows:
        row["case_id"] = case_id(row)
    con.close()
    return rows
