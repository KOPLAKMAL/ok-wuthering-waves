import re
import time

from ok.util.process import is_admin

from src.task.BaseWWTask import BaseWWTask
from src.task.WWOneTimeTask import WWOneTimeTask
from src.task.cubie_wars.model import (
    ADVENTURE_COUNT, CUBES, MILESTONES, STORY_COUNT, STORE_OFFERS,
    Screen, Text, classify, joined, next_stage, parse_item, spotlight_instruction,
)
from src.task.cubie_wars.vision import (
    capacity_tag, green_check, number_frame, placement_points, recipe_available, recommended_item,
    spotlight_target, stage_label_frame, valid_preview, white_check, yellow_button,
)


class ShopInterrupted(Exception):
    """A tutorial appeared after the round's Store animation."""


class CubieWarsTask(WWOneTimeTask, BaseWWTask):
    """Experimental English Cubie Wars task; never treats an unknown screen as success."""

    SHOP_SLOTS = ((.636, .278), (.766, .278), (.895, .278), (.636, .526), (.766, .526))
    CUBE_POSITIONS = (.075, .188, .30, .412, .524)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Cubie Wars (Experimental)"
        self.description = "Open the Cubie Wars menu first. English game UI, 16:9. Targets Astrite rewards."
        self.default_config = {
            "Mode": "Inspect screen",
            "Stage attempts": 3,
            "Refreshes per round": 4,
            "Session minutes": 180,
        }
        self.config_type = {"Mode": {"type": "drop_down", "options": [
            "Inspect screen", "Astrite run", "Claim rewards only", "Resume Story stage"]}}
        self.config_description = {
            "Mode": "Inspect screen saves a screenshot without clicking. Astrite run plays stages and claims rewards.",
            "Stage attempts": "Stop after this many failed attempts at one stage.",
            "Refreshes per round": "Maximum shop refreshes in each round.",
            "Session minutes": "Maximum running time before stopping.",
        }
        self.support_schedule_task = False
        self._texts = []
        self._role = "Adventurer"
        self._deadline = 0
        self._spotlight_attempts = {}

    def validate_config(self, key, value):
        limits = {"Stage attempts": (1, 10), "Refreshes per round": (0, 20), "Session minutes": (1, 360)}
        if key in limits and not limits[key][0] <= value <= limits[key][1]:
            return f"Choose a value between {limits[key][0]} and {limits[key][1]}"
        return None

    def run(self):
        # Inspection is deliberately input-free, including the usual mouse reset.
        self._deadline = time.monotonic() + self.config.get("Session minutes", 180) * 60
        self._spotlight_attempts = {}
        screen = self.observe()
        if self.config.get("Mode") == "Inspect screen":
            self.screenshot("cubie-wars-inspection")
            self.log_info(f"Cubie Wars screen: {screen.value}", notify=True)
            return
        if abs(self.width / self.height - 16 / 9) > .02 or self.width < 1280:
            self.stop_with_evidence("Cubie Wars currently requires a 16:9 game window at least 1280 pixels wide")
        resume_story = self.config.get("Mode") == "Resume Story stage"
        if resume_story:
            if screen not in {Screen.GUIDE, Screen.SPOTLIGHT, Screen.DETAILS, Screen.SHOP, Screen.MATCHING,
                              Screen.COMBAT, Screen.ROUND_RESULT, Screen.STAGE_RESULT, Screen.EVENT}:
                self.stop_with_evidence("Open the active Story stage before choosing Resume Story stage")
        elif screen != Screen.HUB:
            self.stop_with_evidence("Open the Cubie Wars Story Mode / Adventure Mode menu before starting")
        if not self.is_browser() and not is_admin():
            self.stop_with_evidence("Restart OK-WW as Administrator using Start Cubie Wars.cmd, then approve Windows UAC")
        WWOneTimeTask.run(self)
        if resume_story:
            self.play_stage("Story")
            self.wait_screen({Screen.STAGES})
            self.close_page()
        if resume_story or self.config.get("Mode") == "Astrite run":
            for mode in ("Story", "Adventure"):
                self.complete_mode(mode)
        self.claim_rewards()

    def observe(self):
        if self._deadline and time.monotonic() > self._deadline:
            self.stop_with_evidence("Cubie Wars session time limit reached; progress has been kept by the game")
        self.next_frame()
        boxes = self.ocr(frame=self.frame, threshold=.65, target_height=1080)
        self._texts = [Text(b.name, b.x / self.width, b.y / self.height,
                            b.width / self.width, b.height / self.height) for b in boxes]
        screen = classify(self._texts)
        self.info_set("Cubie Wars screen", screen.value)
        return screen

    def stop_with_evidence(self, reason):
        self.screenshot("cubie-wars-needs-attention")
        raise RuntimeError(reason)

    def wait_screen(self, expected, timeout=20):
        expected = set(expected)
        deadline = min(self._deadline, time.monotonic() + timeout)
        while time.monotonic() < deadline:
            screen = self.observe()
            if screen in expected:
                return screen
            self.sleep(.5)
        self.stop_with_evidence("Cubie Wars screen did not change to " + ", ".join(s.value for s in expected))

    def text(self, pattern, region=(0, 0, 1, 1)):
        x, y, right, bottom = region
        return next((t for t in self._texts if x <= t.center[0] <= right
                     and y <= t.center[1] <= bottom
                     and re.search(pattern.replace(" ", r"\s*"), t.name, re.I)), None)

    def click_text(self, pattern, region=(0, 0, 1, 1)):
        target = self.text(pattern, region)
        if not target:
            self.stop_with_evidence(f"Cubie Wars button not recognized: {pattern}")
        self.click_relative(*target.center, after_sleep=.6)

    def close_page(self, expected=Screen.HUB):
        self.click_relative(.943, .06, after_sleep=.6)
        self.wait_screen({expected})

    def complete_mode(self, mode):
        self.wait_screen({Screen.HUB})
        self.click_text(mode + r" Mode$", (.2, .5, .85, .8))
        self.wait_screen({Screen.STAGES})
        failures = {}
        count = STORY_COUNT if mode == "Story" else ADVENTURE_COUNT
        for _ in range(count * (self.config.get("Stage attempts", 3) + 1)):
            checks, rows = self.stage_checks(count)
            stage = next_stage(mode, checks)
            if stage is None:
                self.close_page()
                return
            self.info_set("Cubie Wars stage", f"{mode} {stage}")
            self.log_info(f"Cubie Wars: {mode} stage {stage}")
            self.click_relative(*rows[stage].center, after_sleep=.6)
            self.wait_screen({Screen.STAGES})
            self.click_text(r"^Go$", (.7, .8, 1, 1))
            self.play_stage(mode)
            self.wait_screen({Screen.STAGES})
            after, _ = self.stage_checks(count)
            if not after[stage]:
                failures[stage] = failures.get(stage, 0) + 1
                if failures[stage] >= self.config.get("Stage attempts", 3):
                    self.stop_with_evidence(f"{mode} stage {stage} still incomplete after {failures[stage]} attempts")
        self.stop_with_evidence("Stage selection made no verifiable progress")

    def stage_checks(self, count):
        if self.observe() != Screen.STAGES:
            self.stop_with_evidence("Expected the Cubie Wars stage list")
        # Full-screen OCR misses the dark selected label on its gold background.
        # Restrict detection to the text column, excluding portraits and ticks.
        labels = self.ocr(.085, .2, .14, .9, frame=self.frame, threshold=.65,
                          target_height=2160, frame_processor=stage_label_frame)
        rows = {}
        for label in labels:
            t = Text(label.name, label.x / self.width, label.y / self.height,
                     label.width / self.width, label.height / self.height)
            match = re.fullmatch(r"Stage\s*([1-6])", t.name.strip(), re.I)
            if match and t.center[0] < .18:
                rows[int(match[1])] = t
        if set(rows) != set(range(1, count + 1)):
            self.stop_with_evidence("Could not read every Cubie Wars stage in the list")
        return {n: green_check(self.frame, .149, t.center[1]) for n, t in rows.items()}, rows

    def play_stage(self, mode):
        unknown_since = time.monotonic()
        last_shop = None
        for _ in range(1000):
            screen = self.observe()
            if screen != Screen.UNKNOWN:
                unknown_since = time.monotonic()
            elif time.monotonic() - unknown_since > 45:
                self.stop_with_evidence("Unrecognized Cubie Wars screen during a stage")
            if screen == Screen.SPOTLIGHT:
                self.handle_spotlight()
            elif screen == Screen.GUIDE:
                if self.text(r"^Confirm$", (.3, .8, .7, 1)):
                    self.click_text(r"^Confirm$", (.3, .8, .7, 1))
                else:
                    self.click_relative(.745, .806, after_sleep=.5)
            elif screen == Screen.DETAILS:
                self.click_relative(.935, .19, after_sleep=.6)
            elif screen == Screen.CUBE:
                if mode == "Adventure":
                    # Lynae's Gold Hunter build was observed winning the final
                    # stage in the reference recording. Confirm her name first.
                    self.click_relative(self.CUBE_POSITIONS[4], .914, after_sleep=.6)
                    self.wait_screen({Screen.CUBE})
                    if not self.text(r"Lynae", (.65, .08, 1, .25)):
                        self.stop_with_evidence("Lynae could not be selected")
                self._role = next((role for name, role in zip(CUBES, (
                    "Adventurer", "Rapier", "Traumatizer", "Heavy Hitter", "Gold Hunter"))
                    if self.text(name, (.65, .08, 1, .25))), "Adventurer")
                self.click_text(r"^G[o0C]$", (.65, .8, 1, 1))
            elif screen == Screen.SHOP:
                round_text = self.text(r"Round\s*\d+.*Store", (.55, .09, .8, .2)).name
                if last_shop == round_text:
                    self.stop_with_evidence("The prepared round did not start")
                try:
                    if not self.prepare_round():
                        continue
                except ShopInterrupted:
                    continue  # Re-enter the tutorial branch on the next observation.
                prepared_screen = self.observe()
                if prepared_screen in {Screen.GUIDE, Screen.SPOTLIGHT}:
                    continue
                if prepared_screen != Screen.SHOP:
                    self.stop_with_evidence("Shop layout changed during preparation")
                self.click_text(r"^Start$", (.8, .8, 1, .95))
                last_shop = round_text
            elif screen == Screen.COMBAT:
                if self.text(r"1[.,]0\s*[Xx]", (.85, .12, .98, .22)):
                    self.click_relative(.933, .177, after_sleep=.5)
                self.sleep(1)
            elif screen == Screen.MATCHING:
                self.sleep(1)
            elif screen == Screen.ROUND_RESULT:
                self.click_relative(.5, .9, after_sleep=.7)
                last_shop = None
            elif screen == Screen.EVENT:
                self.choose_event()
            elif screen == Screen.STAGE_RESULT:
                self.click_text(r"^Back$", (.6, .8, .81, 1))
                return
            else:
                self.sleep(.5)
        self.stop_with_evidence("Cubie Wars stage action limit reached")

    def number(self, region, fraction=False):
        pattern = r"(\d+)\s*/\s*(\d+)" if fraction else r"\d+"
        for attempt in range(4):
            boxes = self.ocr(*region, threshold=.65, frame_processor=number_frame)
            text = " ".join(b.name for b in boxes)
            match = re.search(pattern, text)
            if match:
                return (int(match[1]), int(match[2])) if fraction else int(match[0])
            if self.observe() in {Screen.GUIDE, Screen.SPOTLIGHT}:
                raise ShopInterrupted()
            # Small crops sometimes fail to detect a single digit although
            # full-screen OCR can read it. Keep the same positional constraint
            # and require a complete numeric label before using that fallback.
            x, y, right, bottom = region
            values = [re.fullmatch(pattern, t.name.strip()) for t in self._texts
                      if x <= t.center[0] <= right and y <= t.center[1] <= bottom]
            values = [value for value in values if value]
            if len(values) == 1:
                match = values[0]
                return (int(match[1]), int(match[2])) if fraction else int(match[0])
            if attempt < 3:
                self.sleep(.35)
        self.stop_with_evidence(f"Cubie Wars resource value is unreadable: {region}")

    def coins(self):
        return self.number((.934, .121, .966, .162))

    def prepare_round(self):
        # The first-time tutorial opens after the initial round splash. Observe
        # again after it settles, before reading resources or touching items.
        self.sleep(1.5)
        if self.observe() != Screen.SHOP:
            return False
        self.synthesize()
        for refresh in range(self.config.get("Refreshes per round", 4) + 1):
            skipped = set()
            for _ in range(len(self.SHOP_SLOTS)):
                self.move_relative(.55, .78)
                self.sleep(.25)
                self.next_frame()
                coins = self.coins()
                used, maximum = self.number((.139, .103, .178, .139), fraction=True)
                free = len(placement_points(self.frame))
                offers = []
                recommended = [recommended_item(self.frame, (x, .392 if index < 3 else .64))
                               for index, (x, _) in enumerate(self.SHOP_SLOTS)]
                for index, (x, y) in enumerate(self.SHOP_SLOTS):
                    if index in skipped or not recommended[index]:
                        continue
                    self.move_relative(x, y)
                    self.sleep(.4)
                    self.next_frame()
                    price_y = .392 if index < 3 else .64
                    price_boxes = self.ocr(x - .015, price_y - .021, x + .007, price_y + .02,
                                           threshold=.65, frame_processor=number_frame)
                    price_text = " ".join(b.name for b in price_boxes)
                    price_match = re.fullmatch(r"\s*(\d{1,2})\s*", price_text)
                    if not price_match:
                        continue  # Sold, empty, or an unreadable discounted price.
                    price = int(price_match[1])
                    if not 0 < price <= coins:
                        continue
                    tooltip_boxes = self.ocr(.2, .075, .68, .7, threshold=.7)
                    tooltip = [Text(b.name, b.x / self.width, b.y / self.height,
                                    b.width / self.width, b.height / self.height) for b in tooltip_boxes]
                    item = parse_item(tooltip)
                    if item:
                        rank = item.purchase_rank(self._role, maximum - used, free, price)
                        if rank is not None:
                            offers.append((rank, index, item))
                if not offers:
                    break
                _, index, item = max(offers, key=lambda offer: offer[0])
                skipped.add(index)
                self.move_relative(.55, .78)
                self.sleep(.25)
                self.next_frame()
                baseline = self.frame.copy()
                before = self.coins()
                placed = self.drag_to_book(self.SHOP_SLOTS[index], baseline, item.sheet)
                self.sleep(.4)
                self.next_frame()
                after = self.coins()
                if placed:
                    if after >= before:
                        self.stop_with_evidence("Item placement was not confirmed by a coin decrease")
                    self.log_info(f"Cubie Wars: placed {item.name}, spent {before - after} coins")
                    self.synthesize()
                elif after != before:
                    self.stop_with_evidence("Cancelled drag changed coins; check the Storage Box before continuing")
            if refresh < self.config.get("Refreshes per round", 4):
                self.move_relative(.55, .78)
                self.sleep(.25)
                self.next_frame()
                before = self.coins()
                refresh_price = self.number((.899, .621, .921, .658))
                if not 0 < refresh_price <= 20:
                    self.stop_with_evidence('Cubie Wars shop refresh price is invalid')
                if before < refresh_price:
                    break
                self.click_relative(.895, .574, after_sleep=.5)
                self.next_frame()
                if self.coins() != before - refresh_price:
                    self.stop_with_evidence("Shop refresh coin change did not match its price")
        return True

    def handle_spotlight(self):
        instruction = spotlight_instruction(self._texts)
        if not instruction:
            self.stop_with_evidence("Cubie Wars tutorial instruction was not recognized")
        pattern, anchor = instruction
        target = spotlight_target(self.frame, anchor)
        if target is None:
            self.stop_with_evidence("Cubie Wars tutorial yellow border was not recognized")
        attempts = self._spotlight_attempts.get(pattern, 0)
        if attempts >= 3:
            self.stop_with_evidence("Cubie Wars tutorial did not advance after three highlighted clicks")
        self._spotlight_attempts[pattern] = attempts + 1
        self.log_info(f"Cubie Wars: clicking tutorial highlight at {target}")
        self.click_relative(*target, after_sleep=.7)

    def drag_to_book(self, source, baseline, sheet=False):
        points = placement_points(baseline, sheet)
        if not points:
            return False
        self.mouse_down(round(source[0] * self.width), round(source[1] * self.height))
        placed = False
        try:
            self.sleep(.15)
            for rotation in range(4):
                for point in points:
                    if self._deadline and time.monotonic() > self._deadline:
                        self.stop_with_evidence("Cubie Wars session time limit reached during placement")

                    self.move_relative(*point)
                    self.sleep(.12)
                    self.next_frame()
                    if valid_preview(baseline, self.frame):
                        placed = True
                        return True
                self.send_key('r')
                self.sleep(.12)
            return False
        finally:
            # Return to the shop source if no valid ghost was seen. Never drop
            # blindly, and always release even when Stop interrupts a drag.
            if not placed:
                self.move_relative(*source)
            self.mouse_up()

    def synthesize(self):
        for _ in range(8):
            self.move_relative(.55, .78)
            self.sleep(.2)
            self.next_frame()
            recipes = [y for y in (.267, .361, .455, .549) if recipe_available(self.frame, y)]
            synthesized = False
            for y in recipes:
                # The observed recipes are circular icons in the left margin;
                # selecting one exposes a yellow button over its ingredients.
                self.click_relative(.058, y, after_sleep=.35)
                self.observe()
                button = next((t for t in self._texts if re.fullmatch(r"Synthesize", t.name, re.I)
                               and .11 < t.center[0] < .98 and .15 < t.center[1] < .75
                               and yellow_button(self.frame, t.center)), None)
                if not button:
                    continue
                used, _ = self.number((.139, .103, .178, .139), fraction=True)
                self.click_relative(*button.center, after_sleep=.5)
                self.move_relative(.55, .78)
                self.sleep(.2)
                self.next_frame()
                current, _ = self.number((.139, .103, .178, .139), fraction=True)
                if current < used:
                    self.restore_storage()
                self.info_incr("Cubie Wars synthesis attempts")
                synthesized = True
                break
            if not synthesized:
                break
        self.move_relative(.55, .78)
        self.click_relative(.55, .78, after_sleep=.2)

    def restore_storage(self):
        """A synthesis can leave the larger replacement weapon in Storage."""
        for _ in range(6):
            self.next_frame()
            baseline = self.frame.copy()
            tags = self.ocr(.22, .71, .8, .97, match=re.compile(r"^\d+$"), threshold=.7)
            sources = [(b.center()[0] / self.width, b.center()[1] / self.height) for b in tags]
            sources = [p for p in sources if capacity_tag(baseline, p)]
            if not sources:
                return
            used, _ = self.number((.139, .103, .178, .139), fraction=True)
            if not self.drag_to_book(sources[0], baseline):
                self.stop_with_evidence("Synthesized weapon is in Storage and does not fit; rearrange the book")
            self.sleep(.3)
            self.next_frame()
            after, _ = self.number((.139, .103, .178, .139), fraction=True)
            if after <= used:
                self.stop_with_evidence("Could not confirm the synthesized weapon returned to the book")

    def choose_event(self):
        # Inspect all three descriptions and prefer survivability over a random
        # item. This is a heuristic, not a guarantee of winning the round.
        candidates = []
        for x in (.26, .5, .74):
            text = joined([t for t in self._texts if x - .1 < t.center[0] < x + .1])
            score = sum(text.lower().count(word) * weight for word, weight in (
                ("shield", 5), ("heal", 5), ("max hp", 4), ("gold", 2), ("coin", 2), ("random", -1)))
            candidates.append((score, x))
        self.click_relative(max(candidates)[1], .5, after_sleep=.3)
        self.observe()
        self.click_text(r"^Confirm$", (.3, .75, .8, 1))

    def claim_rewards(self):
        self.wait_screen({Screen.HUB})
        self.claim_store()
        self.wait_screen({Screen.HUB})
        self.click_text(r"Adventure [GC]oals", (0, .75, .4, 1))
        self.wait_screen({Screen.GOALS})
        pending = self.claim_goals()
        if pending:
            self.stop_with_evidence("Astrite goals still incomplete: " + ", ".join(sorted(pending)))
        # Both Astrite milestones must show a claimed check. 22/22 goals and
        # 4500/4500 store spending are intentionally not completion conditions.
        self.observe()
        for x in (.623, .818):
            if not white_check(self.frame, (x, .814)):
                self.stop_with_evidence("Astrite milestone claim could not be verified")
        self.close_page()
        self.log_info("Cubie Wars Astrite reward checks passed. Non-Astrite goals were not required.", notify=True)

    def claim_store(self):
        self.click_text(r"Backstage Store", (0, .7, .3, .95))
        self.wait_screen({Screen.STORE})
        for index, (amount, price) in enumerate(STORE_OFFERS):
            x = .179 + index * .155
            region = (x - .07, .17, x + .07, .49)
            self.observe()
            label = joined([t for t in self._texts if region[0] < t.center[0] < region[2]
                            and region[1] < t.center[1] < region[3]])
            if not re.search(r"Astrite\s*[x×]?\s*" + str(amount), label, re.I):
                self.stop_with_evidence("Expected Astrite offer is not visible; no purchase attempted")
            if re.search(r"SOLD\s*OUT", label, re.I):
                continue
            balance = self.number((.795, .036, .843, .077))
            if balance < price:
                self.stop_with_evidence(f"Not enough Backstage Store currency: {balance}, requires {price}")
            self.click_relative(x, .3, after_sleep=.5)
            self.wait_screen({Screen.PURCHASE})
            if not self.text(r"Astrite\s*[x×]?\s*" + str(amount), (.2, .15, .8, .7)):
                self.stop_with_evidence("Purchase dialog does not match the expected Astrite offer")
            self.click_text(r"^Confirm$", (.5, .6, .85, .9))
            self.dismiss_receipt(Screen.STORE)
            self.observe()
            sold = self.text(r"SOLD\s*OUT", region)
            if sold is None:
                self.stop_with_evidence("Astrite purchase did not become SOLD OUT")
        self.close_page()

    def dismiss_receipt(self, expected):
        self.wait_screen({Screen.RECEIPT})
        self.click_relative(.5, .9, after_sleep=.5)
        self.wait_screen({expected})

    def claim_goals(self):
        observed = {}
        for tab, x in (("Story", .43), ("Adventure", .583), ("Cube", .736)):
            self.click_relative(x, .15, after_sleep=.4)
            self.scroll_relative(.9, .45, 15)
            self.sleep(.4)
            for _ in range(6):
                self.observe()
                claim = self.text(r"^Claim$", (.83, .2, .95, .72))
                if claim:
                    self.click_relative(*claim.center, after_sleep=.4)
                    self.dismiss_receipt(Screen.GOALS)
                    self.observe()
                row_names = [t for t in self._texts if .36 < t.center[0] < .64 and .2 < t.center[1] < .72
                             and (re.search(r"Complete.*Mode.*Stage|Win.*with", t.name, re.I))]
                for row in row_names:
                    row_text = joined([t for t in self._texts if .36 < t.center[0] < .82
                                       and row.y - .015 < t.center[1] < row.y + .10])
                    if tab == "Cube":
                        name = next((name for name in CUBES if name.lower() in row_text.lower()), None)
                        key = f"Cube {name}" if name else None
                    else:
                        stage = re.search(r"Stage\s*([1-6])", row_text, re.I)
                        key = f"{tab} {stage[1]}" if stage else None
                    if key:
                        # The first reward is Astrite; its white tick verifies
                        # the claim independently of the 1/1 objective counter.
                        complete = bool(re.search(r"1\s*/\s*1", row_text))
                        claimed = white_check(self.frame, (.681, row.center[1] + .018))
                        observed[key] = complete and claimed
                self.scroll_relative(.9, .45, -3)
                self.sleep(.4)
        required = {f"Story {n}" for n in range(1, 6)} | {f"Adventure {n}" for n in range(1, 7)} | {f"Cube {c}" for c in CUBES}
        missing = required - observed.keys()
        if missing:
            self.stop_with_evidence("Could not inspect all Astrite goals: " + ", ".join(sorted(missing)))
        self.observe()
        # Milestone clicks claim available rewards in bulk in the recording.
        for threshold, x in zip(MILESTONES, (.623, .818)):
            if white_check(self.frame, (x, .814)):
                continue
            badges = self.number((.416, .785, .479, .838))
            if badges < threshold:
                return {key for key in required if not observed[key]} | {f"{threshold} badges"}
            self.click_relative(x, .814, after_sleep=.5)
            self.dismiss_receipt(Screen.GOALS)
        return {key for key in required if not observed[key]}
