@echo off
chcp 65001 >nul
title FOMO AI Trading Intelligence
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
  echo [erro] Python 3.12 ou mais recente nao encontrado. Instale em https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist backend\.venv\Scripts\python.exe (
  echo Criando ambiente Python...
  py -3 -m venv backend\.venv || (pause & exit /b 1)
)
echo Conferindo dependencias do backend...
backend\.venv\Scripts\python -m pip install -q --disable-pip-version-check -r backend\requirements.txt || (pause & exit /b 1)

if not exist frontend\dist\index.html (
  where npm >nul 2>&1
  if errorlevel 1 (
    echo [erro] Node.js nao encontrado. Instale em https://nodejs.org/ para compilar a interface.
    pause
    exit /b 1
  )
  echo Compilando a interface...
  pushd frontend
  call npm install --no-audit --no-fund || (popd & pause & exit /b 1)
  call npm run build || (popd & pause & exit /b 1)
  popd
)

echo.
echo FOMO AI Trading Intelligence em http://127.0.0.1:8765
echo Feche esta janela (ou Ctrl+C) para encerrar.
echo.
if not defined FOMOAI_NO_BROWSER start "" http://127.0.0.1:8765
cd backend
.venv\Scripts\python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765
