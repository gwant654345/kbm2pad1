@echo off
py -m pip install --quiet vgamepad pynput pyinstaller
py -m PyInstaller --onefile --noconsole --collect-all vgamepad kbm2pad.py
echo Done - your app is in the dist folder.
pause
