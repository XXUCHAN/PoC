# FFprobe로 실제 영상 길이·프레임 간격을 읽고 FFmpeg로 구간을 추출한다.
# 메타데이터의 예상 길이만 믿지 않고 출력 파일을 다시 확인한다.

import json
import subprocess
from pathlib import Path
from fractions import Fraction


# 입력: 미디어 파일 경로. 출력: FFprobe가 읽은 스트림·컨테이너 메타데이터.
# 외부 명령 실패는 그대로 전달해 깨진 영상을 정상 자료로 취급하지 않는다.
def probe(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


# 입력: 영상 경로. 출력: 비디오 스트림 기준의 실제 길이(초).
def duration(path):
    streams = probe(path)["streams"]
    video = next(s for s in streams if s["codec_type"] == "video")
    return float(video["duration"])


# 입력: 영상 경로. 출력: 평균 프레임률의 역수인 한 프레임 시간(초).
# 분수 형태 프레임률을 그대로 읽어 1프레임 단위의 오차를 계산한다.
def frame_interval(path):
    video = next(s for s in probe(path)["streams"] if s["codec_type"] == "video")
    return 1 / float(Fraction(video["avg_frame_rate"]))


# 입력: 원본 영상, 시작·종료 시각, 출력 경로. 출력: 생성 영상의 시각·길이·명령 기록.
# 실제 출력 길이가 요청 길이에서 1프레임보다 많이 벗어나면 실패한다.
def export(source, start, end, target):
    tolerance = frame_interval(source)
    if start < 0 or end <= start or end > duration(source) + tolerance:
        raise ValueError("Invalid clip bounds")
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    # 시작 시각과 길이로 재인코딩하며 영상 타임스탬프를 0에서 시작시킨다.
    # 오디오는 있으면 포함하지만 AI 분석에는 소리를 전달하지 않는다.
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-ss",
        str(start),
        "-i",
        str(source),
        "-t",
        str(end - start),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-vf",
        "setpts=PTS-STARTPTS",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(target),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    # 요청한 12초와 실제 인코딩된 재생 길이가 같은지 출력 파일에서 다시 확인한다.
    actual = duration(target)
    if abs(actual - (end - start)) > tolerance + 1e-5:
        raise ValueError(f"Exported duration mismatch: {actual}")
    return dict(
        start_s=start,
        end_s=end,
        path=str(target.resolve()),
        actual_duration_s=actual,
        frame_tolerance_s=tolerance,
        command=command,
    )
