KBM2Pad - keyboard & mouse -> virtual Xbox 360 controller (Windows)

SETUP
1. Install Python 3.9+ from python.org (tick "Add to PATH").
2. Double-click run.bat. It installs vgamepad + pynput and launches the app.
   (vgamepad installs the ViGEmBus driver; if it doesn't, get it from the
   nefarius/ViGEmBus GitHub releases and reboot.)
3. Optional: double-click build_exe.bat to make a standalone kbm2pad.exe in dist\.

USE
- Press F8 (or the button) to start/stop. While running, the mouse is locked to
  screen centre and its movement drives the right stick.
- Double-click any row to rebind: press a key, mouse button or scroll wheel.
- "Block mapped keys" stops mapped inputs reaching other apps (F8 is never blocked).
- Settings save to %USERPROFILE%\kbm2pad.json.

NOTES
- Games must see an Xbox 360 controller; start the app BEFORE launching the game.
- Online games with anti-cheat may flag input emulation. Use at your own risk.
