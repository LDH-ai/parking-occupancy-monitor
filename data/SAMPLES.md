# 제안서 참고 프로젝트의 샘플 자료

2026-11-02에 제안서의 세 GitHub 저장소를 확인하고, 커밋을 고정해 원본 파일을 내려받았다.
실제 파일은 `data/raw/`에 로컬로만 보관한다. 중복 제외 26개, 총 63,838,174바이트다.
영상 3개, 이미지·GIF 16개, 좌표 참고 파일 2개, README·LICENSE 5개가 포함된다.

## 영상

| ID | 로컬 파일 (`data/raw/` 기준) | 크기 | FPS | 실제 디코딩 프레임 | 길이 |
| --- | --- | --- | --- | --- | --- |
| shared_carpark | `faisal_ajao/video.mp4` | 1100×720 | 24 | 679 | 약 28.29초 |
| olgarose_lot_1 | `olgarose/parking_lot/videos/parking_lot_1.mp4` | 854×480 | 약 15 | 2247 | 약 149.80초 |
| olgarose_lot_2 | `olgarose/parking_lot/videos/parking_lot_2.mp4` | 960×720 | 약 29.97 | 3770 | 약 125.79초 |

- 모든 다운로드는 원본 Git blob 해시와 크기가 일치한다. 개별 SHA256은 `manifests/sample_validation.json`에 기록했다.
- 영상은 처음부터 읽기 종료까지 디코딩했고 첫·중간·마지막 장면을 확인했다. 세 영상은 관찰상 서로 다른 구도다. 촬영 시각·세션 독립성은 확인되지 않아 videos.csv의 관련 칸은 비워 두었다.
- `olgarose_lot_1`은 컨테이너 표시 2248프레임과 실제 읽힌 2247프레임이 다르다. 메타데이터 차이인지 마지막 프레임 문제인지 확정하지 않았다. 분할·라벨링에는 실제 읽힌 범위를 사용하고 끝부분을 점검한다.
- `mohd-faizy/parking-occupancy-detection`의 `asset/carPark.mp4`와 `asset/carParkImg.png`는 faisal-ajao의 영상·이미지와 각각 완전히 동일하다. 별도 영상이나 독립 테스트 조건으로 세지 않는다. 중복 파일은 한 번만 저장하며 원 출처별 레코드는 유지한다.
- 일부 이미지는 처리 결과·선 검출 예시·배너·시스템 그림이다. 원본 영상이나 정답 이미지로 자동 편입하지 않는다.
- `car_park_pos`, `CarParkPos`는 외부 직렬화 좌표 파일로 보관만 한다. 실행·pickle 역직렬화하지 않았으며 정답이나 자체 ROI로 간주하지 않는다.

## 출처와 사용 조건

추가 조사와 현재 채택 상태는 [USAGE_REVIEW.md](USAGE_REVIEW.md)를 따른다. 2026-11-10 사용자의 MIT 공개 영상 확인을 근거로 개발·평가용 채택을 확정했다. 아래 저장소별 선언은 별도 조사 사실로 보존한다.

- [faisal-ajao/parking-space-counter-opencv](https://github.com/faisal-ajao/parking-space-counter-opencv): 저장소 MIT 라이선스. 원문 LICENSE를 함께 보관했다.
- [olgarose/ParkingLot](https://github.com/olgarose/ParkingLot): 확인한 커밋에 라이선스 파일과 명시적 저장소 라이선스가 없다. 로컬 검토용으로 보관하고 재배포 허가는 미확인으로 기록했다.
- [mohd-faizy/parking-occupancy-detection](https://github.com/mohd-faizy/parking-occupancy-detection): 저장소 MIT 라이선스. README·LICENSE·참고 이미지와 별도 좌표 파일을 보관했다.

저장소 라이선스가 제3자 촬영 영상의 권리까지 독립적으로 입증하는 것은 아니다. 원본 자료는 Git에서 제외하고 공유 전 영상의 원출처·사용 조건을 확인한다.
커밋·원본 URL·크기·Git 해시·중복 관계는 `manifests/upstream_assets.json`에서 확인한다.

## 다시 받기·검증

프로젝트 루트에서:

```powershell
.\.venv\Scripts\python.exe scripts/download_samples.py
.\.venv\Scripts\python.exe scripts/inspect_samples.py
```

다운로드 스크립트는 기존 파일의 해시가 같으면 건너뛰고, 다르면 덮어쓰지 않고 중단한다.
영상 목록은 `manifests/videos.csv`, 무결성·디코딩 결과는 `manifests/sample_validation.json`에 기록된다.
샘플 화면 대조 이미지는 `tmp/sample_review/video_contact_sheet.jpg`에 생성된다.
보정·검증·테스트 개발용 분할 버전 2와 표집 목록을 확정했다. [SPLITS.md](SPLITS.md)를 따른다. 2026-11-10 팀원 ROI 69칸을 보존하고, 그중 경계를 검수·보정한 20칸과 파일럿 검수본 30행을 확정해 10주차 최소 산출물을 완료했다. [검수 기록](../docs/stage10-review.md)·[ROI 안내](../docs/roi.md)·[인계 안내](handoffs/shared_carpark_2026-11-10/README.md)를 따른다. 독립 사람 재검수·다른 시점 ROI·정답 및 사건 규모 확대·최종 성능평가 동결은 후속 작업이다.
