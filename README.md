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
- fetch S-tier Golden Spatula lineups from the public `实时铲榜` Tencent Docs sheet
- recommend S-tier lineups from live card/name tokens
- track owned card copies and warn for cost-aware 4/5-cost star progress
- combine live tokens, owned cards, and current S-tier lineups into one core advice view
- scan shop slots, export shop debug crops, and recognize locally labeled shop templates
- recognize Chinese shop card names with local offline candidate OCR
- warn immediately when a shop card is a tracked two-star/three-star hit or S-lineup key card
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

Fetch current S-tier Golden Spatula lineups from `实时铲榜`:

```powershell
python main.py lineups
```

Recommend from S-tier lineups using live card/name tokens:

```powershell
python main.py recommend-lineup --seen 机甲 远征
```

Get the core advice loop with S-tier recommendations and star warnings:

```powershell
python main.py core-advice --seen 机甲 远征 --owned 4费薇古丝x7 --reset
```

Track additional owned copies during the same game:

```powershell
python main.py core-advice --seen 机甲 --owned 4费薇古丝x1
```

The card tracker understands cost-aware forms such as `4费薇古丝x7`, `五费安妮=3`, `4费 薇古丝x7`, and `薇古丝@4x7`. By default, star warnings focus on 4-cost and 5-cost units because they are the most valuable and scarce three-star targets.

Default public pool sizes are `1:30,2:25,3:18,4:10,5:9`. If the current Golden Spatula season uses a different bag size, override it:

```powershell
python main.py core-advice --owned 4费薇古丝x7 --pool-sizes 1:29,2:22,3:16,4:12,5:10
```

Clear the local card count tracker between games:

```powershell
python main.py reset-cards
```

Scan shop slots from an existing screenshot:

```powershell
python main.py shop-scan --input captures\live_game.png
```

Teach local templates from a screenshot, then scan again:

```powershell
python main.py shop-label --input captures\live_game.png --label 2=丽桑卓:1 5=雷克塞:1
python main.py shop-scan --input captures\live_game.png
```

The first scan can show `occupied unknown` for cards that have not been labeled yet. This is expected: module 7 learns local visual templates from your own screenshots so it can recognize the same card art later without external OCR services.

Capture the current emulator screen, scan the shop, and feed recognized shop names into S-tier lineup advice:

```powershell
python main.py capture-shop-scan --index 0 --launch-if-needed
```

Trigger a shop-hit reminder from your tracked copies, for example when buying the visible card would complete a three-star:

```powershell
python main.py capture-shop-scan --index 0 --launch-if-needed --owned 卡莎@3x8 --reset
```

Module 7 uses two local recognition paths: labeled card-art templates first, then offline Chinese name OCR from a candidate list. You can extend the OCR candidates without changing code by creating `captures\champions.json`:

```json
{"champions": [{"name": "自定义棋子"}]}
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

`v0.8.0` includes the first seven modules plus shop-hit reminders:

- LDPlayer connection
- game launch
- screenshot pipeline
- simple end-user GUI
- 1920x1080 in-game region presets
- region crop export for gold, level, HP, traits, shop, bench, and opponents
- lightweight local digit OCR for gold, level, and HP
- confidence warnings, debug exports, and basic economy advice
- read-only `实时铲榜` S-tier lineup fetching and token-based S lineup recommendation
- card count tracking for owned copies
- cost-aware pair, two-star, four/five-copy, seven/eight-copy, and three-star warnings
- default 4/5-cost focus so low-cost shop noise does not drown out real win-condition alerts
- a GUI core helper panel for live tokens, owned copies, S-line recommendations, and upgrade warnings
- shop slot occupancy detection
- shop cost digit reading
- local card-template labeling and recognition with `shop-label`, `shop-scan`, and `capture-shop-scan`
- offline Chinese shop-name OCR for common champion names
- shop-hit alerts that say when to buy a visible card because it completes a two-star, pushes a four/five-cost chase, or matches an S-tier lineup
- GUI Scan Shop button that feeds recognized shop names into the S-line recommendation flow

## Next module

The next planned module is the four/five-cost chase calculator and richer game-state awareness:

- estimate whether a 4-cost or 5-cost three-star chase is realistic from level, gold, owned copies, and suspected contested copies
- add opponent/contested-card screenshot checks
- add main carry/tank and item reminders from the current S-lineup source
- add stage and economy rhythm suggestions
- simplify the Chinese EXE layout into a left screenshot status / right recommendation dashboard
- keep all behavior read-only
