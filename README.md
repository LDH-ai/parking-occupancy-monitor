# Parking Occupancy Monitor

고전 영상처리 기반 주차면 점유 검출 팀프로젝트.
개발 코드·설정·설치 및 실행 절차는 [프로젝트 README](p3_과제프로젝트/README.md)를 참조한다.

```powershell
cd .\p3_과제프로젝트
.\scripts\setup.ps1 -Python 'C:\path\to\Python312\python.exe'
.\.venv\Scripts\python.exe -m parking_monitor doctor
.\.venv\Scripts\python.exe -m pytest
```

현재는 개발 환경과 입력 점검 도구를 구성했다. 실제 주차 영상·ROI·사람 정답 확보와 검출기·평가 구현은 후속 단계다.
프로젝트의 범위·단계·평가 기준은 [프로젝트 지침](p3_과제프로젝트/AGENTS.md)을 따른다.
