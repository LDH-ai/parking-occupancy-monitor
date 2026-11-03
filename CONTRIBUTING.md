# 팀원 시작 안내

## 처음 참여할 때
1. 저장소 관리자가 GitHub Settings → Collaborators에서 팀원을 초대하고 팀원은 초대를 수락한다.
2. Git과 Python 3.12를 설치하고 아래 명령을 실행한다.

```powershell
git clone https://github.com/LDH-ai/parking-occupancy-monitor.git
cd parking-occupancy-monitor
.\scripts\setup.ps1 -Python 'C:\실제경로\Python312\python.exe'
.\.venv\Scripts\python.exe -m pytest
```

Python 경로는 본인 PC에 맞게 바꾼다. VS Code에서 복제한 폴더를 열고 `.venv` 인터프리터를 선택한다. 영상과 가상환경은 각 PC에서 준비한다.

## 작업 한 건의 순서
1. [단계별 작업표](docs/TEAM_ROADMAP.md)에서 선행 조건을 확인하고 GitHub Issues의 단계별 작업 양식으로 담당자와 완료 조건을 기록한다.
2. 변경 사항이 없는 상태에서 아래 명령으로 작업 브랜치를 만든다.

```powershell
git switch main
git pull --ff-only
git switch -c feat/10-data-yourname
```

3. 작은 작업 단위로 구현하고 테스트한다. 원본 영상·개인정보·가상환경·실행 결과는 올리지 않는다. 공개 가능한 라벨과 설정도 출처와 권한을 확인한다.
4. 자신이 변경한 파일만 지정해서 커밋한다.

```powershell
git add 본인이수정한파일경로
git commit -m "feat: 작업 내용"
git push -u origin HEAD
```

5. GitHub에서 main 대상 Pull Request를 만들고 팀원 한 명에게 검토를 요청한다. 테스트 결과와 재현 명령을 기입하고 검토·자동 검사 후 병합한다. 충돌이 생기면 상대 변경을 확인하고 해결하며 강제 푸시로 main을 덮어쓰지 않는다.

자동 검사는 코드의 기본 동작을 확인한다. 실제 영상의 정확도, 사람 정답 검수, 다른 PC 재현은 별도 증거가 필요하다. 저장소 관리자는 필요하면 main 보호 규칙에서 PR 검토 1명과 `test` 검사 통과를 필수로 설정한다. 초대와 보호 규칙 설정은 이 안내만으로 적용되지 않는다.
