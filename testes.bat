@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Backend (pytest) ===
cd backend
.venv\Scripts\python -m pytest -q || (cd .. & pause & exit /b 1)
cd ..\frontend
echo === Frontend (vitest e build) ===
call npx vitest run || (pause & exit /b 1)
call npm run build || (pause & exit /b 1)
cd ..
echo Todos os testes passaram.
pause
