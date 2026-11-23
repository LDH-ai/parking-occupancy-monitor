"""정량 평가 CLI의 하위 명령과 인자를 연결한다."""

from .runner import freeze_evaluation, run_evaluation


def add_arguments(parser):
    phases = parser.add_subparsers(dest="evaluation_phase", required=True)
    validate = phases.add_parser("validate", help="보정과 검증 구간에서 구성 비교")
    test = phases.add_parser("test", help="동결 설정으로 최종 테스트")
    for command in (validate, test):
        command.add_argument("--manifest", required=True, help="평가 목록 JSON")
        command.add_argument("--out", required=True, help="새 결과 폴더")
        command.set_defaults(handler=_run)
    test.add_argument("--frozen", required=True, help="검증 후 동결한 설정 JSON")

    freeze = phases.add_parser("freeze", help="검증 결과에서 시연 구성과 설정 동결")
    freeze.add_argument("--validation-run", required=True, help="validate 결과 폴더")
    freeze.add_argument("--out", required=True, help="새 동결 설정 JSON 파일")
    freeze.add_argument("--candidate", help="기준 충족 구성이 없을 때 선택할 비교 구성")
    freeze.add_argument("--reason", help="기준 미달 구성을 선택한 이유")
    freeze.set_defaults(handler=_freeze)


def _run(args):
    phase = "validation" if args.evaluation_phase == "validate" else "test"
    try:
        return run_evaluation(args.manifest, args.out, phase=phase, frozen_path=getattr(args, "frozen", None))
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError(f"평가 입력의 열 또는 설정을 확인하세요: {error}") from error


def _freeze(args):
    try:
        return freeze_evaluation(args.validation_run, args.out, candidate_id=args.candidate, reason=args.reason)
    except (KeyError, TypeError) as error:
        raise ValueError(f"검증 실행 결과 형식을 확인하세요: {error}") from error
