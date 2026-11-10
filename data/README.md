# 데이터 준비

제안서의 참고 저장소에서 내려받은 자료는 [SAMPLES.md](SAMPLES.md)를 확인한다. 2026-11-10 고유 영상 3개의 목록·개발용 분할 버전 2·라벨 규칙·공통 영상 20칸을 10주차 개발 범위로 확정했다. [확정 검수 기록](../docs/stage10-review.md)과 [라벨 규칙](LABEL_RULES.md)을 따른다. 팀원 ROI 69칸과 정답 원본은 별도 보존한다.

원본 영상은 `raw/`에 로컬로 둔다. 원본 영상·번호판 이미지와 실행 결과는 기본 Git 제외다.
`manifests/videos.csv`에는 출처·사용 조건·촬영 세션·메타데이터를 기록한다.
`manifests/splits.csv`에는 보정(calibration)·검증(validation)·테스트(test) 시간 블록을 기록한다.
현재 개발용 분할과 표집 인덱스는 버전 2로 확정했다. 구간·표집 수·최종 평가 전 조건은 [SPLITS.md](SPLITS.md)를 따른다.
블록 경계는 최소 10초이며 같은 입출차 사건을 나누지 않는다.
`labels/labels.csv`는 헤더만 있는 사람 정답 양식으로 유지한다. 실제 파일럿은 `labels/pilot.shared_carpark.csv`이며 A07·A20·A23의 10시점, 총 30행(free 21·occupied 7·unknown 2)이다. 독립 재검수자는 기록되지 않았다.

현재 사용할 `labels/pilot.shared_carpark.reviewed.csv`는 보정한 20칸 경계에 대한 에이전트 검수본이다. 불명 2건에 차체 겹침이 보여 점유로 수정해 free 21·occupied 9가 되었고, 독립 사람 검수와 구분해 기록했다.

[팀원 인계 원본](handoffs/shared_carpark_2026-11-10/README.md)과 `manifests/team_handoff_validation.json`에 출처·해시·형식 대응을 기록했다. 프로젝트 프레임 번호는 0부터 시작하며 팀원 원본의 1부터 시작하는 번호에서 1을 뺐다. 분할 버전 2는 공통 영상 전체 `[0, 679/24)`를 보정에 배정해 마지막 678번 프레임을 포함한 30행이 모두 보정 구간 안에 있다. 최종 테스트 정답은 아니다.

공통 키는 video_id, frame_id, timestamp_s, slot_id다.
정답은 free/occupied/unknown(사람도 판단 불가), 검출 출력은 free/occupied/unknown(보류)으로 문맥을 구분한다.
차량이 일부라도 칸 안에 있으면 occupied, 완전히 나가면 free다.
정답 unknown은 분류 지표에서 제외하고 수·사유를 보고한다.
원본 링크나 재배포 가능한 데이터만 공유한다.
