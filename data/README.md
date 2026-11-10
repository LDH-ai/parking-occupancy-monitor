# 데이터 준비

제안서의 참고 저장소에서 내려받은 자료와 사용 시 유의사항은 [SAMPLES.md](SAMPLES.md)를 확인한다. 고유 영상 3개와 잠정 분할, 공통 영상의 팀원 ROI 69칸과 파일럿 정답 30행을 확보했다. 경계·정답 재검수와 데이터 확대·분할 확정은 남아 있다.

원본 영상은 `raw/`에 로컬로 둔다. 원본 영상·번호판 이미지와 실행 결과는 기본 Git 제외다.
`manifests/videos.csv`에는 출처·사용 조건·촬영 세션·메타데이터를 기록한다.
`manifests/splits.csv`에는 보정(calibration)·검증(validation)·테스트(test) 시간 블록을 기록한다.
현재 개발용 잠정 분할과 표집 인덱스를 작성했다. 구간·표집 수·확정 전 조건은 [SPLITS.md](SPLITS.md)를 따른다.
블록 경계는 최소 10초이며 같은 입출차 사건을 나누지 않는다.
`labels/labels.csv`는 헤더만 있는 사람 정답 양식으로 유지한다. 실제 파일럿은 `labels/pilot.shared_carpark.csv`이며 A07·A20·A23의 10시점, 총 30행(free 21·occupied 7·unknown 2)이다. 독립 재검수자는 기록되지 않았다.

[팀원 인계 원본](handoffs/shared_carpark_2026-11-10/README.md)과 `manifests/team_handoff_validation.json`에 출처·해시·형식 대응을 기록했다. 프로젝트 프레임 번호는 0부터 시작하며 팀원 원본의 1부터 시작하는 번호에서 1을 뺐다. 마지막 678번 프레임의 3행은 현재 보정 구간 `[0, 28)` 밖이다. 파일럿 전체를 자동으로 보정·테스트 집합에 넣지 않는다.

공통 키는 video_id, frame_id, timestamp_s, slot_id다.
정답은 free/occupied/unknown(사람도 판단 불가), 검출 출력은 free/occupied/unknown(보류)으로 문맥을 구분한다.
차량이 일부라도 칸 안에 있으면 occupied, 완전히 나가면 free다.
정답 unknown은 분류 지표에서 제외하고 수·사유를 보고한다.
원본 링크나 재배포 가능한 데이터만 공유한다.
