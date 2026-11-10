# 주차면 ROI 지정·저장·재사용

프로젝트 루트 `주차면점유검출/`에서 실행한다. ROI는 주차면 경계이며 빈자리·점유 정답이나 검출 결과가 아니다.

## 준비한 실제 영상 초안

2026-11-10 팀원 인계 ROI `configs/roi.shared_carpark.team.json`을 추가했다. A01~A69의 69칸이며 ID·구역 A·꼭짓점을 원본 그대로 유지하고 현재 JSON 형식과 원본 영상 해시를 연결했다. 기존 아래의 R01~R10 초안은 보존용 별도 설정이다. 같은 영상의 두 설정을 합치거나 ID를 서로 대응한다고 가정하지 않는다.

```powershell
.\.venv\Scripts\python.exe -m parking_monitor roi-preview .\data\raw\faisal_ajao\video.mp4 --roi .\configs\roi.shared_carpark.team.json --frame 377 --output .\tmp\team_roi_review\preview.png
.\.venv\Scripts\python.exe -m parking_monitor roi-pick .\data\raw\faisal_ajao\video.mp4 --output .\configs\roi.shared_carpark.team.json --video-id shared_carpark --zone A --prefix A
```

69칸의 형상·범위·중복 ID·비중첩·마스크 생성·영상 해시·저장/재로드를 검증했다. 프레임 0·377·678에서 원본과 50% 크기로 미리보기를 생성했다. 시작·끝 화면 및 파일럿 10시점을 시각적으로 검토했지만, 주차면 안쪽으로 좁게 잡힌 영역의 일부 진입 판정은 연속 구간에서 추가 검수해야 한다. 69칸은 후보 전체이며 로드맵의 10~20칸 평가 대상 확정이나 해당 조건의 속도 측정을 뜻하지 않는다. [인계 원본·파일럿 정답 안내](../data/handoffs/shared_carpark_2026-11-10/README.md)를 따른다.

`configs/roi.shared_carpark.json`에는 공통 영상의 오른쪽 주차열 10칸(R01~R10)을 저장했다.
실제 영상 0번 프레임을 눈으로 확인해 주차선 안쪽에 네 꼭짓점을 지정한 에이전트 초안이며, 사용자 검토는 아직 하지 않았다.
기준 해상도는 1100×720, 구역은 `right`다. 원본 영상 SHA256·영상 ID·지정 프레임을 함께 기록했다.
소스 라이선스 문제·사람 정답·임계값 보정·분할 최종 확정은 별도 작업이다. 이 공통 영상은 현재 보정용에만 배정되어 있다.

## 기존 초안 열기

```powershell
.\.venv\Scripts\python.exe -m parking_monitor roi-pick .\data\raw\faisal_ajao\video.mp4 --output .\configs\roi.shared_carpark.json --video-id shared_carpark --zone right --prefix R
```

출력 JSON이 이미 있으면 먼저 불러와 표시한다. 다른 원본 영상 해시·기준 해상도와 일치하지 않으면 중단한다.
GUI 창이 열린 동안 터미널은 프로그램 종료를 기다린다. 창에 표시된 노란 윤곽선은 ROI이며 점유 상태가 아니다.

| 조작 | 동작 |
| --- | --- |
| 왼쪽 클릭 4회 | 한 칸의 꼭짓점을 시계 또는 반시계 방향으로 순서대로 지정 |
| 오른쪽 클릭 또는 U | 마지막 점 취소. 입력 중인 점이 없으면 마지막 칸을 3개 점 상태로 되돌림 |
| D | 입력 중인 칸 취소. 입력 중인 칸이 없으면 마지막 완성 칸 삭제 |
| S | JSON 저장. 네 점이 미완성이면 저장을 중단하고 안내 |
| Q 또는 ESC | 종료. 미저장 변경이 있으면 한 번 더 눌러 버리거나 S로 저장 |

처음부터 다시 지정하려면 기존 파일을 덮기보다 `--output configs/roi.shared_carpark.reviewed.json`처럼 새 이름을 사용한다.
기존 칸 수정은 뒤에서부터 U/D로 되돌려 다시 지정할 수 있다. `--zone`, `--prefix`는 새로 추가하는 칸에 적용되며 기존 ID는 유지한다.
주차면 안쪽을 지정하고 서로 겹치지 않게 한다. 사각형은 직사각형일 필요가 없으며 원근에 맞춘 네 점을 허용한다.
마우스 좌표는 화면의 표시 배율·안내 영역을 보정해 원본 좌표로 저장한다. OpenCV 기본 글꼴을 사용해 조작 안내와 ID는 영문으로 표시한다.

## 다른 영상의 ROI 만들기

```powershell
.\.venv\Scripts\python.exe -m parking_monitor roi-pick .\data\raw\olgarose\parking_lot\videos\parking_lot_1.mp4 --output .\configs\roi.olgarose_lot_1.json --video-id olgarose_lot_1 --zone A --prefix A
```

`--frame 150`처럼 다른 지정 프레임을 선택할 수 있다. 다른 시점·카메라에는 별도 JSON을 만든다.
이 도구는 원본 해시가 다른 영상에 설정을 자동 재사용하지 않는다. 같은 카메라의 다른 촬영 파일로 확장하려면 별도 확인 절차가 필요하다.

## 저장 파일 재사용 확인

```powershell
.\.venv\Scripts\python.exe -m parking_monitor roi-preview .\data\raw\faisal_ajao\video.mp4 --roi .\configs\roi.shared_carpark.json --frame 336 --width 550 --output .\tmp\roi_review\preview.png
```

위 명령은 GUI 없이 JSON을 불러와 지정 프레임에 ROI를 표시하고 이미지와 각 마스크의 픽셀 수를 출력한다.
`--width` 생략 시 원본 해상도다. 영상과 좌표를 같은 비율로 축소하며 잘못된 종횡비·빈 마스크·잘못된 소스를 검사한다.
0개 칸인 예시 JSON은 최종 저장·미리보기용으로 사용할 수 없다. 좌표는 정수 `[x,y]`, 기준 크기는 `[width,height]`다.

## 검증 결과

- 공통 영상 10칸 JSON 저장·불러오기 내용 일치, 서로 다른 3프레임(0·336·678) 표시, 원본·50% 축소 마스크 생성 확인.
- 실제 GUI 창 생성·렌더·기존 설정 로드·종료 점검 통과. 자동 테스트에서는 마우스 콜백·화면 좌표 변환·저장 흐름도 확인했다. 사용자의 실제 클릭 검수를 대신하지 않는다.
- 교차 사각형·중복 꼭짓점·겹친 칸·영상 밖 좌표·다른 영상 해시를 거부한다. JSON 저장은 임시 파일 작성 후 교체한다.
- 전체 테스트 27개 통과. 상세 재사용 기록은 `data/manifests/roi_validation.json`이다.

VS Code에서 이 폴더를 열면 실행 구성 `ROI 편집 - 공통 영상`을 선택해 F5로 열 수도 있다.
