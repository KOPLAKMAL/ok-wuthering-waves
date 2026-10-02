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

During active Cubie Wars runs with the native PostMessage backend, a temporary
adapter brings the game to the foreground and moves the real cursor through
the framework's PyDirect cursor method. Keep the mouse free while it runs.
The usual PostMessage backend is restored on completion, error, or Stop.
Inspection does not install this adapter or move the cursor.

The first Store phase waits for its round splash and observes again before
shopping. A delayed tutorial returns control to the tutorial handler. Unreadable
resources are retried a bounded number of times; they never default to zero.
Numeric crops are enlarged three times before OCR. The live 61×44 coin crop
returned no detections at its original size; the enlarged crop correctly reads
6 with the application's OCR settings. Discounted prices use a narrow crop of
the active price, excluding the crossed-out old price.
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
  recognized tooltip and a gold recommendation thumb above its price badge.
  Weapon COST must fit the remaining capacity.
- Buy recommended items in this order: Weapon, Sheet, Accessory, Relic, Item.
  Within a category, rank by damage per attack interval, role, and defensive
  effects. An unknown category is skipped. The thumb is detected before
  hovering so tooltips do not obscure it.
- Thumb detection searches multiple icon sizes and closes small antialiasing
  gaps. Native captures of the first Story round have smaller hands than the
  recording; both recording and native thumb shapes are reference assets.
  Recheck an empty scan after animation delays before refreshing. Unresolved
  gold marks and unreadable marked offers stop before refresh spending instead
  of being treated as absent recommendations. Save up to 20 compact offer
  captures per run to diagnose the exact scanned frames.
- With no eligible recommended purchase, refresh while coins cover the visible
  refresh price and the configured refresh limit permits it. Verify that the
  coin decrease equals the refresh price, then scan the new offers. Start combat
  when no further purchases or refreshes are possible within those limits.
- Read Start in an enlarged crop of its label and require the Store screen.
  Full-screen OCR read the live label as `Stari`. After clicking the verified
  button, require Matching, combat, or the next tutorial to appear.
- Recheck for a late tutorial before a purchase or refresh and after refresh.
  The round-two coin-carryover highlight uses the same verified coin border.
  When combat shows 1x or 1.5x, advance and observe until 2x; never click 2x,
  which would cycle back. Stop if three clicks do not advance the control.
- Test candidate positions in all four orientations. Release only after a
  green placement preview with no red collision cells. On failure or Stop,
  return to the source and release the mouse.
- The 05:23 native capture detected the middle offer's thumb, but contained no
  tooltip after a message-only hover. The temporary adapter moves the actual
  Windows cursor, preserves MK_LBUTTON on drag motion, and releases at the
  last target rather than the framework's unchanged (0, 0) position. Read each
  offer's price before hovering and retry tooltip OCR for four fresh frames;
  tutorial interruptions return control to their handler. Live purchase and
  drag still need validation with this adapter.
- The 05:36 run confirms real hover opened the native "Random" Crystal card.
  Its Accessory label is below Adventurer, not beside it; read either layout
  without treating "Weapons" in the description as the category. A valid
  tooltip with the Store's capacity, Stage Details, and Storage Box is a
  separate item-tooltip state, even when it hides the round title. Resume
  clears that card before reading the round or taking shop actions.
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
The thumb asset and Store fixtures also come from the recording. Native-size
coin and price crops reproduce the live OCR failure and its correction with the
same OCR settings as the application; these tests still do not prove live input
or a stage win.
Native Store PNGs reproduce the two smaller thumbs, both during the refresh
animation and after it settles, with the user-ID strip removed. Tests preserve
the distinction between thumbs and gold price-badge borders, and verify an
attempt with the last coin before any refresh.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cubie_wars.py -q -p no:cacheprovider
```

These checks cover screen recognition, reward planning, collision/claim
recognition, capacity limits, releasing input on cancellation, and the
input-free inspection mode. They do not establish live-game success.
