# 팀원 원본 인계 파일

2026-11-10 전달받은 `roi.json`, `pilot_ground_truth.csv`, `roi_picker.py`를 내용 변경 없이 보존했다. 원본 해시와 현재 구현 형식으로의 대응은 `../../manifests/team_handoff_validation.json`에 기록했다.

- 영상은 기존 `shared_carpark`와 SHA-256이 같다. `video.mp4`는 재배포하지 않으며 [샘플 안내](../../SAMPLES.md)에 따라 `data/raw/faisal_ajao/video.mp4`로 준비한다.
- 원본 ROI는 1100×720의 A01~A69, 69칸이다. 현재 도구에서는 `configs/roi.shared_carpark.team.json`을 사용한다. 기존 R01~R10 초안은 별도 보존했다. 두 설정은 같은 영상의 별도 ID 체계이므로 합쳐서 79칸으로 세지 않는다.
- 원본 CSV는 A07·A20·A23의 10시점, 30행이다. 현재 양식 파일은 `data/labels/pilot.shared_carpark.csv`다. `frame_id`에서 1을 빼고 `vacant`를 `free`로 대응했다. 라벨과 불명 사유를 임의로 바꾸거나 재검수자로 서명하지 않았다.
- 원본 선택기는 이 폴더 바로 아래의 `video.mp4`를 요구한다. 영상은 이 폴더에 포함하지 않으며, 일반 사용에는 프로젝트의 `roi-pick`·`roi-preview` 명령을 권장한다. 원본 선택기를 재현해야 한다면 Git 제외 위치인 `tmp/`에 선택기·ROI 복사본과 영상을 함께 두고 실행한다. 이 보존본에서 직접 편집하지 않는다.

초기 인계 검토에서는 678번 프레임(28.250초)의 3행이 당시 보정 구간 `[0, 28)` 밖이었다. 후속 검수에서 분할 버전 2를 공통 영상 전체로 바꿔 현재는 30행 모두 보정 구간 안에 있다. 사용할 20칸은 `configs/roi.shared_carpark.final.json`, 별도 정답 검수본은 `data/labels/pilot.shared_carpark.reviewed.csv`다. 경계를 보정하면서 불명 2건을 점유로 수정했으며, 여기 보존한 원본 값은 바꾸지 않았다. [후속 검수 기록](../../../docs/stage10-review.md)을 따른다. 에이전트 검수는 독립 사람 검수와 구분하며 이 파일럿을 최종 테스트 정답이나 검출 성능 실적으로 보고하지 않는다.
