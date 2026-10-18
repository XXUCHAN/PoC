# 제출본에 담긴 실제 영상·프레임·AI 실행 기록을 이식 가능한 경로로 불러온다.
# 해시는 파일 변경을 확인할 뿐, AI 설명이 사실이라는 것을 보증하지 않는다.

"""Portable recorded samples; checksums validate the export, not semantic truth."""

import json
from pathlib import Path
from src.config import SAMPLE
from src.ingestion.io import sha


# 입력: 샘플 폴더와 상대 경로. 출력: 해당 폴더 안의 절대 경로.
# 경로를 정규화한 뒤 폴더 밖으로 벗어나는 참조를 거부한다.
def inside(folder, value):
    path = (folder / value).resolve()
    if not path.is_relative_to(folder.resolve()):
        raise ValueError("Sample path escapes its directory")
    return path


# 입력: 사례 폴더. 출력: 파일 목록과 해시를 담은 manifest.
# 목록에 있는 모든 파일의 실제 내용이 제출 당시 해시와 같은지 검사한다.
def verify_snapshot(folder):
    manifest = json.loads((folder / "manifest.json").read_text())
    for rel, expected in manifest["files"].items():
        if sha(inside(folder, rel)) != expected:
            raise ValueError("Sample checksum mismatch: " + rel)
    return manifest


# 출력: 검사에 통과한 제출 사례 목록.
# 저장 파일의 상대 경로는 보존하고, 메모리에서만 현재 위치의 절대 경로로 바꾼다.
def load_samples():
    out = []
    # 루트 목록과 하위 manifest 해시를 함께 확인해 사례 추가·누락도 감지한다.
    root = json.loads((SAMPLE / "manifest.json").read_text())
    paths = sorted(SAMPLE.glob("*/case.json"))
    if {package.parent.name for package in paths} != set(root["sample_manifests"]):
        raise ValueError("Sample collection mismatch")
    for path in paths:
        if sha(path.parent / "manifest.json") != root["sample_manifests"][path.parent.name]:
            raise ValueError("Sample manifest mismatch")
        folder = path.parent
        verify_snapshot(folder)
        package = json.loads(path.read_text())
        package["sample_dir"] = str(folder.resolve())
        package["package_path"] = str(path.resolve())
        for clip in [package["anchor"], *package["context"], *package.get("fixed_context", [])]:
            clip["path"] = str(inside(folder, clip["path"]))
        for frame in package["frames"]:
            frame["path"] = str(inside(folder, frame["path"]))
        out.append(package)
    return out


# 입력: 불러온 샘플 package. 출력: 실제 저장 분석과 연결된 근거 사진.
# 두 AI 응답의 인용과 구간 시각을 검증한 뒤 UI가 사용할 evidence를 구성한다.
def load_sample_analysis(package):
    from src.analysis.visual import verify_inputs, validate_report

    folder = Path(package["sample_dir"])
    verify_snapshot(folder)
    frames = verify_inputs(package)
    report_path = folder / "analysis.json"
    report = validate_report(package, json.loads(report_path.read_text()), frames)
    report["report_path"] = str(report_path.resolve())
    return report
