param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    & $Python -c "import sys; assert sys.version_info[:2] == (3, 12), 'Python 3.12 is required'"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 실행 파일을 -Python 인자로 지정하세요." }
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "가상환경 생성 실패" }
    }
    $venvPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "의존성 설치 실패" }
    & $venvPython -m pip install --no-deps --no-build-isolation -e .
    if ($LASTEXITCODE -ne 0) { throw "패키지 설치 실패" }
    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw "의존성 충돌" }
    & $venvPython -m parking_monitor doctor
    if ($LASTEXITCODE -ne 0) { throw "환경 점검 실패" }
} finally { Pop-Location }
