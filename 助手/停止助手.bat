@echo off
chcp 65001 >nul
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 18765 -State Listen -ErrorAction SilentlyContinue; if ($c) { Stop-Process -Id $c.OwningProcess -Force; Write-Host 'stopped' } else { Write-Host 'not running' }"
timeout /t 2 >nul
