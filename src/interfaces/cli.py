# 수집·분석·검증·평가 재계산에 필요한 최소 명령을 제공한다.
# UI용 모델 설정 메뉴를 추가하지 않고 새 분석도 고정 모델을 사용한다.

"""Essential collection, analysis, verification and result reproduction commands."""

import argparse
import json


# 명령행 인자를 해석하고 해당 파이프라인 함수를 호출한 뒤 JSON으로 결과를 출력한다.
# 각 명령에 필요한 모듈은 해당 분기에서 불러온다.
def main():
    parser = argparse.ArgumentParser(prog="poc")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List prepared and generated cases")
    run = sub.add_parser("run", help="Collect selected source files and regenerate v7 media")
    run.add_argument("--case-id")
    run.add_argument("--limit", type=int, default=1)
    run.add_argument(
        "--local", action="store_true", help="Require already-downloaded source assets"
    )
    analyze = sub.add_parser("analyze", help="Run actual fixed-model analysis for a generated case")
    analyze.add_argument("--case-id", required=True)
    sub.add_parser("verify", help="Verify sample files, citations, media and metrics offline")
    sub.add_parser("evaluate", help="Recalculate the submitted 40-case retrieval results")
    # run은 자료 생성, analyze는 실제 모델 호출, verify·evaluate는 모델 호출 없는 검사다.
    args = parser.parse_args()
    if args.command == "list":
        from src.pipeline import load_packages

        result = [
            dict(case_id=p["case"]["case_id"], map=p["case"]["map_name"], round=p["case"]["round"])
            for p in load_packages()
        ]
    elif args.command == "run":
        from src.pipeline import run

        result = run(args.limit, not args.local, args.case_id)
    elif args.command == "analyze":
        from src.analysis.visual import analyze_case

        report = analyze_case(args.case_id)
        result = dict(
            status=report["status"], case_id=report["case_id"], report_path=report["report_path"]
        )
    elif args.command == "verify":
        from src.evaluation.verify import verify

        result = verify()
    else:
        from src.evaluation.reproduce import reproduce

        result = reproduce()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
