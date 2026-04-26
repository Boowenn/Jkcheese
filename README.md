# Jkcheese

`Jkcheese` is a read-only helper for Golden Spatula (`com.tencent.jkchess`) on LDPlayer.

Current module scope:

- detect LDPlayer instances
- check game install status
- launch the emulator
- launch the game
- capture emulator screenshots
- crop known in-game regions from screenshots
- read gold, level, and HP from screenshots
- print confidence warnings and basic economy advice
- export OCR debug crops for calibration
- provide a simple Windows GUI
- build a one-file EXE with PyInstaller
- run unit tests
- run CI on each push

This project does **not** do:

- auto click
- auto buy
- auto positioning
- memory injection
- packet tampering
- APK modification

## Quick start

Run the GUI:

```powershell
python main.py
```

Run the CLI:

```powershell
python main.py inspect
python main.py launch --index 0
python main.py run-game --index 0 --launch-if-needed
python main.py screenshot --index 0
```

Crop regions from an existing screenshot:

```powershell
python main.py regions --input captures\live_game.png --output captures\regions
```

Capture and crop regions in one step:

```powershell
python main.py capture-regions --index 0 --output captures\regions --launch-if-needed
```

Read gold, level, and HP from an existing screenshot:

```powershell
python main.py read --input captures\live_game.png
```

Capture and read gold, level, and HP in one step:

```powershell
python main.py capture-read --index 0 --output captures\reads --launch-if-needed
```

Get basic economy advice from an existing screenshot:

```powershell
python main.py advise --input captures\live_game.png --debug-output captures\debug
```

Capture and get advice in one step:

```powershell
python main.py capture-advise --index 0 --output captures\advice --launch-if-needed
```

Build the EXE:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

The built file will be:

```text
dist\Jkcheese.exe
```

Run the tests:

```powershell
python -m pip install -r requirements-dev.txt
py -3.14 -m pytest -q
```

## CI and releases

- `.github/workflows/ci.yml` runs tests on every push and pull request
- `.github/workflows/ci.yml` also performs a packaging smoke build
- `.github/workflows/release-build.yml` builds and uploads `Jkcheese.exe` when a GitHub release is published

## Current module

`v0.4.0` includes the first four modules:

- LDPlayer connection
- game launch
- screenshot pipeline
- simple end-user GUI
- 1920x1080 in-game region presets
- region crop export for gold, level, HP, traits, shop, bench, and opponents
- lightweight local digit OCR for gold, level, and HP
- confidence warnings, debug exports, and basic economy advice

## Next module

The next planned module is making advice richer:

- clearer rule tuning around stage and shop state
- OCR calibration samples
- shop card recognition experiments
