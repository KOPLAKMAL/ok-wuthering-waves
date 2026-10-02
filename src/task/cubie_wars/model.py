"""Pure decisions shared by the live task and recording replay checks.

Only the English 16:9 interface has been observed. Unknown or incomplete
observations deliberately do not count as completion.
"""

import re
from dataclasses import dataclass
from enum import Enum


class Screen(Enum):
    UNKNOWN = "Unknown"
    HUB = "Cubie Wars menu"
    STAGES = "Stage selection"
    CUBE = "Cube selection"
    DETAILS = "Stage details"
    GUIDE = "Tutorial"
    SPOTLIGHT = "Tutorial highlight"
    SHOP = "Round store"
    MATCHING = "Matchmaking"
    COMBAT = "Combat"
    ROUND_RESULT = "Round result"
    STAGE_RESULT = "Stage result"
    EVENT = "Event choice"
    GOALS = "Adventure goals"
    STORE = "Backstage store"
    PURCHASE = "Purchase confirmation"
    RECEIPT = "Items obtained"
    SYNTHESIS = "Quick synthesis"


@dataclass(frozen=True)
class Text:
    name: str
    x: float
    y: float
    width: float = 0
    height: float = 0

    @property
    def center(self):
        return self.x + self.width / 2, self.y + self.height / 2


def joined(texts):
    return " ".join(t.name for t in sorted(texts, key=lambda t: (round(t.y / .015), t.x)))


def classify(texts):
    def has(pattern, region=(0, 0, 1, 1)):
        x, y, right, bottom = region
        return any(x <= t.center[0] <= right and y <= t.center[1] <= bottom
                   and re.search(pattern.replace(" ", r"\s*"), t.name, re.I) for t in texts)

    if has(r"Items Obtained", (.3, .1, .75, .4)):
        return Screen.RECEIPT
    if has(r"Astrite", (.2, .15, .8, .8)) and has(r"^Confirm$", (.2, .5, .85, .95)) and has(r"^Cancel$"):
        return Screen.PURCHASE
    if has(r"Turn to the last page|Items must be placed entirely|Items placed in the Storybook"):
        return Screen.GUIDE
    if spotlight_instruction(texts):
        return Screen.SPOTLIGHT
    if has(r"Adventure Goals", (0, 0, .4, .15)):
        return Screen.GOALS
    if has(r"Backstage Store", (0, 0, .5, .2)) and has(r"Inventory|SOLD OUT|Astrite", (0, .18, 1, .85)):
        return Screen.STORE
    if has(r"Click anywhere to continue", (.2, .7, .85, 1)) and has(
            r"Current Victories|Retries Available|Win\s*duels\s*to\s*earn\s*Trophies"):
        return Screen.ROUND_RESULT
    if has(r"Rounds Won|Remaining Retries", (.6, .25, 1, .6)) and has(r"^Back$|Next Stage|Try Again|Retry", (.5, .8, 1, 1)):
        return Screen.STAGE_RESULT
    if has(r"Please select an Event|Select an Event"):
        return Screen.EVENT
    if has(r"Items Available for Synthesis", (.45, .1, 1, .4)) or (
            has(r"^Synthesize$", (.11, .15, .98, .75))
            and has(r"Quick|Synthesis", (0, .08, .13, .2))):
        return Screen.SYNTHESIS
    if has(r"Trophies required to clear|Total Retries", (.25, .25, .8, .65)) and not has(r"Stage Objective"):
        return Screen.DETAILS
    if has(r"Cube Info|Default Items", (.65, .15, 1, .85)) and has(r"^G[o0C]$", (.65, .8, 1, 1)):
        return Screen.CUBE
    if has(r"Stage Objective", (.7, .2, 1, .65)) and has(r"Stage\s*[1-6]", (0, .12, .2, .9)):
        return Screen.STAGES
    if has(r"Drag the Item here to|View Synthesisinfo", (.6, .25, .98, .8)):
        return Screen.UNKNOWN
    if has(r"Matching", (.8, .8, 1, .95)) and has(r"Storage Box", (.35, .85, .7, 1)):
        return Screen.MATCHING
    if has(r"Storage Box", (.35, .85, .7, 1)) and has(r"Round\s*\d+.*Store", (.55, .09, .8, .2)):
        return Screen.SHOP
    if has(r"HP", (0, 0, .4, .1)) and has(r"HP", (.58, 0, .87, .1)) and has(r"Round\s*\d+", (.42, 0, .6, .1)):
        return Screen.COMBAT
    if has(r"Story Mode", (.2, .55, .5, .8)) and has(r"Adventure Mode", (.5, .55, .82, .8)):
        return Screen.HUB
    return Screen.UNKNOWN


def spotlight_instruction(texts):
    """Only tutorial instructions observed in the supplied recording."""
    prompts = (
        (r"Use\s*Coins\s*to\s*purchase\s*Items", (.937, .144)),
        (r"(?:set\s*amount\s*of\s*Coins\s*after\s*each\s*round|"
         r"unused\s*Coins\s*will\s*be\s*carried\s*over)", (.937, .144)),
        (r"Drag\s*Items\s*into\s*the\s*Sheet\s*to\s*purchase", (.636, .278)),
        (r"Drag\s*the\s*Items\s*you\s*want\s*into\s*the\s*Sheet", (.348, .37)),
        (r"Manage\s*your\s*set\s*and\s*click\s*the\s*bottom\s*right", (.895, .84)),
        (r"Use\s*the\s*Speed\s*Button\s*to\s*adjust\s*the\s*combat\s*s?peed", (.933, .177)),
    )
    text = joined(texts)
    return next(((pattern, anchor) for pattern, anchor in prompts
                 if re.search(pattern, text, re.I)), None)


STORY_COUNT = 5
ADVENTURE_COUNT = 6  # Stage 6 also grants 50 Astrite through the Challenge tab.
CUBES = ("Rover", "Aemeath", "Hsin", "Sigrika", "Lynae")
ROLES = ("Adventurer", "Rapier", "Traumatizer", "Heavy Hitter", "Gold Hunter")
ASTRITE_TOTAL = 1200
STORE_OFFERS = ((50, 200), (50, 200), (100, 500), (100, 500))
MILESTONES = (250, 750)
CATEGORY_PRIORITY = {'Weapon': 0, 'Sheet': 1, 'Accessory': 2, 'Relic': 3, 'Item': 4}


def next_stage(mode, checks):
    """checks must contain a visual observation for every stage in this mode."""
    count = STORY_COUNT if mode == "Story" else ADVENTURE_COUNT
    if set(checks) != set(range(1, count + 1)):
        raise ValueError("Incomplete stage list; cannot decide which stage remains")
    return next((stage for stage in range(1, count + 1) if not checks[stage]), None)


@dataclass(frozen=True)
class Item:
    name: str
    role: str
    sheet: bool
    cost: int | None
    damage: float
    interval: float
    description: str
    category: str = ''

    def purchase_rank(self, role, spare_capacity, free_cells, price):
        score = self.score(role, spare_capacity, free_cells, price)
        if self.category not in CATEGORY_PRIORITY or score <= 0:
            return None
        return -CATEGORY_PRIORITY[self.category], score

    def score(self, role, spare_capacity, free_cells, price):
        if price <= 0:
            return 0
        if self.sheet:
            return (18 if free_cells < 8 else 2) / price
        if self.cost is None or self.cost > spare_capacity:
            return 0
        synergy = 1.8 if self.role in (role, "Adventurer") else .55
        dps = self.damage / max(self.interval, .2)
        utility = 0
        for word, value in (("shield", 4), ("heal", 4), ("max hp", 3),
                            ("speed", 3), ("precision", 2), ("coin", 2)):
            if word in self.description.lower():
                utility += value
        return synergy * (dps + utility + (1 if self.cost == 0 else 0)) / price


def parse_item(texts):
    """Read tooltip stat values by row instead of joining interleaved columns."""
    role_text = next((t for t in texts if any(r.lower() in t.name.lower() for r in ROLES)), None)
    if role_text is None:
        return None
    role = next(r for r in ROLES if r.lower() in role_text.name.lower())
    above = [t for t in texts if role_text.y - .09 < t.y < role_text.y - .01
             and abs(t.x - role_text.x) < .06]
    name = joined(above).strip()
    if not name:
        return None
    card = [t for t in texts if role_text.x - .03 <= t.x <= role_text.x + .26
            and role_text.y - .09 <= t.y <= role_text.y + .5]
    text = joined(card)

    def stat(label, default):
        row = next((t for t in card if re.search(label, t.name, re.I)), None)
        if row is None:
            return default
        right = [t for t in card if t.x >= row.x and abs(t.center[1] - row.center[1]) < .018]
        values = re.findall(r"\d+(?:\.\d+)?", joined(right))
        return float(values[-1]) if values else default

    category_row = joined([t for t in card if abs(t.center[1]-role_text.center[1]) < .025])
    category = next((kind for kind in CATEGORY_PRIORITY
                     if re.search(kind+r'\b', category_row, re.I)), '')
    if not category and re.search(r'Skill\s*Chip', category_row, re.I):
        category = 'Item'
    if not category and re.search(r'[Iil1|][Il1|]?tem\b', category_row):
        category = 'Item'  # Actual OCR read the category icon + Item as Iltem.
    sheet = category == 'Sheet'
    cost = stat(r"\bCOST\b", None)
    # Skill chips and accessories have no COST row in the recorded tooltips.
    if cost is None and category in {'Accessory', 'Relic', 'Item'}:
        cost = 0
    return Item(name, role, sheet, int(cost) if cost is not None else None,
                stat(r"\bDMG\b", 0), stat(r"Attack Interval", 1), text, category)
