import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.task.CubieWarsTask import CubieWarsTask
from src.task.cubie_wars.catalog import CORE_ITEMS, core_item, definitions, normalize_name, reference_item, sheet_footprint
from src.task.cubie_wars.model import Item, Screen, Text, parse_item


FIXTURES = Path(__file__).parent/'images/cubie_wars'
SOURCE_OCR = json.loads((FIXTURES/'collection/actual_ocr.json').read_text())['records']
BY_SOURCE = {r['source_filename']: r for r in definitions().values()}


def card_header(case):
    # Translate actual Collection card OCR to the shop tooltip coordinate band.
    # Stat/description rows are deliberately missing, like a cropped live card.
    return [Text(t['name'], t['x']-.4, t['y']-.33, t['width'], t['height'])
            for t in case['raw_ocr'] if t['confidence'] >= .65 and .405 < t['y'] < .52]


@pytest.mark.parametrize('case', SOURCE_OCR, ids=lambda c: BY_SOURCE[c['source_filename']]['name'])
def test_actual_collection_title_and_role_recover_missing_metadata(case):
    expected = BY_SOURCE[case['source_filename']]
    item = reference_item(card_header(case))
    assert item is not None
    assert (item.name, item.role, item.category) == (
        expected['name'], expected['role'], expected['category'])
    if item.category == 'Weapon':
        assert (item.cost, item.damage, item.interval) == (
            expected['cost_weight'], expected['damage'], expected['attack_interval'])


def test_catalog_preserves_base_variants_clipped_descriptions_and_absent_stats():
    facts = list(definitions().values())
    assert Counter(r['category'] for r in facts) == {
        'Sheet': 12, 'Weapon': 35, 'Accessory': 53, 'Relic': 7, 'Item': 19}
    assert len(facts) == 126
    assert sum(r['description_may_be_clipped'] for r in facts) == 7
    assert all(r['cost_weight'] is None for r in facts if r['category'] != 'Weapon')
    assert definitions()['calloftheabyss']['cost_weight'] == 0
    for cube, names in CORE_ITEMS.items():
        assert all(normalize_name(name) in definitions() for name in names), cube
    assert core_item('Everbright Polestar', 'Rover')
    assert not core_item('Everbright Polestar: Xtreme', 'Rover')
    assert core_item('Everbright Polestar: Xtreme', 'Aemeath')
    assert not core_item('Everbright Polestar', 'Aemeath')


def test_every_provided_sheet_has_a_verified_footprint_and_other_items_do_not():
    for row in definitions().values():
        shape = sheet_footprint(row['name'])
        if row['category'] == 'Sheet':
            assert shape and len(shape) == len(set(shape))
            assert row['source_filename'] in row['sheet_shape_verification']
        else:
            assert shape is None
    assert len(sheet_footprint('HP Bread Sheet')) == 6
    assert len(sheet_footprint('Boom Boom Pow Sheet')) == 4
    assert len(sheet_footprint('Speed Sand Sheet')) == 2
    assert sheet_footprint('Unknown Sheet') is None


@pytest.mark.parametrize('name,cost,damage', [
    ('Thunderflare Dominion', 4, 159), ('Training Pistols', 2, 7),
    ('Solsworn Ciphers: Xtreme', 4, 240), ('Aleph-1 from Memories', 4, 1),
])
def test_catalog_keeps_visually_verified_numeric_rows(name, cost, damage):
    # Values read from the actual source pixels, not the low-confidence OCR.
    row = definitions()[normalize_name(name)]
    assert (row['cost_weight'], row['damage']) == (cost, damage)


def sword_header():
    return [Text('Training Sword', .3, .1), Text('Rapier', .3, .15),
            Text('Weapon', .44, .15)]


@pytest.mark.parametrize('field', ['role', 'category', 'cost', 'damage', 'interval'])
def test_readable_conflicting_tooltip_rejects_reference(field):
    texts = sword_header()
    if field == 'role':
        texts[1] = Text('Gold Hunter', .3, .15)
    elif field == 'category':
        texts[2] = Text('Accessory', .44, .15)
    else:
        label = {'cost': 'COST', 'damage': 'DMG', 'interval': 'Attack Interval'}[field]
        texts += [Text(label, .3, .25), Text('99', .5, .25)]
    assert reference_item(texts, parse_item(texts)) is None


@pytest.mark.parametrize('label', ['COST 99', 'COST99', 'DMG 99', 'XDMG99',
                                  'Attack Interval 99s', 'Attack Interval99s'])
def test_combined_label_and_numeric_box_cannot_override_live_conflict(label):
    texts = sword_header()+[Text(label, .3, .25)]
    assert reference_item(texts, parse_item(texts)) is None


def test_matching_combined_stat_boxes_keep_reference_usable():
    texts = sword_header()+[Text('DMG 6', .3, .23), Text('Attack Interval2s', .3, .27),
                            Text('COST3', .3, .31)]
    item = reference_item(texts, parse_item(texts))
    assert (item.damage, item.interval, item.cost) == (6, 2, 3)


def test_ambiguous_duplicate_stat_values_reject_reference():
    assert reference_item(sword_header()+[Text('COST 3', .3, .25),
                                         Text('4', .5, .25)]) is None


def test_reference_never_guesses_unknown_truncated_or_headerless_item():
    for name in ('Training Swor', 'Training Sword Plus', 'New Sword'):
        assert reference_item([Text(name, .3, .1), Text('Rapier', .3, .15)]) is None
    assert reference_item([Text('Training Sword', .3, .1)]) is None
    assert reference_item(sword_header()+[Text('Training Pistols', .65, .1),
                                         Text('Gold Hunter', .65, .15)]) is None


def task_with_store():
    task = CubieWarsTask(MagicMock(), MagicMock())
    task.config = dict(task.default_config)
    task.executor.method.width, task.executor.method.height = 1280, 720
    task.executor.frame = np.zeros((720, 1280, 3), np.uint8)
    task.move_relative = MagicMock()
    task.sleep = MagicMock()
    task.next_frame = MagicMock()
    task.require_shop = MagicMock()
    task.screenshot = MagicMock()
    return task


def test_shop_recovers_known_weapon_before_refresh_despite_missing_category_and_stats():
    task = task_with_store()
    texts = sword_header()[:2]
    task.ocr = MagicMock(return_value=[SimpleNamespace(
        name=t.name, x=t.x*1280, y=t.y*720, width=0, height=0) for t in texts])
    item = task.shop_item(1)
    assert (item.category, item.cost, item.damage, item.interval) == ('Weapon', 3, 6, 2)
    task.require_shop.assert_not_called()


def test_known_name_with_conflicting_role_stops_before_purchasing_or_refresh():
    task = task_with_store()
    texts = [Text('Training Sword', .3, .1), Text('Gold Hunter', .3, .15),
             Text('Weapon', .44, .15)]
    task.ocr = MagicMock(return_value=[SimpleNamespace(
        name=t.name, x=t.x*1280, y=t.y*720, width=0, height=0) for t in texts])
    task.click_relative = MagicMock()
    with pytest.raises(RuntimeError, match='tooltip is unreadable'):
        task.shop_item(0)
    task.click_relative.assert_not_called()


def test_core_weapon_is_preferred_within_category_before_refresh():
    task = task_with_store()
    task._cube, task._role = 'Aemeath', 'Rapier'
    task.config['Refreshes per round'] = 0
    task.observe = MagicMock(return_value=Screen.SHOP)
    task.synthesize = MagicMock()
    task.coins = MagicMock(side_effect=[10, 10, 6, 0])
    task.number = MagicMock(return_value=(0, 6))
    task.scan_recommendations = MagicMock(return_value=[False]*5)
    task.text = MagicMock(return_value=None)
    task.ocr = MagicMock(return_value=[SimpleNamespace(name='4')])
    offers = [Item('Training Sword', 'Rapier', False, 3, 999, 2, '', 'Weapon'),
              Item('Frostburn', 'Rapier', False, 3, 39, 2, '', 'Weapon')]
    task.shop_item = MagicMock(side_effect=lambda i: offers[i] if i < 2 else
                               Item('Other', 'Adventurer', False, 0, 0, 1, '', 'Accessory'))
    task.drag_to_book = MagicMock(return_value=True)
    task.click_relative = MagicMock()
    assert task.prepare_round()
    task.drag_to_book.assert_called_once()
    assert task.drag_to_book.call_args.args[0] == task.SHOP_SLOTS[1]
    task.click_relative.assert_not_called()
