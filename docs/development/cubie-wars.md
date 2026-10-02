# Cubie Wars Astrite task (experimental)

The task targets Astrite, not the 22/22 goal counter or spending 4500/4500
Backstage Store currency. It has not yet passed a live, complete gameplay run.
The shop policy is a heuristic and does not guarantee a stage win.

## Starting

1. Use the English game UI in a 16:9 window, at least 1280 pixels wide.
2. Unlock the event yourself and open its menu showing **Story Mode** and
   **Adventure Mode**. World quests and travel are outside this task.
3. Select **Cubie Wars (Experimental)** in OK-WW.
4. Start with **Inspect screen**. This mode records the recognized screen and
   saves a screenshot without sending mouse or keyboard input.
5. Use **Astrite run** to attempt uncleared stages and claim rewards, or
   **Claim rewards only** after playing the stages yourself.
6. If a Story stage is already open, **Resume Story stage** resumes its tutorial,
   Store, or combat before checking the stage list and continuing the Astrite run.
   This option is for Story only; do not select it inside an Adventure stage.

On Windows, run OK-WW as Administrator and approve the Windows UAC prompt
yourself. Live input is blocked with an actionable error when OK-WW has no
administrator privileges. This prevents silent clicks against an elevated game;
input-free inspection still works without elevation.

The first Store phase waits for its round splash and observes again before
shopping. A delayed tutorial returns control to the tutorial handler. Unreadable
resources are retried a bounded number of times; they never default to zero.
If a small crop misses a number, the task accepts a single complete numeric
label from full-screen OCR inside the same resource region. Tutorials take
precedence over this fallback.

The recorded tutorial highlights for coins, the shop item, the destination
Sheet, Start, and combat speed are handled
before normal Store or combat actions. Each click requires both the instruction
text and a yellow border around the expected control. The speed click targets
the speed control inside the shared border with Pause. A missing border or three
clicks without advancing stops with a screenshot. Other tutorial instructions
still need observation and live validation.
The two drag instructions are introductory click-through overlays in the
recording: the highlighted shop item and then the Sheet are clicked before
normal purchasing begins. They do not initiate a purchase themselves.

The task reads the stage list again after each attempt; it does not persist
assumed victories. Stage attempts, shop refreshes, and session duration have
limits. A changed layout, an unreadable value, an ambiguous purchase, or an
unconfirmed reward stops the task with a diagnostic screenshot.

The stage list uses grayscale OCR restricted to its label column.
This reads both white unselected labels and brown selected labels on gold;
the selected Story stage 5 was missed by full-screen OCR during live testing.

## Reward target verified from the reference recording

| Source | Astrite | Required progress |
| --- | ---: | --- |
| Progress goals | 200 | Story stages 1–5 |
| Challenge goals | 300 | Adventure stages 1–6, 50 each |
| Cube goals | 200 | A win with each of Rover, Aemeath, Hsin, Sigrika, Lynae |
| Badge milestones | 200 | 250 badges: 80; 750 badges: 120 |
| Backstage Store | 300 | Two 50 offers at 200 currency; two 100 offers at 500 currency |
| **Total** | **1200** | |

Adventure stage 6's **stage reward** is event currency, but its **Challenge
goal** grants 50 Astrite. It must not be skipped based on the stage reward icon.
The remaining goal “Win the final Round while carrying 2 Red Items” has no
Astrite reward and is not pursued. Non-Astrite store items are not purchased.

## Input and shopping

- Hold the left mouse button to drag; press **R** to rotate while holding.
- A purchase is attempted only with a readable price, adequate coins, and a
  recognized tooltip. Weapon COST must fit the remaining capacity.
- Rank items by damage per attack interval, character role, and defensive
  effects. Prefer Sheets when few empty cells remain.
- Test candidate positions in all four orientations. Release only after a
  green placement preview with no red collision cells. On failure or Stop,
  return to the source and release the mouse.
- Try available yellow Synthesize buttons, bounded shop refreshes, and 2x
  combat speed. Adventure currently selects Lynae; Story uses its fixed Cubie.

## Current limitations / live validation still required

- Tutorial popups, quick synthesis, discount OCR, item stacking and replacement,
  and event choices need live validation. The task currently adds items to free
  slots; it does not solve a global inventory rearrangement or replacement plan.
- Stage 6 can fail even with legal placements. Stop on the configured attempt
  limit and inspect the build; an offline test does not prove a winning strategy.
- English is the only observed game language. Translated application labels do
  not imply recognition of a translated game interface.
- If an Astrite Cube goal remains despite cleared Story stages, the reward
  check stops; it does not automatically replay an already cleared stage.
- Captures use the existing framework. No game-memory access is added.

## Recording evidence and checks

The supplied AV1 MKV is 2560×1440, 60 fps, 2:22:54.954. Useful timestamps:
Story tutorial 01:40–06:00; first stage result 07:50; Adventure stage 6's pending
50-Astrite goal 1:38:30; completed Adventure list 2:21:48; store 2:21:51 onward;
goal receipts 2:22:32 / **2:22:34.2 (300 Astrite)** / 2:22:36; milestones 2:22:43;
claimed ticks 2:22:44. Mouse controls were confirmed separately by the user.

`tests/images/cubie_wars/ocr.json` contains actual OCR output from selected
recording frames, not hand-written ideal labels. Small JPEG replay fixtures
have the user-ID strip removed. The claimed-check asset comes from the same
recording. The video, account configuration, caches, and runtime logs are not
part of the feature.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cubie_wars.py -q -p no:cacheprovider
```

These checks cover screen recognition, reward planning, collision/claim
recognition, capacity limits, releasing input on cancellation, and the
input-free inspection mode. They do not establish live-game success.
