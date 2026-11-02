# 데이터 준비

원본 영상은 `raw/`에 로컬로 둔다. 원본 영상·번호판 이미지와 실행 결과는 기본 Git 제외다.
`manifests/videos.csv`에는 출처·사용 조건·촬영 세션·메타데이터를 기록한다.
`manifests/splits.csv`에는 보정(calibration)·검증(validation)·테스트(test) 시간 블록을 기록한다.
블록 경계는 최소 10초이며 같은 입출차 사건을 나누지 않는다.
`labels/labels.csv`는 사람 정답 양식이다. 헤더만 제공하며 실제 정답은 아직 없다.

공통 키는 video_id, frame_id, timestamp_s, slot_id다.
정답은 free/occupied/unknown(사람도 판단 불가), 검출 출력은 free/occupied/unknown(보류)으로 문맥을 구분한다.
차량이 일부라도 칸 안에 있으면 occupied, 완전히 나가면 free다.
정답 unknown은 분류 지표에서 제외하고 수·사유를 보고한다.
원본 링크나 재배포 가능한 데이터만 공유한다.
