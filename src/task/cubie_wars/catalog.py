"""Reference definitions read from the user's English Collection screenshots."""
import json
import re
from functools import lru_cache
from pathlib import Path

from .model import CATEGORY_PRIORITY, ROLES, Item


# Core Item icons visually matched between the five guides and Collection.
# These are preferences within a category, not a mandatory completed build.
CORE_ITEMS = {
    'Rover': ('Blooming Jadehaven', 'Solsworn Ciphers', 'Everbright Polestar', 'The Last Dance'),
    'Aemeath': ('Everbright Polestar: Xtreme', 'Frostburn', 'Snowfluff Seal', '"Little Savior"'),
    'Hsin': ('Blooming Jadehaven: Xtreme', 'Cursed Violet Pendant', "Void's Keepsake", 'Cursed Edict Bell'),
    'Sigrika': ('Solsworn Ciphers: Xtreme', 'Iron Weight', 'Thunderflare Dominion', 'Blazing Justice'),
    'Lynae': ('The Last Dance: Xtreme', 'Lux & Umbra', 'Lucky Cloudstar', 'Golden Necklace'),
}


def normalize_name(name):
    # Exact identity modulo spacing/punctuation; never fuzzy-match an item.
    return re.sub(r'[^a-z0-9]', '', name.casefold())


def core_item(name, cube):
    return normalize_name(name) in {normalize_name(n) for n in CORE_ITEMS.get(cube, ())}


def sheet_footprint(name):
    row = name_index().get(normalize_name(name))
    if row and row['category'] == 'Sheet' and row.get('sheet_cells'):
        return tuple(tuple(cell) for cell in row['sheet_cells'])
    return None


@lru_cache(maxsize=1)
def definitions():
    records = json.loads(Path(__file__).with_name('items.json').read_text(encoding='utf-8'))['items']
    return {normalize_name(row['name']): row for row in records}


@lru_cache(maxsize=1)
def name_index():
    result = {}
    for row in definitions().values():
        for name in (row['name'], *row.get('ocr_name_aliases', ())):
            key = normalize_name(name)
            if key in result and result[key]['name'] != row['name']:
                raise ValueError('Ambiguous Collection item title: ' + name)
            result[key] = row
    return result


def reference_item(texts, parsed=None):
    """Recover only a uniquely named tooltip whose header agrees with the catalog.

    Runtime shop prices, coins, and placement are never inferred from Collection.
    A conflicting readable field rejects the reference instead of overriding it.
    """
    records = name_index()
    candidates = {}
    for title in texts:
        if not (.2 <= title.x < .98 and .075 <= title.y <= .3):
            continue
        line = [t for t in texts if title.x <= t.x <= title.x+.27
                and abs(t.center[1]-title.center[1]) < .018]
        for name in (title.name, ' '.join(t.name for t in sorted(line, key=lambda t: t.x))):
            key = normalize_name(name)
            if key in records:
                candidates[normalize_name(records[key]['name'])] = (records[key], title)
    # parse_item can join a wrapped title above the role pill.
    if parsed and normalize_name(parsed.name) in records:
        key = normalize_name(parsed.name)
        title = next((t for t in texts if .075 <= t.y <= .3
                      and normalize_name(t.name) in key and len(normalize_name(t.name)) >= 5), None)
        if title:
            candidates[normalize_name(records[key]['name'])] = (records[key], title)
    if len(candidates) > 1:
        # A full "Ever Bigger Namipon Bank" row includes the exact shorter
        # title "Namipon Bank" as one OCR fragment. Prefer the full row only
        # when all competing matches are contained on that same title line.
        full = max(candidates, key=len)
        full_title = candidates[full][1]
        if all(key in full and abs(title.center[1]-full_title.center[1]) < .018
               and abs(title.x-full_title.x) < .27
               for key, (_, title) in candidates.items()):
            candidates = {full: candidates[full]}
    if len(candidates) != 1:
        return None
    row, title = next(iter(candidates.values()))
    header = [t for t in texts if title.x-.04 <= t.x <= title.x+.27
              and title.y+.015 <= t.y <= title.y+.15]
    roles = {role for t in header for role in ROLES
             if re.fullmatch(r'(?:[^a-z]|[XIl|])*' + re.escape(role).replace(r'\ ', r'\s*'),
                             t.name.strip(), re.I)}
    categories = {kind for t in header for kind in CATEGORY_PRIORITY
                  if re.fullmatch(r'(?:[^a-z]|[XIl|])*' + kind, t.name.strip(), re.I)}
    if not roles and not categories and not (parsed and parsed.category):
        return None
    if roles and roles != {row['role']} or categories and categories != {row['category']}:
        return None
    if parsed and (parsed.role != row['role'] or parsed.category and parsed.category != row['category']):
        return None
    card = [t for t in texts if title.x-.04 <= t.x <= title.x+.27
            and title.y <= t.y <= title.y+.55]
    observed = {}
    for label, field in ((r'^\s*(?:[^a-z]|X)*DMG(?=\s|\d|$)', 'damage'),
                         (r'^\s*Attack\s*Interval(?=\s|\d|$)', 'attack_interval'),
                         (r'^\s*(?:[^a-z])*COST(?=\s|\d|$)', 'cost_weight')):
        stat = next((t for t in card if re.search(label, t.name, re.I)), None)
        if stat:
            label_match = re.search(label, stat.name, re.I)
            values = re.findall(r'\d+(?:\.\d+)?', stat.name[label_match.end():])
            values += [re.search(r'\d+(?:\.\d+)?', t.name).group()
                       for t in card if t.x > stat.x
                       and abs(t.center[1]-stat.center[1]) < .018
                       and re.fullmatch(r'\d+(?:\.\d+)?(?:s)?', t.name.strip(), re.I)]
            if len(values) > 1:
                return None
            if values:
                observed[field] = float(values[0])
                if row[field] is not None and observed[field] != row[field]:
                    return None
    if row['category'] == 'Weapon' and any(row[k] is None for k in ('cost_weight', 'damage', 'attack_interval')):
        return None
    # Matches the existing shop rule: only Weapons carry the COST stat;
    # Collection's absent nonweapon stat remains null in the source facts.
    cost = observed.get('cost_weight', row['cost_weight'])
    if cost is None and row['category'] in {'Accessory', 'Relic', 'Item'}:
        cost = parsed.cost if parsed and parsed.cost is not None else 0
    return Item(row['name'], row['role'], row['category'] == 'Sheet',
                int(cost) if cost is not None else None,
                observed.get('damage', row['damage'] or 0),
                observed.get('attack_interval', row['attack_interval'] or 1),
                row['description_visible'], row['category'])
