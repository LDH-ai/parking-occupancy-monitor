# 주차면 점유 검출 및 모니터링

고정 카메라의 주간 영상과 수동 다각형 ROI를 이용하는 비훈련 고전 영상처리 프로젝트다.
프로젝트 로드맵은 로컬 형제 폴더 `../디지털영상처리이론과실습/p3_과제프로젝트/`의 **주차면 점유검출 프로젝트 제안서.pdf / 주차면_점유검출_프로젝트_제안서_로드맵_최종.docx**이며 단계별 실행 기준은 [AGENTS.md](AGENTS.md)를 따른다.
현재는 개발 환경과 입력 점검 도구를 준비한 상태다. 검출기·보정·평가·화면은 후속 구현이며, 실영상 성능을 측정하지 않았다.

## 개발 환경

Windows x64, Python 3.12(로컬 검증 3.12.14), NumPy, OpenCV, Matplotlib, pytest.
이 README가 있는 `주차면점유검출` 폴더에서 실행한다.
프로젝트 전용 `.venv`를 사용하며 기존 실습 환경은 재사용하지 않는다.
Python 3.12 설치 후 PowerShell에서:

```powershell
.\scripts\setup.ps1 -Python 'C:\path\to\Python312\python.exe'
.\.venv\Scripts\python.exe -m parking_monitor doctor
.\.venv\Scripts\python.exe -m pytest
```

`-Python`에는 실제 Python 3.12 실행 파일을 지정한다. 실행 정책이 스크립트를 막으면 현재 프로세스에서만 정책을 조정하거나 아래 명령을 직접 실행한다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pip check
```

`requirements.txt`는 로컬에서 설치·검증한 전체 버전을 고정한다. 의존성을 변경할 때 Python 3.12에서 재설치·검증 후 고정 파일을 갱신한다.
VS Code에서 이 폴더를 열면 `.venv/Scripts/python.exe`를 선택한다. 가상환경은 PC 간 복사하지 않고 재생성한다.

## 입력과 초기 설정

1. 사용 조건이 확인된 영상을 `data/raw/`에 확보하고 `data/manifests/videos.csv`에 기록한다.
2. `data/manifests/splits.csv`에 보정·검증·테스트 블록을 분리한다.
3. 영상 정보와 첫 프레임을 확인한다.
4. 실제 프레임에서 10개 이상 칸의 네 꼭짓점을 지정해 `configs/roi.example.json`을 바탕으로 ROI 설정을 만든다.
5. 라벨 규칙에 따라 `data/labels/labels.csv`를 작성한다.

```powershell
.\.venv\Scripts\python.exe -m parking_monitor video-info .\data\raw\parking.mp4
```

`configs/*.example.json`은 미보정 예시다. ROI는 비어 있고 임계값은 없으므로 검출용 최종 설정으로 사용할 수 없다.
현재 지원 명령은 `doctor`, `video-info`다. ROI 편집·검출·보정·평가 명령은 아직 구현하지 않았다.

## 로드맵과 평가 원칙

| 단계 | 산출물과 완료 기준 |
| --- | --- |
| 10주차 | 영상·분할·라벨 규칙·ROI. 저장 영상의 10개 이상 좌표 재사용 |
| 11주차 | 픽셀 비율 기준선·r 분포·초기 혼동표. 동일 설정 CSV 재생성 |
| 12주차 | 라플라시안·결합·시간 안정화 A~D 비교. 검증 후 설정 동결 |
| 13주차 | 화면·CSV·평가 통합, 속도·지연. 저장 영상 전체 실행 후 카메라 확장 |
| 14주차 | 동결 테스트·열화 실험·문서, 다른 팀원의 새 환경 재현 |
| 15주차 | 코드·설정·정답·결과·보고서·포스터·시연 영상 제출 |

픽셀 비율과 ROI 내부 라플라시안 절댓값 평균을 비교한다. 하한/상한 사이와 불일치는 보류다.
초기 보류에서 같은 확정 후보가 T초 유지되어야 확정하며, 후보 변경·불확실 시 즉시 보류로 전환한다.
빈자리를 양성으로 두며 빈자리 정답의 보류 출력도 FN에 포함한다.
목표는 F1 ≥0.90, 확정 비율 ≥95%, 거짓 빈자리율 ≤5%, CPU·720p·20칸 전체 15 FPS다. 모두 미측정 목표다.
보정에서 임계값, 검증에서 필터·결합·T를 선택하고 최종 테스트는 선택에 사용하지 않는다.

강의자료·제공 양식·개인정보가 포함된 원본 문서·원본 영상·가상환경·중간 렌더는 초기 GitHub 반영 범위에서 제외했다.

## 자료와 이전 버전

코드 작성·프로젝트 진행은 이 저장소에서만 수행한다. 이론·로드맵·원본 문서·이전 버전은 로컬 `../디지털영상처리이론과실습/`에서 관리한다. GitHub 이력에서도 분리 전 초기 버전을 확인할 수 있다.
