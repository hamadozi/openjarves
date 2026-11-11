@echo off
setlocal
py -3 -m pip install --upgrade pip
if errorlevel 1 goto failed
py -3 -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Setup complete. Start OpenJarves with: py -3 app.py
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.10+ and try again.
pause
exit /b 1
