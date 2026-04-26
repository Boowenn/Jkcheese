# Jkcheese

`Jkcheese` is a read-only helper for Golden Spatula (`com.tencent.jkchess`) on LDPlayer.

Current module scope:

- detect LDPlayer instances
- check game install status
- launch the emulator
- launch the game
- capture emulator screenshots
- crop known in-game regions from screenshots
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

`v0.2.0` includes the first two modules:

- LDPlayer connection
- game launch
- screenshot pipeline
- simple end-user GUI
- 1920x1080 in-game region presets
- region crop export for gold, level, HP, traits, shop, bench, and opponents

## Next module

The next planned module is OCR over the cropped regions, starting with:

- gold OCR
- level OCR
- HP OCR
- shop card text/image recognition experiments
