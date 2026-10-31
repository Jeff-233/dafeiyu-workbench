@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo 没找到 Python。请先安装 Python 3.9 或更高版本，并勾选 Add to PATH。
  echo https://www.python.org/downloads/
  pause
  exit /b 1
)
echo == 正在生成工作台 ==
%PY% "%~dp0build_workbench.py" --apply
echo.
echo 生成完了，双击 index.html 看效果。
pause >nul
