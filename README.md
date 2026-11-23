# 주차면 점유 검출 및 모니터링

**디지털영상처리 이론과 실습 · 부릉부릉**

고정 카메라가 촬영한 주차장에서 지정한 주차면을 **빈자리·점유·보류**로 판정하는 OpenCV 프로젝트다. 학교 앞 주차장의 실제 촬영 영상으로 검출 성능을 검증하고, 검증을 마친 뒤 USB 웹캠과 모바일 대시보드로 시연하는 것이 목표다. [현장 검증 제안서](<docs/deliverables/field-validation/학교 앞 주차장 점유 검출 검증 제안서.docx>)

| 구분 | 현황 |
| --- | --- |
| 구현 | 영상 점검, 다각형 ROI 편집·미리보기, 픽셀 비율 기준선, 알고리즘 정량 평가 CLI |
| 동작 검증 | FPS가 다른 합성 영상으로 검증·설정 동결·최종 테스트를 실행했다. 공통 저장 영상에서는 20칸 ROI와 픽셀 비율 기준선을 재현했다. |
| 현장 검증 | 공통 영상의 검수 라벨 30행은 보정용이다. 학교 앞 영상과 독립 검증·테스트 정답을 확보한 뒤 실제 F1·지연·처리량과 시연 구성을 확정한다. |
| 시연 계획 | 웹캠 → 노트북 검출 → SQLite → Streamlit. 현장에서 QR을 열어 휴대폰의 빈자리 수와 칸별 상태를 확인한다. 현장 연결이 어려우면 학교 앞 저장 영상으로 재생 시연한다. |

## 검출과 비교 방식

```text
고정 카메라 프레임
├─ 픽셀 비율     이진화 → 형태학 → 선택적 연결성분 필터 → ROI 안의 흰 픽셀 비율
└─ 라플라시안   평활 → 라플라시안 응답 → ROI 안의 절댓값 평균
                  ↓
칸별 두 임계값 → 단독 또는 일치 판정 → 선택적 시간 안정화
                  ↓
빈자리 · 점유 · 보류
```

두 특징을 결합하면 같은 확정 상태를 낸 경우에만 그 상태를 채택한다. 안정화는 같은 확정 후보가 설정 시간 동안 연속으로 유지되면 상태를 확정한다. 다양한 조건에서의 효과를 확인하기 위해 아래 비교를 같은 영상·ROI·정답으로 실행한다.

| 확인할 효과 | 비교 구성 |
| --- | --- |
| 단독 성능 | A 픽셀 비율과 B 라플라시안 |
| 연결성분 필터 | A와 A-CC |
| 특징 결합 | A와 B 각각을 C 두 특징 결합과 비교 |
| 시간 안정화 | C와 D. 안정화 시간 0.5초와 1.0초를 각각 측정 |
| 통합 후 필터 | 같은 안정화 시간의 D와 D-CC |

분류 점수는 정답을 붙인 프레임에서 계산하고, 입·출차 지연은 연속 프레임에서 잰다. 빈자리가 양성이고, 실제 빈자리의 출력 보류는 F1 계산에서 미탐에 포함한다. 검증에서 **거짓 빈자리율 5% 이하와 확정 비율 95% 이상**을 충족한 구성 중 빈자리 F1이 높은 것을 우선하고, 동률이면 전체 루프 시간을 비교한다.

## 설치와 빠른 실행

Windows PowerShell에서 **Python 3.12**의 실행 파일을 지정한다. 설치 스크립트가 프로젝트 전용 가상환경과 고정 의존성을 설정한다.

```powershell
git clone https://github.com/LDH-ai/parking-occupancy-monitor.git
cd parking-occupancy-monitor
.\scripts\setup.ps1 -Python 'C:\path\to\Python312\python.exe'
.\.venv\Scripts\python.exe -m parking_monitor doctor
.\.venv\Scripts\python.exe -m pytest
```

설치 스크립트 대신 직접 설치할 수 있다. Python 3.12가 선택된 상태에서 실행한다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pip check
```

### 공통 샘플로 픽셀 기준선 확인

[샘플 안내](data/SAMPLES.md)에 따라 원본 영상을 로컬에 확보한 뒤, 저장소의 20칸 ROI와 검수 라벨을 사용한다. 이 샘플은 검출 흐름과 보정 결과를 재현하는 용도다.

```powershell
.\.venv\Scripts\python.exe scripts/download_samples.py
$baselineOut = "results/runs/shared-carpark-$(Get-Date -Format yyyyMMdd-HHmmss)"
.\.venv\Scripts\python.exe -m parking_monitor pixel-baseline `
  --video data/raw/faisal_ajao/video.mp4 `
  --roi configs/roi.shared_carpark.final.json `
  --labels data/labels/pilot.shared_carpark.reviewed.csv `
  --splits data/manifests/splits.csv `
  --config configs/examples/pixel-baseline.json `
  --timeseries --out $baselineOut
```

## 학교 앞 영상 정량 평가

1. **촬영과 ROI.** 고정 카메라에 잘 보이는 10칸을 대상으로 촬영한다. 최종 테스트에는 150초 영상 2개와 입차·출차 각각 6건을 촬영해, 각 방향에서 최소 5건을 평가하는 것이 권장안이다. `video-info`로 영상 정보를 확인하고 `roi-pick`으로 해당 영상의 ROI를 작성한다. [ROI 안내](docs/guides/roi.md)
2. **정답과 분할.** 보정·검증·최종 테스트를 세션이나 시간 구간으로 나눈다. 분류용 프레임 정답과 지연 측정용 사건 정답을 준비한다. 최종 분류는 1초 이상 간격의 200프레임 이상을 목표로 한다. [데이터 준비 및 라벨 규칙](data/README.md)
3. **평가 목록.** [예시 JSON](configs/examples/quantitative-evaluation.json)을 복사해 영상·ROI·분할·정답 경로를 채운다. 경로는 목록 파일 기준이다. 카메라 위치나 주차면 좌표가 바뀌면 새 `view_id`와 보정 자료를 지정한다. 동일한 위치·좌표·칸 ID·기준 해상도의 촬영본은 `view_id`를 공유할 수 있다.

```powershell
$manifest = "configs/school-evaluation.json"
$run = "results/runs/quantitative-evaluation/school-$(Get-Date -Format yyyyMMdd-HHmmss)"
.\.venv\Scripts\python.exe -m parking_monitor evaluate validate --manifest $manifest --out "$run/validation"
.\.venv\Scripts\python.exe -m parking_monitor evaluate freeze --validation-run "$run/validation" --out "$run/frozen.json"
.\.venv\Scripts\python.exe -m parking_monitor evaluate test --manifest $manifest --frozen "$run/frozen.json" --out "$run/test"
```

`validate`에서 보정과 검증을 실행하고, `freeze`에서 시연 구성과 임계값을 저장한다. 기준을 충족한 구성이 없으면 검증표를 확인해 `freeze --candidate <구성 ID> --reason "<선택 근거>"`로 절충안을 기록한다. `test`는 동결한 설정으로 별도 최종 구간을 평가한다. [평가 프로그램 설계](docs/project/quantitative-evaluation-design.md)

| 결과 파일 | 내용 |
| --- | --- |
| `comparison.csv` | 구성별 F1, 거짓 빈자리율, 확정 비율, FPS, 처리시간, 입·출차 지연 요약 |
| `metrics.json` | 영상별·전체 혼동표와 지표 |
| `predictions.csv` · `events.csv` | 프레임별 판정과 사건별 지연·미검출 |
| `run_info.json` · `thresholds.json` · `frozen.json` | 입력과 코드 해시, 보정 임계값, 검증에서 선택한 설정 |

저장 영상 CLI의 FPS는 화면을 띄우지 않은 상태에서 디코딩·검출·CSV 기록을 포함해 잰다. 제안서 최종 목표는 **빈자리 F1 ≥ 0.90, 확정 비율 ≥ 95%, 거짓 빈자리율 ≤ 5%, CPU·720p·20칸에서 전체 15 FPS 이상**이다. 모바일 시연의 3초 반영 목표는 웹캠에서 휴대폰까지 별도로 측정한다.

## 저장소 구조

| 경로 | 용도 |
| --- | --- |
| [src/parking_monitor](src/parking_monitor/) | 공통 CLI, 영상·ROI 도구, 픽셀 비율 기준선 |
| [src/evaluation](src/evaluation/) | 라플라시안·결합·안정화, 정량 비교, 설정 동결 |
| [configs](configs/) · [data](data/README.md) | ROI·실행 설정, 영상 목록·분할·정답 |
| [tests](tests/) · [scripts](scripts/) | 자동 테스트, 환경 설정, 데이터 검증 |
| [docs](docs/README.md) | 현장 제안서, 평가 설계, 진행 기록과 팀원 안내 |

영상 원본은 로컬 `data/raw/`에, 실행 결과는 `results/runs/`에 둔다. 팀원 작업 절차와 평가 세부 기준은 [팀원 시작 안내](.github/CONTRIBUTING.md)와 [프로젝트 지침](AGENTS.md)을 참고한다.
