# 공격자 영상에서 일정한 간격으로 사진을 추출하고 AI 입력용 묶음 이미지를 만든다.
# 프레임 ID와 원본 시각은 프로그램이 정하며 AI가 임의로 만들어내지 않는다.

import subprocess
from pathlib import Path
from PIL import Image, ImageDraw
from caer.media.clips import frame_interval
from caer.ingestion.io import sha, write_json


# 입력: 사건 package와 저장 폴더. 출력: 프레임 ID·구간 ID·원본 시각·경로·해시 목록.
# 각 2초 구간에서 4장(2fps), 킬 주변에서 4장을 공격자 영상으로부터 추출한다.
def sample_frames(package, dest):
    """Uniform attacker-only frames, with machine-owned IDs and absolute video times."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    # 각 2초 조각의 0.25·0.75·1.25·1.75초에서 추출해 경계에만 치우치지 않게 한다.
    spec = [
        (f"b{b['bin_id']}_f{j}", b["bin_id"], b["start_s"] + offset)
        for b in package["bins"]
        for j, offset in enumerate((0.25, 0.75, 1.25, 1.75))
    ]
    length = package["synchronization"]["actual_video_duration_s"]
    # 킬 전후의 -1·-0.5·0·+0.5초를 추가하고 영상 범위 안으로 제한한다.
    spec += [
        (
            f"anchor_f{j}",
            None,
            min(
                max(0.0, package["case"]["event_seconds"] + offset),
                length - frame_interval(package["source_video"]),
            ),
        )
        for j, offset in enumerate((-1.0, -0.5, 0.0, 0.5))
    ]
    frames = []
    for index, (fid, bid, t) in enumerate(spec):
        path = dest / f"frame_{index:03}.jpg"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-ss",
                str(t),
                "-i",
                package["source_video"],
                "-frames:v",
                "1",
                "-vf",
                "scale=480:270",
                str(path),
            ],
            check=True,
            capture_output=True,
        )
        frames.append(
            dict(frame_id=fid, bin_id=bid, time_s=t, path=str(path.resolve()), sha256=sha(path))
        )
    write_json(dest / "frames.json", frames)
    return frames


# 입력: 검증된 프레임 목록과 저장 폴더. 출력: AI에 첨부할 묶음 이미지 경로 목록.
# 4열에 최대 8장씩 배치하고 ID·원본 시각을 사진 위에 적어 인용을 추적할 수 있게 한다.
def contact_sheets(frames, dest):
    """Two bins per sheet, keeping each image readable and citations unambiguous."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    groups = [frames[i : i + 8] for i in range(0, len(frames), 8)]
    paths = []
    for n, group in enumerate(groups):
        # 원본 추출 사진은 480×270이며, 위쪽 26픽셀은 ID·시각 표시 공간이다.
        sheet = Image.new("RGB", (1920, 296 * ((len(group) + 3) // 4)), (15, 15, 15))
        draw = ImageDraw.Draw(sheet)
        for j, frame in enumerate(group):
            x = j % 4 * 480
            y = j // 4 * 296
            with Image.open(frame["path"]) as img:
                sheet.paste(img.convert("RGB"), (x, y + 26))
            draw.text((x + 4, y + 5), f"{frame['frame_id']} | {frame['time_s']:.3f}s", fill="white")
        path = dest / f"sheet_{n}.jpg"
        sheet.save(path, quality=92)
        paths.append(str(path.resolve()))
    return paths
