# Jkcheese

`Jkcheese` is a read-only helper for Golden Spatula (`com.tencent.jkchess`) on LDPlayer.

Current module scope:

- detect LDPlayer instances
- check game install status
- launch the emulator
- launch the game
- capture emulator screenshots
- crop known in-game regions from screenshots
- read stage, gold, level, and HP from screenshots
- print confidence warnings and stage-aware economy rhythm advice
- export OCR debug crops for calibration
- fetch S-tier Golden Spatula lineups from the public `实时铲榜` Tencent Docs sheet
- recommend S-tier lineups from live card/name tokens
- track owned card copies and warn for cost-aware 4/5-cost star progress
- combine live tokens, owned cards, and current S-tier lineups into one core advice view
- scan shop slots, export shop debug crops, and recognize locally labeled shop templates
- recognize Chinese shop card names with local offline candidate OCR
- warn immediately when a shop card is a tracked two-star/three-star hit or S-lineup key card
- estimate 4-cost and 5-cost three-star chase odds from pool, owned copies, contested copies, level, and gold
- scout a manually opened opponent board from screenshots and count trained contested 4/5-cost targets
- suggest main carry, main tank, and item direction from real-time S-tier lineups, shop hits, tracked cards, and optional item components
- suggest when to level, save, small-D, or all-in from stage, level, gold, and HP
- provide a Chinese dashboard EXE with left-side screenshot status and right-side recommendation panels
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

The GUI is now the recommended beginner flow. Click `一键扫描当前局势` to capture the current emulator screen and refresh the right-side panels for current advice, S lineup recommendations, three-star/shop-hit warnings, chase odds, and item/main-carry reminders.

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

Read stage, gold, level, and HP from an existing screenshot:

```powershell
python main.py read --input captures\live_game.png
```

Capture and read stage, gold, level, and HP in one step:

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

Get stage-aware economy rhythm advice from manual values:

```powershell
python main.py tempo --stage 4-2 --level 8 --gold 34 --hp 45
```

Capture the current screen and get rhythm advice from OCR. If stage, gold, level, or HP OCR is unstable, pass manual overrides:

```powershell
python main.py capture-tempo --index 0 --stage 3-2 --gold 30
```

The rhythm engine is conservative and read-only. It suggests whether this is a better window to `升人口`, `存钱`, `小 D`, or `all in`, but it never clicks, buys, rolls, or changes the game.

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

Estimate whether a four/five-cost three-star chase is worth the gold:

```powershell
python main.py chase --name 千珏 --cost 4 --owned 8 --contested 0 --level 8 --gold 30
python main.py chase --name 五费主C --cost 5 --owned 6 --contested 2 --level 9 --gold 70 --cost-odds 15
```

The chase calculator is intentionally conservative: it reserves the gold needed to buy the remaining copies, then estimates how many rerolls and shop slots you can see. If your in-game probability bar differs from the default table, override it with `--cost-odds`.

When scanning the live shop, level and gold are read from the screenshot when possible. If OCR is not stable in a fight/shop state, pass them manually:

```powershell
python main.py capture-shop-scan --index 0 --owned 4费千珏x8 --level 8 --gold 30 --contested 千珏=1
```

Scout opponents after you manually switch to their board. First teach a tight visual template from a screenshot crop, then scan future opponent screenshots:

```powershell
python main.py scout-label --input captures\opponent.png --label 千珏:4@720,420,90,90
python main.py scout-scan --input captures\opponent.png --target 千珏
python main.py capture-scout --index 0 --target 千珏 --level 8 --gold 30
```

`capture-scout` only captures the current screen. It does not switch opponents, click the game, or read game memory. The output includes a `Contested 参数` line such as `千珏=2`, which can be used directly in the chase calculator.

Get main carry, main tank, and item direction from current S-tier lineups:

```powershell
python main.py item-advice --seen 新星 薇古丝 --shop 薇古丝 盖伦 --items 眼泪 眼泪 大棒 拳套
```

`item-advice` combines real-time S lineup ranking, current shop names, tracked owned copies, and optional item components. If no components are provided, it still shows recommended main C items, main tank items, and functional items. If components are provided, it marks which priority items can be made now and which component is missing.

`capture-shop-scan` also prints this item advice after scanning the shop:

```powershell
python main.py capture-shop-scan --index 0 --items 大剑 眼泪 拳套
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

`v0.13.2` includes the first twelve modules plus a usability fix pass:

- LDPlayer connection
- game launch
- screenshot pipeline
- simple end-user GUI
- module 12 Chinese dashboard layout with a left screenshot/status area and right recommendation panels
- 1920x1080 in-game region presets
- region crop export for gold, level, HP, traits, shop, bench, and opponents
- lightweight local digit OCR for stage, gold, level, and HP
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
- module 8 four/five-cost chase calculator with `chase`
- automatic chase estimates in `capture-shop-scan` and the GUI Scan Shop flow when level and gold OCR are readable
- module 9 opponent/card monitoring with `scout-label`, `scout-scan`, and `capture-scout`
- GUI Scout Opponent button for the board you manually opened
- module 10 equipment and main-carry reminders with `item-advice`
- GUI Item Advice entry/button and Scan Shop integration for S-lineup carry/tank/item direction
- module 11 stage/economy rhythm advice with `tempo` and `capture-tempo`
- GUI Tempo Advice button and Scan Shop rhythm integration for level/save/small-D/all-in suggestions
- one-click GUI scan that updates S lineup, star warnings, chase odds, item advice, tempo advice, and detailed logs together
- automatic in-game shop scanning for the GUI, using a reusable `_live` screenshot so background scans do not flood the disk
- right-top semi-transparent overlay for live "buy this slot", S lineup, chase risk, and tempo hints without switching away from the game
- click-through shop-slot highlight boxes that frame visible key cards directly over the LDPlayer shop when the window can be located
- draggable shop highlight calibration mode for misaligned overlays; turn it off after calibration to restore click-through play
- compact small-screen dashboard with a shorter default window, scrollable left column, and tighter right-side panels
- read-only live alerts only: the helper can tell you which visible slot to buy, but it never clicks, buys, rolls, or controls the game
- automatic capture cleanup: generated screenshots are retained briefly during a match, and when the match appears to end the tool clears match screenshots and resets match card counts
- single-instance GUI guard so double-clicking the EXE does not open two helper windows

## Next module

The next planned module is live calibration and dashboard polish:

- add easier in-GUI template labeling/calibration for shop and opponent scouting
- improve screenshot preview and panel wording from more live-game examples
- keep all behavior read-only
