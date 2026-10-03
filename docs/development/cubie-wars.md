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
   It also accepts the new-warrior popup or the completed Story stage list.
   This option is for Story only; do not select it inside an Adventure stage.

On Windows, run OK-WW as Administrator and approve the Windows UAC prompt
yourself. Live input is blocked with an actionable error when OK-WW has no
administrator privileges. This prevents silent clicks against an elevated game;
input-free inspection still works without elevation.

During active Cubie Wars runs with the native PostMessage backend, a temporary
adapter brings the game to the foreground. Hover, clicks and held movement use
native input with coordinates converted through the capture's window offsets.
Held movement follows intermediate steps no longer than 16 screen pixels;
focus is checked before each step. No posted hover/button/activation messages
are mixed into this stream. Keyboard controls use the native cursor backend.
Keep the mouse free while it runs.
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

The recorded Story 1–3 tutorial highlights for Cube info, coins, shop items,
Sheets, Start, combat speed, trophies, retries, COST, refresh, synthesis offers,
and the selected Event are handled
before normal Store or combat actions. Each click requires both the instruction
text and a yellow border around the expected control. The speed click targets
the speed control inside the shared border with Pause. A missing border or three
clicks without advancing stops with a screenshot. The refresh border may join
the shop price line; Start's border may be clipped at the bottom of the viewport.
Both cases still require the visible straight yellow edges. Other tutorial
instructions still need observation and live validation.
The 10:22 Storage guide appeared during synthesis preparation: its initial
native capture was entirely blurred, with no readable UI. Eight bounded reads
allow a transient Unknown frame to settle before synthesis/shop checks. The
settled Displaying Storage Box page already classifies as Guide and returns to
the tutorial handler. No recipe or purchase is clicked while these reads remain
Unknown; a persistent Unknown still stops. Tests replay both actual frames.
The two drag instructions are introductory click-through overlays in the
recording: the highlighted shop item and then the Sheet are clicked before
normal purchasing begins. They do not initiate a purchase themselves.
Guide pages advance with D only when its navigation label is recognized;
Confirm takes precedence on the final page. The one-page Events and Selling
Items guides confirm directly. New Cubie Warrior popups are dismissed before
waiting for the stage list, with at most three attempts.

The task reads the stage list again after each attempt; it does not persist
assumed victories. Stage attempts, shop refreshes, and session duration have
limits. A changed layout, an unreadable value, an ambiguous purchase, or an
unconfirmed reward stops the task with a diagnostic screenshot.

The stage list uses grayscale OCR restricted to its label column.
This reads both white unselected labels and brown selected labels on gold;
the selected Story stage 5 was missed by full-screen OCR during live testing.

## Character and item references

The user supplied the player-character mapping below. Stage-list portraits are
not used to infer the player's character; the five Role Guide screenshots
confirm the character affinities. Adventure selects and verifies the stage's
character instead of always selecting Lynae. Story verifies its fixed character.

| Stage | Story | Adventure |
| --- | --- | --- |
| 1 | Rover / all weapon types | Rover / all weapon types |
| 2 | Aemeath / Rapier | Sigrika / Heavy Hitter |
| 3 | Hsin / Traumatizer | Hsin / Traumatizer |
| 4 | Sigrika / Heavy Hitter | Lynae / Gold Hunter |
| 5 | Lynae / Gold Hunter | Aemeath / Rapier |
| 6 | — | Lynae / Gold Hunter |

Resume from Store reads the active character by clicking the observed
Recommendation icon. The user clarified that pressing N does nothing; mouse
input is required. An enlarged caption crop handles labels missed by full OCR.
The selected header name and role must agree, excluding the other four sidebar
entries. Close the guide and return to Store before shopping. An already-open
guide is reopened by clicking Recommendation because the user may have selected
another entry.
Unreadable identity stops without assuming Rover or buying anything.

`src/task/cubie_wars/items.json` contains 126 definitions from the Collection
photos: 12 Sheets, 35 Weapons, 53 Accessories, 7 Relics, 19 Items. Names/roles and
all 35 weapon stat rows were visually checked. Four numeric OCR failures were
corrected from the source pixels; raw OCR and compact card crops remain in tests.
Thirteen measured title aliases handle actual split/extra-glyph OCR; matching
is exact after punctuation/spacing normalization, never fuzzy or truncated.
Missing metadata can be restored only when the visible item title and header
identify one entry. Conflicting readable roles, categories or stat values reject
the reference instead of overriding current game text. Prices and coins are
always read live. Absent nonweapon COST remains null in the source catalog;
the runtime keeps its existing zero-COST rule for Accessories/Relics/Items.
Seven descriptions are visibly clipped and are explicitly marked incomplete.

Core Item icons in the five guides were matched to Collection names. Prefer
those items within a category, retaining Sheet-first order and the thumb policy
for Accessories/Relics/Items. Rover's four core Weapons are the base variants;
the specialists' first core Weapons are Xtreme variants. This preference does
not require a completed illustrated build or guarantee a win.

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

- Hold the left mouse button to drag; **right-click** to rotate while holding.
  The user clarified that the earlier "R" meant the right mouse button, not
  keyboard R. Track buttons separately so releasing right keeps left held.
- A purchase is attempted only with a readable price, adequate coins, and a
  recognized tooltip. Sheet and Weapon offers may be purchased without a thumb;
  Accessory, Relic, and Item offers require a gold recommendation thumb.
  Weapon COST must fit the remaining capacity.
  Specialists reject Weapons from another specialist role; Adventurer Weapons
  remain usable. Rover accepts all weapon roles with equal affinity.
- Buy eligible items in this order: Sheet, Weapon, Accessory, Relic, Item.
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
- With no eligible purchase, refresh while coins cover the visible
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
- Test candidate positions in all four orientations, including empty tan
  sheet cells. Hold each position for up to three captures and release after
  two consecutive green previews with no red collision cells. On failure or
  Stop, return to the source and always release, even if that move fails.
  When every candidate ends with a red collision, try other recommendations;
  a successful sheet expansion also retries previously rejected items.
  Unreadable previews stop before refresh. Save bounded before/held board
  crops on failure so preview problems can be reproduced without the UID.
- The 05:23 native capture detected the middle offer's thumb, but contained no
  tooltip after a message-only hover. The temporary adapter moves the actual
  Windows cursor. Drag press, movement, and release now use native input as a
  pair, avoiding posted held-button flags combined with physically released
  mouse state. Release runs even after focus loss; posted mouse movement and
  activation are suppressed during the native drag. Read each
  offer's price before hovering and retry tooltip OCR for four fresh frames;
  tutorial interruptions return control to their handler. The 06:31 run
  confirms a Crystal purchase/placement with coins decreasing from 5 to 4.
  Other item shapes still require live validation.
- The user's held Crystal screenshot already passes the existing green mask:
  1208 green pixels and no red collision at 1920 pixels wide. It is a regression
  fixture at 1280/1920/2560, not proof that the bot's earlier captured preview
  matched the user's manual preview. Native drag and settling changes remain
  verified for Crystal in the 06:31 run. Tests cover a stale first frame, transient green,
  partial green plus red beyond the book, and retry after sheet expansion.
- The 06:07 live run saved the missing evidence: its centered Crystal hides
  the green ghost, yielding zero accepted green/red components despite being
  held above a free cell. The manual capture exposes the ghost with the icon
  slightly right and down. When centered previews remain unresolved, move
  24 pixels right/16 down, then 24 left/16 up (scaled from 1920x1080), within
  the same 102-pixel cell before rotating. Red collision previews skip these
  offsets. Stable green is still required; the 06:31 run confirms Crystal placement.
  Board-only before/held captures reproduce the missed preview in tests.

Sheet expansion now has a separate grid planner. Empty space for another
Sheet means bare board cells; an empty existing Sheet tile is still occupied
for expansion. The twelve supplied Collection Sheet footprints are verified
in the catalog. Check every footprint cell against the 8×6 board in each
distinct rotation, prefer positions adjacent to existing Sheets, and aim at
the whole shape's bounding-box center. Even-width shapes aim between cells.
The 10:44 board has 20 occupied and 28 blank cells; HP Bread Sheet (2×3) has
five valid geometric placements. Its preferred vertical plan starts at column
1, row 3, with cursor center (414,609) in the 1920×1080 viewport. Bright
obstructions are conservatively blocked. Unknown Sheet shapes retain probing
of bare cells with live green-preview verification. A nonempty geometric plan
whose preview fails is reported as unverifiable, not as proof of no space.

The 10:43/10:44 lost-HP-Bread errors were false detections: the Sheet was still
held, but actual OCR merged its control with the neighboring stamp as
`Rotate Sold`. At 1440p on October 4 the mouse glyph also became `1Rotate` or
`DRotate`; accept these observed icon prefixes and the combined label while
rejecting tutorial sentences. The preserved native capture reproduces the
error. Both geometric plans and combined-label handling remain subject to live
drop validation; two stable green previews and a coin decrease are required.

The 11:17 Empty Sheet capture exposed a separate preview issue: the Sheet
sprite hides most green fill, leaving long thin strips. The generic item
detector counted only 287 pixels, below its native threshold of 311, and lost
the strips entirely at 1440p. Known Sheet plans now require all footprint cells
blank, four new orange corners aligned to the commanded cursor and shape,
exposed changed green in multiple planned cells, and no meaningful red collision
(including thin red strips). The dragged sprite's bounding box plus a two-pixel
margin is excluded from green evidence so a green Rapier Sheet cannot prove
legality using its own color. Orange alone is never enough. This specialized
check also rejects stale previews at a previous target. Two consecutive held,
valid samples are still required before release, followed by live coin checks.
The preserved positive and below-board negative crops are tested at 720p,
1080p and 1440p; their unobserved exterior is explicitly zero-filled.

The October 4 capture shows a vertical HP Bread Sheet at a candidate intended
for its horizontal rotation, with red collision cells. The old code sent a
keyboard R instead of the mouse-right glyph shown by the game. Native right
press/release now rotates while preserving the held left button; interruption
cleanup releases every tracked button and restores the original backend.
- The 05:36 run confirms real hover opened the native "Random" Crystal card.
  Its Accessory label is below Adventurer, not beside it; read either layout
  without treating "Weapons" in the description as the category. A valid
  tooltip with the Store's capacity, Stage Details, and Storage Box is a
  separate item-tooltip state, even when it hides the round title. Resume
  clears that card before reading the round or taking shop actions.
- Try available yellow Synthesize buttons, bounded shop refreshes, and 2x
  combat speed. Adventure uses the stage-character mapping above; Story uses
  its fixed Cubie.
- Event cards prefer a visible recommendation thumb. If none is present, try
  each card's refresh once, stopping when a recommendation appears. If none
  appears, use the existing defensive-effect heuristic and confirm. The first
  tutorial's single mandatory Event is confirmed without refresh.
- The 06:31 run opened a Sword of Night synthesis modal after purchasing the
  Crystal, then failed reading book capacity hidden by that modal. Both modal
  and inline synthesis now click an observed yellow Synthesize button without
  reading capacity first. Return to the recognized Store before checking for
  a replacement weapon in Storage, even when its weight stays unchanged.
  Close modal recipes using their verified Click anywhere to close instruction;
  clear inline selections through the Storage area. Resume Story stage accepts
  an already-open synthesis panel. Capture/OCR fixtures cover the real modal;
  actual crafting and subsequent placement remain pending live validation.
  If a tutorial interrupts after an upgrade click, retain pending Storage
  restoration in the running task and retry it after Store is reacquired,
  before shopping or selecting another recipe. Verify Store before inspecting
  Storage so tutorial illustrations cannot be mistaken for stored weapons.
  This pending flag is in-process state and does not survive an app restart.
- Stop searching cells or rotating when three consecutive placement captures
  no longer show the held-item Rotate control. Cancel/return and release before
  reporting the lost drag; do not spend coins on refresh. Held movement now
  uses the same SendInput path as pressing, instead of SetCursorPos. The 10:21
  log confirms successful Sheet/Crystal purchases with the previous backend;
  this consistency change is not proof of the intermittent cause or a live fix.

## Current limitations / live validation still required

The 08:21 Story 2 capture exposed a right-hand Training Sword tooltip beyond
the previous OCR crop. Hover OCR now extends to x=.98 and uses confidence .65
to retain the native 2s value (measured .652). The DMG parser accepts the
crossed-swords icon read as XDMG. The actual old/new crop OCR is preserved in
`live_right_sword_ocr.json`; tests verify Weapon, DMG 6, interval 2s, COST 3
and the capacity guard before buying. Live purchase still needs verification.

- Tutorial popups, quick synthesis, discount OCR, item stacking and replacement,
  and event choices need live validation. The task currently adds items to free
  slots; it does not solve a global inventory rearrangement or replacement plan.
  Signature Weapon limits are separate from weight capacity; the planner does
  not yet model that counter. Placement still requires a valid green preview.
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
`tests/images/cubie_wars/tutorial/` contains the 31 additional Story 1–3
screenshots supplied by the user and their actual OCR output. Tests verify all
screen types, highlighted targets at three resolutions, single-page guides,
deferring shop resource reads under tutorials, and Event thumb/refresh choices.
`tests/images/cubie_wars/builds/` contains the five Role Guides and both stage
lists, with UID removed, plus actual OCR. Tests cross-check all selected header
roles and all 5/6 stage labels using the production grayscale OCR crop.
`tests/images/cubie_wars/collection/` preserves actual OCR for all 126 selected
item cards and five compact regression crops. Replay tests use these real title
and role detections to verify recovery when the tooltip stats are missing.
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
