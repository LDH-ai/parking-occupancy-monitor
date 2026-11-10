# 샘플 데이터 사용 조건 검토

검토일: 2026-11-02. 다운로드한 커밋의 LICENSE·README·전체 파일 목록·영상 추가 이력과 공개된 출처 정보를 대조했다.

**저장소 라이선스 조사는 완료했지만, 영상 3개의 이용 조건은 아직 확정되지 않았다.**
이는 모든 이용이 금지된다는 법적 판정이 아니라, 최종 평가·발표·재배포에 쓸 권한의 근거를 아직 확보하지 못했다는 프로젝트 상태다.

## 자료별 판정

| 자료 | 확인된 사실 | 미확인 사항 | 프로젝트 상태 |
| --- | --- | --- | --- |
| faisal-ajao의 video.mp4 / image.png | 저장소는 MIT, 2025 Faisal Ajao 저작권 고지 | 촬영 원출처·영상에 적용되는 권한과 허가 범위 | 영상 사용 조건 미확정 |
| mohd-faizy의 carPark.mp4 / carParkImg.png | 저장소는 MIT, 2026 Mohd Faizy 고지. 위 영상·이미지와 바이트가 동일 | 위와 동일. 다른 저장소에 복제되었다는 사실은 원권리 증거가 아님 | 동일 원천 자료로 묶음, 별도 승인 근거로 세지 않음 |
| olgarose의 parking_lot_1.mp4 / parking_lot_2.mp4 | 확인 커밋에 LICENSE·COPYING·NOTICE 파일이 없고 README에도 명시적 허가 조건 없음 | 촬영 원출처·학술 이용·발표·재배포 허가 | 이용 조건 미확정 |
| 처리 결과 이미지·GIF·배너·좌표 | 출처별 저장소 선언·파일 해시 확보 | 제3자 원본의 포함 여부·개별 자산의 허가 범위 | 원본 코드 라이선스를 일괄 대입하지 않음 |

## 확인 근거

1. [faisal-ajao MIT LICENSE](https://github.com/faisal-ajao/parking-space-counter-opencv/blob/1711e343cef555d90056601999978bfaa7b5a420/LICENSE): 해당 소프트웨어의 사용·수정·배포 시 저작권·허가 고지 보존이 조건이다. 원본 촬영자·미디어별 권한 설명은 확인하지 못했다.
2. [mohd-faizy MIT LICENSE](https://github.com/mohd-faizy/parking-occupancy-detection/blob/ad79b62dec513471af1f34179ee1ec84d13d1c90/LICENSE): 같은 MIT 조건이다. 다른 저장소의 라이선스만으로 공통 영상의 촬영자·원권리자를 확정하지 않았다.
3. [olgarose 고정 커밋](https://github.com/olgarose/ParkingLot/tree/5367aba807ccf99a5697dbbf6790ddc011dda67d): 전체 트리와 README에서 일반 사용 허가를 확인하지 못했다. [초기 영상 추가 커밋](https://github.com/olgarose/ParkingLot/commit/29399684a7c91787f679765db0d9a9eb7e09f0fc)은 2018년 자료 포함 이력이며 촬영 권리를 입증하지는 않는다.
4. [faisal-ajao 영상 추가 커밋](https://github.com/faisal-ajao/parking-space-counter-opencv/commit/7d473c6da89be26bab469daef0417333f7881830): 파일 추가 사실은 확인했지만 원촬영 출처는 확인하지 못했다.
5. [GitHub 공식 라이선스 안내](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository): 공개 저장소에서 열람·fork가 가능하다는 사실과 일반적인 사용·변경·배포 허가는 구분된다.

Murtaza / Computer Vision Zone 튜토리얼은 웹 검색에서 출처 후보로 나타났지만 정확한 원본 파일 연결과 촬영 권리를 검증하지 못했다. 영상의 확정 출처나 라이선스 근거로 채택하지 않았다.

## 프로젝트에 적용할 처리

- 영상 목록의 기존 `MIT` 단독 표기를 수정해 **저장소 MIT 선언 / 영상 권한 미확인**을 구분했다.
- 원본 자료와 기존 로컬 검토 결과는 보존한다. 원본은 계속 Git 제외이며, 세 영상을 최종 평가용 데이터로 확정하거나 공개 시연·스크린샷·재배포 허가가 확보됐다고 기록하지 않는다.
- 학술 목적·출처 표기만으로 허가가 자동 성립한다고 가정하지 않는다. 공개 발표와 원본 재배포는 별도 사용 형태로 확인한다.
- 최종 채택 전 실제 권리자에게 영상 원출처와 허가 범위를 확인하거나, 영상 자체에 명시적 이용 조건이 있는 데이터 또는 허가받은 직접 촬영본으로 교체한다.
- 확인할 범위는 수업용 알고리즘 개발·평가, 프레임 추출·정답 작성, 보고서·포스터 이미지, 시연 영상 공개, 원본 영상 또는 수정본 재배포다. 실제 권리자와 저장소 게시자가 같은지도 확인한다.
- 소유자에게 연락하거나 허가를 받은 사실은 없다. 현재 상태는 `manifests/rights_review.json`에 기록했다. 이 검토로 10주차의 데이터 사용 조건 확정을 완료 처리하지 않는다.
