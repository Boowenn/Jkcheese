# Jkcheese

`Jkcheese` is a read-only helper for Golden Spatula (`com.tencent.jkchess`) on LDPlayer.

Current module scope:

- detect LDPlayer instances
- check game install status
- launch the emulator
- launch the game
- capture emulator screenshots
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

`v0.1.0` is the first module:

- LDPlayer connection
- game launch
- screenshot pipeline
- simple end-user GUI

## Next module

The next planned module is in-game region presets for `1920x1080`, which will prepare:

- gold OCR
- level OCR
- HP OCR
- shop-area export
