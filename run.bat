@echo off

REM Enable ANSI color support for Windows 10/11
set TERM=xterm-256color

echo Checking for virtual environment...
if not exist "venv" (
    echo Creating virtual environment...
    py -m venv venv
) else (
    echo Virtual environment already exists
)

echo Activating virtual environment...
call .\venv\Scripts\activate

echo Installing dependencies...
pip install -r requirements.txt

echo Starting application...
python main.py

pause