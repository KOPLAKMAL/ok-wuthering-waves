import json
import re
import time
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from src.task.CubieWarsTask import CubieWarsTask, ShopInterrupted
from src.task.cubie_wars.catalog import sheet_footprint
from src.task.cubie_wars.model import (
    ADVENTURE_COUNT, ASTRITE_TOTAL, CHAR_ROLES, Item, Screen, Text, classify,
    next_stage, parse_item, selected_build, stage_cube, spotlight_instruction,
)
from src.task.cubie_wars.vision import (
    capacity_tag, green_check, number_frame, placement_points, possible_recommendation,
    recipe_available, recommended_item, SheetPlacement,
    recommended_event,
    spotlight_target, stage_label_frame, valid_preview, white_check, yellow_button,
)


FIXTURES = Path(__file__).parent / 'images' / 'cubie_wars'
CASES = json.loads((FIXTURES / 'ocr.json').read_text(encoding='utf-8'))
LIVE_HOVER = json.loads((FIXTURES / 'live_hover_ocr.json').read_text(encoding='utf-8'))
LIVE_SYNTHESIS = json.loads((FIXTURES / 'live_synthesis_modal_ocr.json').read_text(encoding='utf-8'))
LIVE_PERSISTENT_ITEM = json.loads((FIXTURES / 'live_persistent_item_ocr.json').read_text(encoding='utf-8'))
LIVE_UNLOCK = json.loads((FIXTURES / 'live_new_warrior_ocr.json').read_text(encoding='utf-8'))
LIVE_RIGHT_SWORD = json.loads((FIXTURES / 'live_right_sword_ocr.json').read_text(encoding='utf-8'))
TUTORIAL_CASES = json.loads((FIXTURES / 'tutorial/ocr.json').read_text(encoding='utf-8'))
BUILD_CASES = json.loads((FIXTURES / 'builds/ocr.json').read_text(encoding='utf-8'))
RECOMMENDATION_CASES = json.loads((FIXTURES / 'recommendation_button_ocr.json').read_text())
STORAGE_GUIDE = json.loads((FIXTURES / 'storage_guide/ocr.json').read_text())
HELD_HP_SHEET = json.loads((FIXTURES / 'held_hp_bread_sheet_ocr.json').read_text(encoding='utf-8'))
HELD_HP_SHEET_OCT4 = json.loads((FIXTURES / 'held_hp_bread_sheet_oct4_ocr.json').read_text(encoding='utf-8'))


def build_texts(case):
    return [Text(**{k: v for k, v in t.items() if k != 'confidence'})
            for t in case['texts'] if t['confidence'] >= .65]


@pytest.mark.parametrize('case', BUILD_CASES[:5], ids=lambda c: c['name'])
def test_supplied_role_guides_read_selected_header_not_left_sidebar(case):
    texts = build_texts(case)
    assert classify(texts) == Screen.BUILD_GUIDE
    assert selected_build(texts) == case['name'].capitalize()


@pytest.mark.parametrize('missing', ['character', 'role', 'guide'])
def test_role_guide_needs_selected_header_and_matching_role(missing):
    texts = build_texts(BUILD_CASES[0])
    if missing == 'character':
        texts = [t for t in texts if t.center[0] < .8]
    elif missing == 'role':
        texts = [t for t in texts if not (.36 <= t.center[0] <= .55
                                         and .23 <= t.center[1] <= .33)]
        texts.append(Text('Gold Hunter', .4, .27))
    else:
        texts = [t for t in texts if not re.fullmatch(r'Role\s*Guide', t.name)]
    assert selected_build(texts) is None


@pytest.mark.parametrize('case', BUILD_CASES[:5], ids=lambda c: c['name'])
def test_resume_clicks_recommendation_and_returns_to_store(case):
    task = make_task()
    task._cube = None
    task._texts = [Text('Recommendation', .025, .79)]
    texts = build_texts(case)
    def guide_ready(expected):
        if expected == {Screen.BUILD_GUIDE}:
            task._texts = texts
    task.wait_screen = MagicMock(side_effect=guide_ready)
    task.click_relative = MagicMock()
    task.read_active_build()
    cube = case['name'].capitalize()
    assert task._cube == cube and task._role == CHAR_ROLES[cube]
    task.send_key.assert_not_called()
    assert [c.args for c in task.click_relative.call_args_list] == [
        (.033, .76), (.943, .06)]
    assert [c.args[0] for c in task.wait_screen.call_args_list] == [
        {Screen.BUILD_GUIDE}, {Screen.SHOP}]


def test_unreadable_resume_build_stops_before_any_purchase():
    task = make_task()
    task._cube = None
    task._texts = [Text('Recommendation', .025, .79)]
    task.wait_screen = MagicMock()
    task.click_relative = MagicMock()
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='active Cubie name and role'):
        task.read_active_build()
    assert task._cube is None
    task.click_relative.assert_called_once_with(.033, .76, after_sleep=.6)


def test_resume_reopens_manual_guide_via_recommendation_to_get_active_character():
    task = make_task()
    task._cube = None
    task._texts = build_texts(BUILD_CASES[0])  # Manually selected Aemeath.
    def ready(expected):
        task._texts = (build_texts(BUILD_CASES[1]) if expected == {Screen.BUILD_GUIDE}
                       else [Text('Recommendation', .025, .79)])
    task.wait_screen = MagicMock(side_effect=ready)
    task.click_relative = MagicMock()
    task.read_active_build(already_open=True)
    assert task._cube == 'Hsin' and task._role == 'Traumatizer'
    task.send_key.assert_not_called()
    assert [c.args[0] for c in task.wait_screen.call_args_list] == [
        {Screen.SHOP}, {Screen.BUILD_GUIDE}, {Screen.SHOP}]
    assert [c.args for c in task.click_relative.call_args_list] == [
        (.943, .06), (.033, .76), (.943, .06)]


@pytest.mark.parametrize('case', RECOMMENDATION_CASES, ids=lambda c: c['image'])
def test_focused_native_recommendation_caption_opens_guide_without_keyboard(case):
    task = make_task()
    task._cube = None
    task._texts = []  # Full-screen OCR missed the caption in these captures.
    task.executor.method.width, task.executor.method.height = 1920, 1080
    task.executor.frame = cv2.imread(str(FIXTURES / case['image']))
    task.ocr = MagicMock(return_value=[SimpleNamespace(**t) for t in case['texts']])
    def ready(expected):
        if expected == {Screen.BUILD_GUIDE}:
            task._texts = build_texts(BUILD_CASES[0])
    task.wait_screen = MagicMock(side_effect=ready)
    task.click_relative = MagicMock()
    task.read_active_build()
    task.ocr.assert_called_once_with(0, .71, .11, .86, threshold=.65, target_height=2160)
    task.send_key.assert_not_called()
    assert task._cube == 'Aemeath'
    assert [c.args for c in task.click_relative.call_args_list] == [
        (.033, .76), (.943, .06)]


def test_unreadable_recommendation_stops_before_clicking():
    task = make_task()
    task._cube = None
    task._texts = []
    task.ocr = MagicMock(return_value=[])
    task.screenshot = MagicMock()
    task.click_relative = MagicMock()
    with pytest.raises(RuntimeError, match='Recommendation is unreadable'):
        task.read_active_build()
    task.click_relative.assert_not_called()
    task.send_key.assert_not_called()


@pytest.mark.parametrize('case,count', [(BUILD_CASES[5], 6), (BUILD_CASES[6], 5)],
                         ids=['supplied_adventure', 'supplied_story'])
def test_supplied_stage_lists_with_production_ocr(case, count):
    task = make_task()
    task.executor.method.width, task.executor.method.height = 1280, 720
    task.executor.frame = cv2.imread(str(FIXTURES / 'builds' / (case['name']+'.jpg')))
    task.observe = MagicMock(return_value=Screen.STAGES)
    task.ocr = MagicMock(return_value=[SimpleNamespace(
        name=t['name'], x=t['x']*1280, y=t['y']*720,
        width=t['width']*1280, height=t['height']*720)
        for t in case['production_stage_list'] if t['confidence'] >= .65])
    checks, rows = task.stage_checks(count)
    assert set(rows) == set(range(1, count+1)) and all(checks.values())


def tutorial_case(name):
    return next(case for case in TUTORIAL_CASES if case['name'] == name)


@pytest.mark.parametrize('case', TUTORIAL_CASES, ids=lambda case: case['name'])
def test_supplied_story_1_2_3_tutorial_recognition(case):
    assert classify([Text(**t) for t in case['texts']]) == Screen[case['expected']]


@pytest.mark.parametrize('width', [1280, 1600, 1920])
@pytest.mark.parametrize('case', [c for c in TUTORIAL_CASES if c['expected'] == 'SPOTLIGHT'],
                         ids=lambda case: case['name'])
def test_supplied_highlight_clicks_verified_border_before_game_actions(case, width):
    task = make_task()
    image = cv2.imread(str(FIXTURES / 'tutorial' / (case['name']+'.jpg')))
    task.executor.frame = cv2.resize(image, (width, width*9//16))
    task._texts = [Text(**t) for t in case['texts']]
    task.click_relative = MagicMock()
    anchor = spotlight_instruction(task._texts)[1]
    assert spotlight_target(task.frame, anchor) == anchor
    task.handle_spotlight()
    task.click_relative.assert_called_once_with(*anchor, after_sleep=.7)


@pytest.mark.parametrize('name', ['story_2_03', 'story_2_07'])
def test_supplied_single_page_tutorial_confirms_without_pressing_d(name):
    task = make_task()
    task._texts = [Text(**t) for t in tutorial_case(name)['texts']]
    task.click_relative = MagicMock()
    task.handle_guide()
    confirm = next(t for t in task._texts if t.name == 'Confirm')
    task.click_relative.assert_called_once_with(*confirm.center, after_sleep=.6)


@pytest.mark.parametrize('name', ['story_1_13', 'story_1_14', 'story_1_16',
                                'story_2_00', 'story_2_01', 'story_2_02', 'story_2_06'])
def test_supplied_shop_tutorial_defers_resource_reads_and_shopping(name):
    task = make_task()
    task._texts = [Text(**t) for t in tutorial_case(name)['texts']]
    task.observe = MagicMock(side_effect=lambda: classify(task._texts))
    task.synthesize = MagicMock()
    task.coins = MagicMock()
    task.number = MagicMock()
    task.shop_item = MagicMock()
    assert task.prepare_round() is False
    task.synthesize.assert_not_called()
    task.coins.assert_not_called()
    task.number.assert_not_called()
    task.shop_item.assert_not_called()


@pytest.mark.parametrize('width', [1280, 1600, 1920])
def test_event_thumb_is_distinct_from_card_gold_decoration(width):
    image = cv2.imread(str(FIXTURES / 'tutorial/story_3_01.jpg'))
    image = cv2.resize(image, (width, width*9//16))
    assert [recommended_event(image, x) for x in (.22, .5, .78)] == [False, False, True]
    ordinary = cv2.imread(str(FIXTURES / 'tutorial/story_3_00.jpg'))
    ordinary = cv2.resize(ordinary, (width, width*9//16))
    assert not any(recommended_event(ordinary, x) for x in (.22, .5, .78))


def event_task(name):
    task = make_task()
    task._texts = [Text(**t) for t in tutorial_case(name)['texts']]
    task.executor.frame = cv2.imread(str(FIXTURES / 'tutorial' / (name+'.jpg')))
    task.click_relative = MagicMock()
    task.observe = MagicMock(return_value=Screen.EVENT)
    return task


def test_event_selects_thumb_before_survivability_heuristic_without_refresh():
    task = event_task('story_3_01')
    task.choose_event()
    confirm = next(t for t in task._texts if t.name == 'Confirm')
    assert [call.args for call in task.click_relative.call_args_list] == [(.78, .5), confirm.center]


def test_event_refreshes_until_thumb_appears_then_selects_it():
    task = event_task('story_3_00')
    def observe():
        task._texts = [Text(**t) for t in tutorial_case('story_3_01')['texts']]
        task.executor.frame = cv2.imread(str(FIXTURES / 'tutorial/story_3_01.jpg'))
        return Screen.EVENT
    task.observe.side_effect = observe
    task.choose_event()
    assert [call.args for call in task.click_relative.call_args_list[:2]] == [(.22, .765), (.78, .5)]


def test_event_without_thumbs_refreshes_each_card_once_then_confirms_fallback():
    task = event_task('story_3_00')
    task.choose_event()
    clicks = [call.args for call in task.click_relative.call_args_list]
    assert clicks[:3] == [(.22, .765), (.5, .765), (.78, .765)]
    assert len(clicks) == 5
    assert clicks[3][1] == .5
    assert clicks[4] == next(t.center for t in task._texts if t.name == 'Confirm')


def test_mandatory_single_event_card_does_not_reroll():
    task = event_task('story_2_04')
    task.choose_event()
    assert [call.args for call in task.click_relative.call_args_list] == [
        (.5, .5), next(t.center for t in task._texts if t.name == 'Confirm')]


def test_event_screen_change_after_refresh_stops_before_selecting_or_confirming():
    task = event_task('story_3_00')
    task.observe.return_value = Screen.SHOP
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='Event screen changed after refresh'):
        task.choose_event()
    task.click_relative.assert_called_once_with(.22, .765, after_sleep=.7)


def test_unreadable_event_cards_after_refresh_stop_before_more_input():
    task = event_task('story_3_00')
    def observe():
        task._texts = [t for t in task._texts if not (.4 < t.center[1] < .49)]
        return Screen.EVENT
    task.observe.side_effect = observe
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='Event cards were unreadable after refresh'):
        task.choose_event()
    task.click_relative.assert_called_once_with(.22, .765, after_sleep=.7)


def frame(name):
    return cv2.imread(str(FIXTURES / (name + '.jpg')))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['name'])
def test_recording_screen_recognition(case):
    assert classify([Text(**t) for t in case['texts']]) == Screen[case['expected']]


def test_live_new_warrior_popup_recognition_requires_header_and_close_prompt():
    texts = [Text(**t) for t in LIVE_UNLOCK]
    assert classify(texts) == Screen.UNLOCK
    assert classify([t for t in texts if 'New' not in t.name]) == Screen.UNKNOWN
    assert classify([t for t in texts if 'close' not in t.name]) == Screen.UNKNOWN


def final_synthesis_guide():
    # Navigation positions come from the recorded guide. Page text comes from
    # the live Quick Synthesis tutorial that was UNKNOWN before manual Confirm.
    controls = [Text(**t) for t in next(c for c in CASES if c['name'] == 'guide')['texts']
                if t['name'] in {'A', 'D', 'Confirm'}]
    return controls + [Text('Quick Synthesis', .07, .29),
                       Text('The Quick Synthesis list shows all Items available for synthesis,', .03, .37),
                       Text('saving you the hassle of dragging Items next to each other.', .03, .41)]


def test_final_synthesis_guide_is_recognized_without_earlier_page_phrases():
    assert classify(final_synthesis_guide()) == Screen.GUIDE
    assert classify([t for t in final_synthesis_guide() if t.name not in {'A', 'D'}]) == Screen.UNKNOWN


def test_final_guide_clicks_confirm_instead_of_forward():
    task = make_task()
    task._texts = final_synthesis_guide()
    task.click_relative = MagicMock()
    task.handle_guide()
    confirm = next(t for t in task._texts if t.name == 'Confirm')
    task.click_relative.assert_called_once_with(*confirm.center, after_sleep=.6)


def test_guide_stops_repeating_same_page_even_if_demo_numbers_change():
    task = make_task()
    task._texts = [t for t in final_synthesis_guide() if t.name != 'Confirm']
    task.click_relative = MagicMock()
    task.screenshot = MagicMock()
    for number in range(3):
        task._texts.append(Text(str(number), .7, .3))
        task.handle_guide()
    with pytest.raises(RuntimeError, match='page did not advance after three clicks'):
        task.handle_guide()
    assert task.click_relative.call_count == 3
    assert all(call.args == (.745, .806) for call in task.click_relative.call_args_list)


def test_guide_without_readable_navigation_stops_before_clicking():
    task = make_task()
    task._texts = [Text('Quick Synthesis', .07, .29)]
    task.click_relative = MagicMock()
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='tutorial navigation is unreadable'):
        task.handle_guide()
    task.click_relative.assert_not_called()


def test_wait_for_stage_list_dismisses_new_warrior_popup():
    task = make_task()
    task._deadline = time.monotonic() + 60
    task.observe = MagicMock(side_effect=[Screen.UNLOCK, Screen.UNLOCK, Screen.STAGES])
    task.click_relative = MagicMock()
    assert task.wait_screen({Screen.STAGES}) == Screen.STAGES
    assert task.click_relative.call_count == 2
    assert all(call.args == (.5, .9) for call in task.click_relative.call_args_list)


def test_new_warrior_popup_that_does_not_close_has_bounded_retries():
    task = make_task()
    task._deadline = time.monotonic() + 60
    task.observe = MagicMock(return_value=Screen.UNLOCK)
    task.click_relative = MagicMock()
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='popup did not close after three clicks'):
        task.wait_screen({Screen.STAGES})
    assert task.click_relative.call_count == 3


def test_stage_six_is_required_for_astrite():
    assert ADVENTURE_COUNT == 6
    assert ASTRITE_TOTAL == 200 + 300 + 200 + 200 + 300
    assert next_stage('Adventure', {n: n < 6 for n in range(1, 7)}) == 6
    with pytest.raises(ValueError):
        next_stage('Adventure', {n: True for n in range(1, 6)})


def test_recorded_stage_checks():
    texts = next(case['texts'] for case in CASES if case['name'] == 'stages')
    rows = [Text(**t) for t in texts if re.fullmatch(r'Stage\s*[1-6]', t['name']) and t['x'] < .18]
    assert len(rows) == 6
    assert all(green_check(frame('stages'), .149, t.center[1]) for t in rows)


def test_tooltip_stats_and_capacity_guard():
    texts = next(case['texts'] for case in CASES if case['name'] == 'shop_tooltip')
    item = parse_item([Text(**t) for t in texts])
    assert (item.name, item.role, item.cost, item.damage, item.interval) == ('Training Sword', 'Rapier', 3, 6, 2)
    assert item.category == 'Weapon'
    assert item.score('Rapier', 2, 5, 2) == 0
    assert item.score('Rapier', 3, 5, 2) > item.score('Gold Hunter', 3, 5, 2)


def test_native_right_tooltip_recovers_category_and_stat_columns():
    # Actual failing Story 2 capture: the old crop cuts off Weapon and all
    # right-aligned numbers. The wider crop also reads the icon as XDMG.
    partial = parse_item([Text(**t) for t in LIVE_RIGHT_SWORD['old']])
    assert partial.category == '' and partial.cost is None
    item = parse_item([Text(**t) for t in LIVE_RIGHT_SWORD['wide']])
    assert (item.name, item.category, item.cost, item.damage, item.interval) == (
        'Training Sword', 'Weapon', 3, 6, 2)
    assert item.purchase_rank('Rapier', 2, 5, 4) is None
    assert item.purchase_rank('Rapier', 3, 5, 4) is not None


def test_shop_reads_native_right_weapon_on_first_hover():
    task = make_task()
    task.executor.method.width, task.executor.method.height = 1920, 1080
    task.executor.frame = cv2.imread(str(FIXTURES / 'live_right_sword.png'))
    boxes = [SimpleNamespace(name=t['name'], x=t['x']*1920, y=t['y']*1080,
                             width=t['width']*1920, height=t['height']*1080)
             for t in LIVE_RIGHT_SWORD['wide']]
    task.ocr = MagicMock(return_value=boxes)
    task.require_shop = MagicMock()
    item = task.shop_item(2)
    assert (item.name, item.category, item.damage, item.interval, item.cost) == (
        'Training Sword', 'Weapon', 6, 2, 3)
    task.ocr.assert_called_once_with(.2, .075, .98, .7, threshold=.65)
    task.require_shop.assert_not_called()
    task.move_relative.assert_called_once_with(*task.SHOP_SLOTS[2])


def test_claimed_tick_is_distinct_from_an_available_astrite_icon():
    for point in ((.623, .814), (.818, .814), (.681, .265)):
        assert white_check(frame('goals_claimed'), point)
        assert not white_check(frame('goals_unclaimed'), point)


def test_free_cells_do_not_include_initial_sword():
    points = placement_points(frame('shop'))
    assert len(points) >= 3
    assert all(not (.27 < x < .31 and .35 < y < .58) for x, y in points)


def test_recorded_synthesis_controls_and_storage_tag():
    assert recipe_available(frame('synthesis_book'), .267)
    assert recipe_available(frame('synthesis_book'), .361)
    assert not recipe_available(frame('shop'), .267)
    assert yellow_button(frame('synthesis_book'), (.164, .49))
    assert capacity_tag(frame('storage'), (.535, .731))


def test_live_modal_synthesis_button_is_recognized_and_enabled():
    texts = [Text(**t) for t in LIVE_SYNTHESIS]
    assert classify(texts) == Screen.SYNTHESIS
    button = next(t for t in texts if t.name == 'Synthesize')
    assert yellow_button(cv2.imread(str(FIXTURES / 'live_synthesis_modal.png')), button.center)


@pytest.mark.parametrize('already_open', [False, True])
def test_synthesis_clicks_before_hidden_capacity_and_returns_to_shop(already_open):
    task = make_task()
    modal = cv2.imread(str(FIXTURES / 'live_synthesis_modal.png'))
    shop = frame('shop')
    sequence = ([Screen.SYNTHESIS] if already_open else [Screen.SHOP, Screen.SYNTHESIS]) + [
        Screen.SYNTHESIS, Screen.SHOP, Screen.SHOP]
    screens = iter(sequence)

    def observe():
        screen = next(screens)
        task.executor.frame = modal if screen == Screen.SYNTHESIS else shop
        task._texts = [Text(**t) for t in LIVE_SYNTHESIS] if screen == Screen.SYNTHESIS else []
        return screen

    task.observe = MagicMock(side_effect=observe)
    task.number = MagicMock(side_effect=AssertionError('Book capacity is hidden'))
    task.click_relative = MagicMock()
    task.info_incr = MagicMock()
    task.restore_storage = MagicMock(side_effect=lambda: pytest.fail('Storage read in modal')
                                    if task.executor.frame is modal else None)
    availability = ([True, False, False, False] if not already_open else []) + [False] * 4
    with patch('src.task.CubieWarsTask.recipe_available', side_effect=availability):
        task.synthesize()
    button = next(Text(**t) for t in LIVE_SYNTHESIS if t['name'] == 'Synthesize')
    clicks = [call.args for call in task.click_relative.call_args_list]
    assert clicks == ([] if already_open else [(.058, .267)]) + [button.center, (.5, .9)]
    task.number.assert_not_called()
    task.restore_storage.assert_called_once()
    task.info_incr.assert_called_once_with('Cubie Wars synthesis attempts')


def test_unavailable_modal_recipe_closes_without_synthesizing():
    task = make_task()
    modal = cv2.imread(str(FIXTURES / 'live_synthesis_modal.png'))
    disabled = [Text(**t) for t in LIVE_SYNTHESIS if t['name'] != 'Synthesize']
    screens = iter([Screen.SYNTHESIS, Screen.SYNTHESIS, Screen.SHOP])

    def observe():
        screen = next(screens)
        task._texts = disabled if screen == Screen.SYNTHESIS else []
        task.executor.frame = modal if screen == Screen.SYNTHESIS else frame('shop')
        return screen

    task.observe = MagicMock(side_effect=observe)
    task.number = MagicMock()
    task.click_relative = MagicMock()
    task.restore_storage = MagicMock()
    task.info_incr = MagicMock()
    task.synthesize()
    task.click_relative.assert_called_once_with(.5, .9, after_sleep=.4)
    task.number.assert_not_called()
    task.restore_storage.assert_not_called()
    task.info_incr.assert_not_called()


def test_inline_synthesis_returns_to_book_before_storage_check():
    task = make_task()
    screens = iter([Screen.SYNTHESIS, Screen.SYNTHESIS, Screen.SHOP, Screen.SHOP])
    button = Text('Synthesize', .127, .475, .071, .033)

    def observe():
        screen = next(screens)
        task._texts = [button] if screen == Screen.SYNTHESIS else []
        task.executor.frame = frame('synthesis_book') if screen == Screen.SYNTHESIS else frame('shop')
        return screen

    task.observe = MagicMock(side_effect=observe)
    task.number = MagicMock()
    task.click_relative = MagicMock()
    task.restore_storage = MagicMock()
    task.info_incr = MagicMock()
    with patch('src.task.CubieWarsTask.recipe_available', return_value=False):
        task.synthesize()
    assert [call.args for call in task.click_relative.call_args_list] == [button.center, (.55, .78)]
    task.number.assert_not_called()
    task.restore_storage.assert_called_once()


@pytest.mark.parametrize('screen', [Screen.GUIDE, Screen.SPOTLIGHT])
def test_tutorial_after_synthesis_defers_storage_and_resource_reads(screen):
    task = make_task()
    task.observe = MagicMock(return_value=screen)
    task.number = MagicMock()
    with pytest.raises(ShopInterrupted):
        task.leave_synthesis()
    task.number.assert_not_called()


def test_real_storage_guide_transition_defers_synthesis_until_tutorial_settles():
    transition = [Text(**t) for t in STORAGE_GUIDE['transition']['texts']]
    settled = [Text(**t) for t in STORAGE_GUIDE['settled']['texts']]
    assert classify(transition) == Screen.UNKNOWN
    assert classify(settled) == Screen.GUIDE
    task = make_task()
    captures = iter([transition, transition, settled])
    def observe():
        task._texts = next(captures)
        return classify(task._texts)
    task.observe = MagicMock(side_effect=observe)
    task.click_relative = MagicMock()
    task.number = MagicMock()
    with pytest.raises(ShopInterrupted):
        task.synthesize()
    assert task.observe.call_count == 3
    task.click_relative.assert_not_called()
    task.number.assert_not_called()


def test_unknown_synthesis_screen_retries_but_stops_without_clicking():
    task = make_task()
    task.observe = MagicMock(return_value=Screen.UNKNOWN)
    task.click_relative = MagicMock()
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='changed before synthesis'):
        task.synthesize()
    assert task.observe.call_count == 8
    task.click_relative.assert_not_called()


def test_tutorial_transition_after_opening_recipe_defers_synthesize_click():
    task = make_task()
    task.observe = MagicMock(side_effect=[Screen.SHOP, Screen.UNKNOWN, Screen.GUIDE])
    task.executor.frame = frame('synthesis_book')
    task.click_relative = MagicMock()
    task.number = MagicMock()
    with patch('src.task.CubieWarsTask.recipe_available', return_value=True):
        with pytest.raises(ShopInterrupted):
            task.synthesize()
    task.click_relative.assert_called_once_with(.058, .267, after_sleep=.35)
    task.number.assert_not_called()


def test_shop_transition_to_storage_guide_defers_actions():
    task = make_task()
    task.observe = MagicMock(side_effect=[Screen.UNKNOWN, Screen.GUIDE])
    task.click_relative = MagicMock()
    with pytest.raises(ShopInterrupted):
        task.require_shop()
    task.click_relative.assert_not_called()


def test_upgrade_interrupted_by_tutorial_restores_storage_after_rejoining_shop():
    task = make_task()
    task.executor.frame = cv2.imread(str(FIXTURES / 'live_synthesis_modal.png'))
    task._texts = [Text(**t) for t in LIVE_SYNTHESIS]
    task.observe = MagicMock(side_effect=[Screen.SYNTHESIS, Screen.GUIDE])
    task.click_relative = MagicMock()
    task.restore_storage = MagicMock()
    with pytest.raises(ShopInterrupted):
        task.synthesize()
    assert task._storage_pending
    task.restore_storage.assert_not_called()
    task.observe = MagicMock(return_value=Screen.SHOP)
    task.executor.frame = frame('shop')
    with patch('src.task.CubieWarsTask.recipe_available', return_value=False):
        task.synthesize()
    task.restore_storage.assert_called_once()
    assert not task._storage_pending
    assert task.click_relative.call_count == 1  # Never repeat the upgrade.


def test_storage_restoration_waits_for_tutorial_before_reading_demo_items():
    task = make_task()
    task.observe = MagicMock(side_effect=[Screen.UNKNOWN, Screen.GUIDE])
    task.ocr = MagicMock()
    task.number = MagicMock()
    with pytest.raises(ShopInterrupted):
        task.restore_storage()
    task.ocr.assert_not_called()
    task.number.assert_not_called()


def test_unclosable_synthesis_panel_stops_without_reading_resources():
    task = make_task()
    task.observe = MagicMock(return_value=Screen.SYNTHESIS)
    task._texts = [Text(**t) for t in LIVE_SYNTHESIS if 'close' not in t['name']]
    task.number = MagicMock()
    task.click_relative = MagicMock()
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='close instruction'):
        task.leave_synthesis()
    task.number.assert_not_called()
    task.click_relative.assert_not_called()


def test_drop_requires_green_preview_and_rejects_collision():
    before = frame('shop')
    assert valid_preview(before, frame('valid_ghost'))
    assert not valid_preview(before, frame('invalid_ghost'))
    assert not valid_preview(before, frame('invalid_ghost_sword'))
    assert not valid_preview(before, before)
    crosses_book_border = frame('valid_ghost')
    crosses_book_border[635:690, 500:545] = (70, 60, 220)
    assert not valid_preview(before, crosses_book_border)


def make_task():
    task = CubieWarsTask(MagicMock(), MagicMock())
    # Existing shop/action fixtures start with a verified Rover build.
    # Resume identity tests clear it to exercise Recommendation recovery.
    task._cube = 'Rover'
    task.config = dict(task.default_config)
    task.executor.method.width = 1280
    task.executor.method.height = 720
    task.move_relative = MagicMock()
    task.sleep = MagicMock()
    task.next_frame = MagicMock()
    task.mouse_down = MagicMock()
    task.mouse_up = MagicMock()
    task.send_key = MagicMock()
    task.rotate_held_item = MagicMock()
    # Placement tests below start after a verified pickup; test pickup itself
    # separately with failed presses, stale captures, and actual OCR fixtures.
    def picked_up(source):
        task.mouse_down(round(source[0] * task.width), round(source[1] * task.height))
        return True
    task.pick_up = MagicMock(side_effect=picked_up)
    task.drag_active = MagicMock(return_value=True)
    return task


@pytest.mark.parametrize('mode,cubes', [
    ('Story', ['Rover', 'Aemeath', 'Hsin', 'Sigrika', 'Lynae']),
    ('Adventure', ['Rover', 'Sigrika', 'Hsin', 'Lynae', 'Aemeath', 'Lynae']),
])
def test_player_character_mapping_for_every_stage(mode, cubes):
    assert [stage_cube(mode, stage) for stage in range(1, len(cubes)+1)] == cubes


@pytest.mark.parametrize('mode,stage', [('Story', 0), ('Story', 6),
                                      ('Adventure', 7), ('Other', 1),
                                      ('Story', True), ('Story', None)])
def test_invalid_stage_cannot_choose_a_character(mode, stage):
    with pytest.raises(ValueError):
        stage_cube(mode, stage)


@pytest.mark.parametrize('role', list(CHAR_ROLES.values()))
def test_rover_accepts_all_weapon_roles_and_specialists_reject_other_weapons(role):
    sword = Item('Weapon', role, False, 3, 6, 2, '', 'Weapon')
    assert sword.score('Adventurer', 3, 4, 2) == pytest.approx(2.7)
    for active in list(CHAR_ROLES.values())[1:]:
        assert (sword.purchase_rank(active, 3, 4, 2) is not None) == (
            role in {active, 'Adventurer'})
    assert sword.purchase_rank('Adventurer', 2, 4, 2) is None


@pytest.mark.parametrize('stage', range(1, 7))
def test_adventure_selects_stage_character_in_original_cube_order(stage):
    task = make_task()
    cube = stage_cube('Adventure', stage)
    task.observe = MagicMock(side_effect=[Screen.CUBE, Screen.STAGE_RESULT])
    task._texts = [Text('Rover', .75, .12), Text('Go', .8, .9)]
    task.wait_screen = MagicMock(side_effect=lambda _: setattr(task, '_texts', [
        Text(cube, .75, .12), Text('Go', .8, .9), Text('Back', .7, .9)]))
    task.click_relative = MagicMock()
    task.click_text = MagicMock()
    task.play_stage('Adventure', stage)
    assert task._cube == cube and task._role == CHAR_ROLES[cube]
    task.click_relative.assert_called_once_with(
        task.CUBE_POSITIONS[('Rover', 'Aemeath', 'Hsin', 'Sigrika', 'Lynae').index(cube)],
        .914, after_sleep=.6)


def test_story_character_mismatch_stops_before_entering_stage():
    task = make_task()
    task.observe = MagicMock(return_value=Screen.CUBE)
    task._texts = [Text('Rover', .75, .12), Text('Go', .8, .9)]
    task.click_text = MagicMock()
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='selected Cubie: Aemeath'):
        task.play_stage('Story', 2)
    task.click_text.assert_not_called()


def test_complete_mode_passes_verified_stage_number_to_character_selection():
    task = make_task()
    pending = {n: n != 2 for n in range(1, 7)}
    done = {n: True for n in range(1, 7)}
    rows = {n: Text(f'Stage {n}', .1, .2+n*.1) for n in range(1, 7)}
    task.stage_checks = MagicMock(side_effect=[(pending, rows), (done, rows), (done, rows)])
    task.wait_screen = MagicMock()
    task.click_text = MagicMock()
    task.click_relative = MagicMock()
    task.play_stage = MagicMock()
    task.close_page = MagicMock()
    task.complete_mode('Adventure')
    task.play_stage.assert_called_once_with('Adventure', 2)


@pytest.mark.parametrize('case', json.loads((FIXTURES / 'stage_labels_ocr.json').read_text()),
                         ids=lambda case: case['name'])
def test_selected_stage_label_uses_focused_ocr_and_preserves_all_checks(case):
    task = make_task()
    task.executor.method.width = 1920 if case['count'] == 5 else 1280
    task.executor.method.height = 1080 if case['count'] == 5 else 720
    task.executor.frame = frame('live_story_stages' if case['count'] == 5 else 'stages')
    task.observe = MagicMock(return_value=Screen.STAGES)
    # Full-screen OCR omitted selected Stage 5. Use actual focused OCR results.
    task._texts = [Text('Stage 1', .1, .3)]
    task.ocr = MagicMock(return_value=[SimpleNamespace(
        name=t['name'], x=t['x']*task.width, y=t['y']*task.height,
        width=t['width']*task.width, height=t['height']*task.height)
        for t in case['texts']])
    checks, rows = task.stage_checks(case['count'])
    assert set(rows) == set(range(1, case['count'] + 1))
    assert all(checks.values())
    for row in rows.values():
        for offset in (-2, 0, 2):
            assert green_check(task.frame, .149, row.center[1] + offset / task.height)
    without_tick = task.frame.copy()
    selected_y = rows[case['count']].center[1]
    x, y = round(.149 * task.width), round(selected_y * task.height)
    without_tick[y-25:y+25, x-25:x+25] = (95, 60, 80)
    assert not green_check(without_tick, .149, selected_y)
    assert task.ocr.call_args.kwargs['frame_processor'] is stage_label_frame
    assert task.ocr.call_args.kwargs['target_height'] == 2160
    processed = stage_label_frame(task.frame)
    assert processed.shape == task.frame.shape
    assert (processed[:, :, 0] == processed[:, :, 2]).all()


def test_missing_stage_still_stops_instead_of_assuming_completion():
    task = make_task()
    task.observe = MagicMock(return_value=Screen.STAGES)
    task.ocr = MagicMock(return_value=[])
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='every Cubie Wars stage'):
        task.stage_checks(5)


def test_failed_drag_returns_to_source_rotates_with_right_click_and_releases():
    task = make_task()
    task.executor.frame = frame('shop')
    task.screenshot = MagicMock()
    with patch('src.task.CubieWarsTask.placement_points', return_value=[(.3, .3)]), \
            patch('src.task.CubieWarsTask.valid_preview', return_value=False):
        assert not task.drag_to_book((.636, .278), frame('shop'))
    task.mouse_down.assert_called_once_with(814, 200)
    assert task.rotate_held_item.call_count == 4
    task.send_key.assert_not_called()
    task.move_relative.assert_called_with(.636, .278)
    task.mouse_up.assert_called_once()
    assert task._placement_reason == 'unknown'


@pytest.mark.parametrize('case', json.loads((FIXTURES / 'pickup_ocr.json').read_text()),
                         ids=lambda case: case['name'])
def test_held_item_marker_from_actual_native_and_recording_ocr(case):
    task = make_task()
    del task.drag_active
    suffix = '.png' if case['name'].startswith('live_') else '.jpg'
    task.executor.frame = cv2.imread(str(FIXTURES / (case['name'] + suffix)))

    def replay_ocr(*args, **kwargs):
        assert args == (.05, .1, .97, .96)
        assert kwargs['frame'] is task.frame
        assert kwargs['target_height'] == 1080
        return [SimpleNamespace(name=t['name']) for t in case['texts']
                if t['confidence'] >= kwargs['threshold'] and kwargs['match'].fullmatch(t['name'])]

    task.ocr = MagicMock(side_effect=replay_ocr)
    assert task.drag_active() is case['held']


def test_pickup_retries_missed_press_then_keeps_mouse_down_on_two_held_frames():
    task = make_task()
    del task.pick_up
    task.require_shop = MagicMock()
    task.drag_active.side_effect = [False] * 4 + [False, True, True]
    source = task.SHOP_SLOTS[3]
    assert task.pick_up(source)
    assert task.mouse_down.call_count == 2
    task.mouse_up.assert_called_once()
    assert task.next_frame.call_count == 7
    moves = [c.args for c in task.move_relative.call_args_list]
    assert moves[0] == source
    assert moves[1:3] == [(source[0] + dx / 1920, source[1]) for dx in (8, 16)]
    assert moves[8] == (.5, .78)
    assert moves[9:12] == [source, (.55, .78), source]
    assert moves[-1] == (.5, .78)
    task.require_shop.assert_called_once()
    task.send_key.assert_not_called()


def test_real_sheet_rotate_merged_with_sold_is_still_a_held_item():
    task = make_task()
    del task.drag_active
    task.executor.frame = cv2.imread(str(FIXTURES / 'held_hp_bread_sheet.png'))
    def replay(*args, **kwargs):
        return [SimpleNamespace(name=t['name']) for t in HELD_HP_SHEET['runtime_focused']
                if t['confidence'] >= kwargs['threshold'] and kwargs['match'].fullmatch(t['name'])]
    task.ocr = MagicMock(side_effect=replay)
    assert any(t['name'] == 'Rotate Sold' for t in HELD_HP_SHEET['runtime_focused'])
    assert task.drag_active()


def test_real_1440p_mouse_icon_joined_to_rotate_is_still_held():
    task = make_task()
    del task.drag_active
    task.executor.method.width, task.executor.method.height = 2560, 1440
    task.executor.frame = cv2.imread(str(FIXTURES / 'held_hp_bread_sheet_oct4.png'))
    task.ocr = MagicMock(side_effect=lambda *args, **kwargs: [SimpleNamespace(name=t['name'])
        for t in HELD_HP_SHEET_OCT4['runtime_focused']
        if t['confidence'] >= kwargs['threshold'] and kwargs['match'].fullmatch(t['name'])])
    assert any(t['name'] == '1Rotate' for t in HELD_HP_SHEET_OCT4['runtime_focused'])
    assert task.drag_active()


@pytest.mark.parametrize('name', ['1Rotate', 'DRotate', 'D Rotate', 'IRotate', 'Rotate Sold'])
def test_observed_mouse_glyph_prefixes_and_sold_do_not_signal_lost_drag(name):
    task = make_task()
    del task.drag_active
    task.ocr = MagicMock(side_effect=lambda *args, **kwargs:
                         [SimpleNamespace(name=name)] if kwargs['match'].fullmatch(name) else [])
    assert task.drag_active()


@pytest.mark.parametrize('text', ['Sold', 'Rotate Items to change their orientation',
                                 'Adjust the Sheet and rotate Items'])
def test_static_instruction_text_cannot_confirm_held_sheet(text):
    task = make_task()
    del task.drag_active
    task.ocr = MagicMock(side_effect=lambda *args, **kwargs:
                         [SimpleNamespace(name=text)] if kwargs['match'].fullmatch(text) else [])
    assert not task.drag_active()


def test_rotation_presses_and_releases_right_without_releasing_left():
    task = make_task()
    del task.rotate_held_item
    task.rotate_held_item()
    task.mouse_down.assert_called_once_with(key='right')
    task.mouse_up.assert_called_once_with(key='right')
    task.send_key.assert_not_called()


def test_interrupted_rotation_still_releases_only_right_button():
    task = make_task()
    del task.rotate_held_item
    task.sleep.side_effect = RuntimeError('Stopped')
    with pytest.raises(RuntimeError, match='Stopped'):
        task.rotate_held_item()
    task.mouse_up.assert_called_once_with(key='right')


def test_sheet_drag_uses_whole_footprint_plan_not_a_single_occupied_cell():
    task = make_task()
    before = cv2.imread(str(FIXTURES / 'sheet_geometry/board.png'))
    task.executor.frame = before
    task.click_relative = MagicMock()
    shape = sheet_footprint('HP Bread Sheet')
    with patch('src.task.CubieWarsTask.valid_sheet_preview', return_value=True), \
            patch('src.task.CubieWarsTask.placement_points') as old_points:
        assert task.drag_to_book(task.SHOP_SLOTS[2], before, True, shape)
    old_points.assert_not_called()
    task.move_relative.assert_called_once_with(414/1920, 609/1080)
    task.send_key.assert_not_called()
    task.mouse_up.assert_called_once()
    assert task._placement_reason == 'placed'


def test_sheet_plan_with_no_whole_fit_does_not_pick_up_or_claim_a_placement():
    task = make_task()
    before = cv2.imread(str(FIXTURES / 'sheet_geometry/board.png'))
    oversized = tuple((col, 0) for col in range(9))
    assert not task.drag_to_book(task.SHOP_SLOTS[2], before, True, oversized)
    assert task._placement_reason == 'no_space'
    task.pick_up.assert_not_called()
    task.move_relative.assert_not_called()


def test_rotated_sheet_plan_rotates_before_trying_its_center():
    task = make_task()
    before = cv2.imread(str(FIXTURES / 'sheet_geometry/board.png'))
    task.executor.frame = before
    plan = SimpleNamespace(rotation=1, point=(.3, .4))
    with patch('src.task.CubieWarsTask.sheet_placements', return_value=[plan]), \
            patch('src.task.CubieWarsTask.valid_sheet_preview', return_value=True):
        assert task.drag_to_book(task.SHOP_SLOTS[2], before, True, sheet_footprint('HP Bread Sheet'))
    task.rotate_held_item.assert_called_once_with()
    task.send_key.assert_not_called()
    task.move_relative.assert_called_once_with(*plan.point)
    task.mouse_up.assert_called_once()


def test_geometric_sheet_fit_with_failed_preview_is_not_reported_as_no_space():
    task = make_task()
    before = cv2.imread(str(FIXTURES / 'sheet_geometry/board.png'))
    task.executor.frame = frame('invalid_ghost')
    task.screenshot = MagicMock()
    plan = SimpleNamespace(rotation=0, point=(.3, .4))
    with patch('src.task.CubieWarsTask.sheet_placements', return_value=[plan]), \
            patch('src.task.CubieWarsTask.preview_counts', return_value=(0, 1000)), \
            patch('src.task.CubieWarsTask.valid_sheet_preview', return_value=False):
        assert not task.drag_to_book(task.SHOP_SLOTS[2], before, True, sheet_footprint('HP Bread Sheet'))
    assert task._placement_reason == 'unknown'
    task.send_key.assert_not_called()  # No more planned orientations.
    task.mouse_up.assert_called_once()
    task.move_relative.assert_called_with(*task.SHOP_SLOTS[2])


def thin_sheet_frames():
    directory = FIXTURES / 'thin_preview'
    return (cv2.imread(str(directory/'positive_before_native.png')),
            cv2.imread(str(directory/'positive_held_native.png')))


def thin_sheet_plan():
    return SheetPlacement(0, (6, 0), ((6, 0), (7, 0), (6, 1), (7, 1)),
                          (924/1920, 252/1080), 2)


def test_actual_thin_sheet_edges_release_after_first_stable_nudged_preview():
    task = make_task()
    before, held = thin_sheet_frames()
    task.executor.frame = before
    captures = iter([before]*3+[held]*2)
    task.next_frame.side_effect = lambda: setattr(task.executor, 'frame', next(captures))
    plan = thin_sheet_plan()
    with patch('src.task.CubieWarsTask.sheet_placements', return_value=[plan]):
        assert task.drag_to_book(task.SHOP_SLOTS[1], before, True, sheet_footprint('Empty Sheet'))
    assert [c.args for c in task.move_relative.call_args_list] == [
        plan.point, (948/1920, 268/1080)]
    task.mouse_up.assert_called_once()
    task.send_key.assert_not_called()
    assert task.next_frame.call_count == 5
    assert task._placement_reason == 'placed'


def test_one_thin_sheet_preview_then_disappearance_never_drops():
    task = make_task()
    before, held = thin_sheet_frames()
    task.executor.frame = before
    captures = iter([before]*3+[held]+[before]*5)
    task.next_frame.side_effect = lambda: setattr(task.executor, 'frame', next(captures))
    task.screenshot = MagicMock()
    with patch('src.task.CubieWarsTask.sheet_placements', return_value=[thin_sheet_plan()]):
        assert not task.drag_to_book(task.SHOP_SLOTS[1], before, True, sheet_footprint('Empty Sheet'))
    task.move_relative.assert_called_with(*task.SHOP_SLOTS[1])
    task.mouse_up.assert_called_once()
    assert task._placement_reason == 'unknown'


def test_thin_sheet_evidence_cannot_drop_an_item_when_hold_is_lost():
    task = make_task()
    before, held = thin_sheet_frames()
    task.executor.frame = held
    task.drag_active.return_value = False
    task.screenshot = MagicMock()
    with patch('src.task.CubieWarsTask.sheet_placements', return_value=[thin_sheet_plan()]), \
            patch('src.task.CubieWarsTask.valid_sheet_preview') as preview:
        assert not task.drag_to_book(task.SHOP_SLOTS[1], before, True, sheet_footprint('Empty Sheet'))
    preview.assert_not_called()
    task.mouse_up.assert_called_once()
    task.move_relative.assert_called_with(*task.SHOP_SLOTS[1])
    assert task._placement_reason == 'lost_drag'


def test_three_missed_pickups_do_not_search_or_report_a_purchase():
    task = make_task()
    del task.pick_up
    task.require_shop = MagicMock()
    task.drag_active.return_value = False
    task.screenshot = MagicMock()
    with patch('src.task.CubieWarsTask.placement_points', return_value=[(.3, .3)]), \
            patch('src.task.CubieWarsTask.valid_preview') as preview:
        assert not task.drag_to_book(task.SHOP_SLOTS[3], frame('shop'))
    assert task._placement_reason == 'not_picked_up'
    assert task.mouse_down.call_count == task.mouse_up.call_count == 3
    assert task.next_frame.call_count == 12
    preview.assert_not_called()
    task.send_key.assert_not_called()
    task.screenshot.assert_called_once_with('cubie-wars-pickup-failed')
    assert task.require_shop.call_count == 3


def test_interrupted_pickup_always_returns_to_source_and_releases():
    task = make_task()
    del task.pick_up
    task.next_frame.side_effect = RuntimeError('Stopped')
    with pytest.raises(RuntimeError, match='Stopped'):
        task.pick_up(task.SHOP_SLOTS[3])
    task.mouse_up.assert_called_once()
    task.move_relative.assert_called_with(*task.SHOP_SLOTS[3])


def test_green_hover_card_cannot_confirm_placement_after_drag_is_lost():
    task = make_task()
    before = cv2.imread(str(FIXTURES / 'live_recommended_middle.png'))
    missed = cv2.imread(str(FIXTURES / 'live_pickup_missed.png'))
    # Reproduce the old false positive from the actual failure capture.
    assert valid_preview(before, missed)
    task.executor.frame = missed
    task.drag_active.return_value = False
    task.screenshot = MagicMock()
    with patch('src.task.CubieWarsTask.placement_points', return_value=[(.3, .3)]):
        assert not task.drag_to_book(task.SHOP_SLOTS[3], before)
    assert task._placement_reason == 'lost_drag'
    task.move_relative.assert_called_with(*task.SHOP_SLOTS[3])
    task.mouse_up.assert_called_once()
    task.send_key.assert_not_called()
    assert task.drag_active.call_count == 3


def test_stop_during_drag_still_releases_mouse():
    task = make_task()
    task.next_frame.side_effect = RuntimeError('Stopped')
    with patch('src.task.CubieWarsTask.placement_points', return_value=[(.3, .3)]):
        with pytest.raises(RuntimeError, match='Stopped'):
            task.drag_to_book((.636, .278), frame('shop'))
    task.mouse_up.assert_called_once()


@pytest.mark.parametrize('width', [1280, 1920, 2560])
def test_native_green_outline_and_tan_free_cell(width):
    before = cv2.imread(str(FIXTURES / 'live_recommended_middle.png'))
    held = cv2.imread(str(FIXTURES / 'live_green_crystal.png'))
    size = (width, round(width * 9 / 16))
    before, held = (cv2.resize(image, size) for image in (before, held))
    assert valid_preview(before, held)
    # Tan sheets also provide usable empty space; an occupied card doesn't.
    assert (771 / 1920, 507 / 1080) in placement_points(before)
    assert (771 / 1920, 609 / 1080) not in placement_points(before)


def occluded_crystal_frames():
    # Board-only captures saved by the 06:07 live run, without a user ID.
    images = []
    for name in ('before', 'held'):
        tile = cv2.imread(str(FIXTURES / f'live_occluded_crystal_{name}.png'))
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        image[97:821, 115:1114] = tile
        images.append(image)
    return images


def test_actual_centered_crystal_covers_the_green_preview():
    before, held = occluded_crystal_frames()
    assert not valid_preview(before, held)
    # The earlier manual capture exposes the outline beside the held icon.
    assert valid_preview(before, cv2.imread(str(FIXTURES / 'live_green_crystal.png')))


def test_drag_nudges_hidden_preview_then_releases_without_rotating():
    task = make_task()
    before, covered = occluded_crystal_frames()
    visible = cv2.imread(str(FIXTURES / 'live_green_crystal.png'))
    task.executor.frame = before
    captures = iter([covered] * 3 + [visible] * 2)
    task.next_frame.side_effect = lambda: setattr(task.executor, 'frame', next(captures))
    target = (567 / 1920, 303 / 1080)
    with patch('src.task.CubieWarsTask.placement_points', return_value=[target]):
        assert task.drag_to_book(task.SHOP_SLOTS[3], before)
    assert [call.args for call in task.move_relative.call_args_list] == [
        target, (target[0] + 24 / 1920, target[1] + 16 / 1080)]
    task.send_key.assert_not_called()
    task.mouse_up.assert_called_once()


def test_hidden_preview_tries_both_sides_before_rotating_without_blind_drop():
    task = make_task()
    before, covered = occluded_crystal_frames()
    task.executor.frame = covered
    task.screenshot = MagicMock()
    target = (567 / 1920, 303 / 1080)
    with patch('src.task.CubieWarsTask.placement_points', return_value=[target]):
        assert not task.drag_to_book(task.SHOP_SLOTS[3], before)
    attempts = [target, (target[0] + 24 / 1920, target[1] + 16 / 1080),
                (target[0] - 24 / 1920, target[1] - 16 / 1080)]
    assert [call.args for call in task.move_relative.call_args_list] == attempts * 4 + [task.SHOP_SLOTS[3]]
    task.mouse_up.assert_called_once()
    assert task._placement_reason == 'unknown'


def test_drag_releases_at_first_stable_green_without_returning_to_shop():
    task = make_task()
    before = cv2.imread(str(FIXTURES / 'live_recommended_middle.png'))
    held = cv2.imread(str(FIXTURES / 'live_green_crystal.png'))
    task.executor.frame = before
    captures = iter((before, held, held))  # One stale frame after movement.
    task.next_frame.side_effect = lambda: setattr(task.executor, 'frame', next(captures))
    target = (567 / 1920, 303 / 1080)
    with patch('src.task.CubieWarsTask.placement_points', return_value=[target]):
        assert task.drag_to_book(task.SHOP_SLOTS[3], before)
    task.move_relative.assert_called_once_with(*target)
    task.send_key.assert_not_called()
    task.mouse_up.assert_called_once()
    assert task._placement_reason == 'placed'


def test_partial_green_with_red_collision_returns_item_and_reports_no_space():
    task = make_task()
    before = frame('shop')
    held = frame('valid_ghost')
    # The rest of a large item can extend beyond the sheet into Storage.
    held[635:690, 500:545] = (70, 60, 220)
    task.executor.frame = held
    task.screenshot = MagicMock()
    with patch('src.task.CubieWarsTask.placement_points', return_value=[(.3, .3)]):
        assert not task.drag_to_book(task.SHOP_SLOTS[0], before)
    task.move_relative.assert_called_with(*task.SHOP_SLOTS[0])
    task.mouse_up.assert_called_once()
    assert task._placement_reason == 'no_space'
    assert task.move_relative.call_count == 5  # Four red positions, then cancel; no nudges.


def test_one_green_frame_does_not_drop_after_preview_disappears():
    task = make_task()
    before = cv2.imread(str(FIXTURES / 'live_recommended_middle.png'))
    held = cv2.imread(str(FIXTURES / 'live_green_crystal.png'))
    task.executor.frame = before
    captures = iter([held] + [before] * 35)
    task.next_frame.side_effect = lambda: setattr(task.executor, 'frame', next(captures))
    task.screenshot = MagicMock()
    with patch('src.task.CubieWarsTask.placement_points', return_value=[(.3, .3)]):
        assert not task.drag_to_book(task.SHOP_SLOTS[3], before)
    task.move_relative.assert_called_with(*task.SHOP_SLOTS[3])
    task.mouse_up.assert_called_once()
    assert task._placement_reason == 'unknown'


def test_cancellation_move_failure_still_releases_mouse():
    task = make_task()
    task.next_frame.side_effect = RuntimeError('Stopped')
    task.move_relative.side_effect = [None, RuntimeError('Lost focus')]
    with patch('src.task.CubieWarsTask.placement_points', return_value=[(.3, .3)]):
        with pytest.raises(RuntimeError, match='Lost focus'):
            task.drag_to_book(task.SHOP_SLOTS[0], frame('shop'))
    task.mouse_up.assert_called_once()


def test_inspection_does_not_send_game_input():
    task = make_task()
    task.observe = MagicMock(return_value=Screen.HUB)
    task.screenshot = MagicMock()
    task.log_info = MagicMock()
    task.run()
    task.mouse_down.assert_not_called()
    task.send_key.assert_not_called()
    task.screenshot.assert_called_once_with('cubie-wars-inspection')


def test_windows_run_without_admin_stops_before_sending_input():
    task = make_task()
    task.config['Mode'] = 'Astrite run'
    task.observe = MagicMock(return_value=Screen.HUB)
    task.is_browser = MagicMock(return_value=False)
    task.screenshot = MagicMock()
    task.click_relative = MagicMock()
    with patch('src.task.CubieWarsTask.is_admin', return_value=False), \
            patch('src.task.CubieWarsTask.WWOneTimeTask.run') as prepare_input:
        with pytest.raises(RuntimeError, match='Administrator'):
            task.run()
    prepare_input.assert_not_called()
    task.click_relative.assert_not_called()
    task.mouse_down.assert_not_called()
    task.send_key.assert_not_called()


@pytest.mark.parametrize('screen', [Screen.GUIDE, Screen.SPOTLIGHT])
def test_delayed_tutorial_prevents_shop_actions(screen):
    task = make_task()
    task.observe = MagicMock(return_value=screen)
    task.synthesize = MagicMock()
    task.coins = MagicMock()
    assert task.prepare_round() is False
    task.synthesize.assert_not_called()
    task.coins.assert_not_called()
    task.mouse_down.assert_not_called()


def test_resource_ocr_retries_an_initial_animation_frame():
    task = make_task()
    task.ocr = MagicMock(side_effect=[[], [SimpleNamespace(name='6')]])
    task.observe = MagicMock(return_value=Screen.SHOP)
    assert task.coins() == 6
    assert task.ocr.call_count == 2


@pytest.mark.parametrize('screen', [Screen.GUIDE, Screen.SPOTLIGHT])
def test_resource_ocr_defers_to_a_new_tutorial(screen):
    task = make_task()
    task.ocr = MagicMock(return_value=[])
    task.observe = MagicMock(return_value=screen)
    with pytest.raises(ShopInterrupted):
        task.coins()
    assert task.ocr.call_count == 1


def test_unreadable_resource_still_stops_after_bounded_retries():
    task = make_task()
    task.ocr = MagicMock(return_value=[])
    task.observe = MagicMock(return_value=Screen.SHOP)
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='resource value is unreadable'):
        task.coins()
    assert task.ocr.call_count == 4


@pytest.mark.parametrize('screen', [Screen.GUIDE, Screen.SYNTHESIS, Screen.UNLOCK, Screen.STAGES])
def test_resume_story_rejoins_stage_verification_and_rewards(screen):
    task = make_task()
    task.config['Mode'] = 'Resume Story stage'
    task.observe = MagicMock(return_value=screen)
    task.is_browser = MagicMock(return_value=False)
    task.play_stage = MagicMock()
    task.wait_screen = MagicMock()
    task.close_page = MagicMock()
    task.complete_mode = MagicMock()
    task.claim_rewards = MagicMock()
    with patch('src.task.CubieWarsTask.is_admin', return_value=True), \
            patch('src.task.CubieWarsTask.WWOneTimeTask.run'):
        task.run()
    if screen in {Screen.UNLOCK, Screen.STAGES}:
        task.play_stage.assert_not_called()
    else:
        task.play_stage.assert_called_once_with('Story')
    task.wait_screen.assert_called_once_with({Screen.STAGES})
    task.close_page.assert_called_once()
    assert [call.args for call in task.complete_mode.call_args_list] == [('Story',), ('Adventure',)]
    task.claim_rewards.assert_called_once()


def test_stage_handles_open_synthesis_before_preparing_shop():
    task = make_task()
    screens = iter([Screen.SYNTHESIS, Screen.SHOP, Screen.SHOP, Screen.STAGE_RESULT])

    def observe():
        screen = next(screens)
        task._texts = [Text('Round 1 - Store', .6, .1)]
        return screen

    task.observe = MagicMock(side_effect=observe)
    actions = MagicMock()
    task.synthesize = actions.synthesize
    task.prepare_round = actions.prepare_round
    task.prepare_round.return_value = True
    task.start_round = actions.start_round
    task.click_text = MagicMock()
    task.play_stage('Story')
    assert [call[0] for call in actions.mock_calls] == ['synthesize', 'prepare_round', 'start_round']


@pytest.mark.parametrize('name,anchor', [
    ('spotlight_coins', (.937, .144)),
    ('spotlight_round_coins', (.937, .144)),
    ('spotlight_item', (.636, .278)),
    ('spotlight_sheet', (.348, .37)),
    ('spotlight_start', (.895, .84)),
    ('spotlight_speed', (.933, .177)),
])
def test_recorded_highlight_requires_border_and_clicks_the_control(name, anchor):
    task = make_task()
    task.executor.frame = frame(name)
    task._texts = [Text(**t) for t in next(c['texts'] for c in CASES if c['name'] == name)]
    task.click_relative = MagicMock()
    assert spotlight_instruction(task._texts)[1] == anchor
    assert spotlight_target(task.frame, anchor) == anchor
    task.handle_spotlight()
    task.click_relative.assert_called_once_with(*anchor, after_sleep=.7)
    # Ordinary shop gold and sword decorations cannot substitute for a border.
    assert spotlight_target(frame('shop'), anchor) is None


def test_highlight_missing_border_stops_before_input():
    task = make_task()
    task.executor.frame = frame('shop')
    task._texts = [Text('Use Coins to purchase Items', .7, .2)]
    task.click_relative = MagicMock()
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='yellow border'):
        task.handle_spotlight()
    task.click_relative.assert_not_called()


def test_highlight_that_does_not_advance_has_a_click_limit():
    task = make_task()
    task.executor.frame = frame('spotlight_coins')
    task._texts = [Text('Use Coins to purchase Items', .7, .2)]
    task.click_relative = MagicMock()
    task.screenshot = MagicMock()
    for _ in range(3):
        task.handle_spotlight()
    with pytest.raises(RuntimeError, match='three highlighted clicks'):
        task.handle_spotlight()
    assert task.click_relative.call_count == 3


def test_start_highlight_arriving_after_preparation_returns_to_tutorial():
    task = make_task()
    task._texts = [Text('Round 1 - Store', .6, .1)]
    task.observe = MagicMock(side_effect=[Screen.SHOP, Screen.SPOTLIGHT,
                                         Screen.SPOTLIGHT, Screen.STAGE_RESULT])
    task.prepare_round = MagicMock(return_value=True)
    task.handle_spotlight = MagicMock()
    task.click_text = MagicMock()
    task.start_round = MagicMock()
    task.play_stage('Story')
    task.handle_spotlight.assert_called_once()
    # The tutorial handler owns Start while the overlay is present.
    task.start_round.assert_not_called()


def test_resource_fallback_uses_recorded_full_screen_numbers():
    task = make_task()
    task._texts = [Text(**t) for t in next(c['texts'] for c in CASES if c['name'] == 'shop')]
    task.ocr = MagicMock(return_value=[])
    task.observe = MagicMock(return_value=Screen.SHOP)
    assert task.coins() == 6
    assert task.number((.139, .103, .178, .139), fraction=True) == (3, 6)


@pytest.mark.parametrize('screen', [Screen.GUIDE, Screen.SPOTLIGHT])
def test_tutorial_precedes_readable_full_screen_number_fallback(screen):
    task = make_task()
    task._texts = [Text('6', .94, .13, .01, .02)]
    task.ocr = MagicMock(return_value=[])
    task.observe = MagicMock(return_value=screen)
    with pytest.raises(ShopInterrupted):
        task.coins()


@pytest.mark.parametrize('texts', [
    [Text('6', .5, .5)],  # A number elsewhere in the screen is not a resource.
    [Text('6', .94, .13), Text('9', .95, .14)],  # Ambiguous detections.
    [Text('Round 6', .94, .13)],  # Numeric substring in a label.
])
def test_resource_fallback_rejects_unrelated_or_ambiguous_numbers(texts):
    task = make_task()
    task._texts = texts
    task.ocr = MagicMock(return_value=[])
    task.observe = MagicMock(return_value=Screen.SHOP)
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='resource value is unreadable'):
        task.coins()
    assert task.ocr.call_count == 4


@pytest.mark.parametrize('width', [1280, 1920, 2560])
@pytest.mark.parametrize('name,expected', [
    ('recommended_shop', [False, False, True, True, False]),
    ('recommended_shop_2', [False, True, True, True, False]),
    ('live_shop', [False, False, False, False, False]),
])
def test_recorded_recommendation_thumbs_and_unmarked_slots(width, name, expected):
    image = cv2.resize(frame(name), (width, width*9//16))
    points = [(x, .392 if index < 3 else .64)
              for index, (x, _) in enumerate(CubieWarsTask.SHOP_SLOTS)]
    assert [recommended_item(image, point) for point in points] == expected


@pytest.mark.parametrize('width', [1280, 1920, 2560])
@pytest.mark.parametrize('name', ['live_recommended_shop', 'live_recommended_shop_settled'])
def test_native_smaller_thumbs_are_not_skipped_during_or_after_refresh_animation(width, name):
    image = cv2.imread(str(FIXTURES / (name + '.png')))
    image = cv2.resize(image, (width, width*9//16))
    points = [(x, .392 if index < 3 else .64)
              for index, (x, _) in enumerate(CubieWarsTask.SHOP_SLOTS)]
    # Gold price-badge edges in slots 1 and 2 are not recommendation hands.
    assert [recommended_item(image, point) for point in points] == [False, False, True, False, True]


def test_start_uses_focused_label_when_full_screen_ocr_reads_stari():
    task = make_task()
    task.executor.frame = cv2.imread(str(FIXTURES / 'live_recommended_shop.png'))
    task._texts = [Text('Round 1 - Store', .57, .14), Text('Storage Box', .45, .92),
                   Text('Stari', .87, .89)]
    task.ocr = MagicMock(return_value=[SimpleNamespace(name='Start')])
    task.click_relative = MagicMock()
    task.wait_screen = MagicMock()
    task.start_round()
    assert task.ocr.call_args.kwargs['frame_processor'] is number_frame
    task.click_relative.assert_called_once_with(.895, .85, after_sleep=.6)
    task.wait_screen.assert_called_once_with({Screen.MATCHING, Screen.COMBAT, Screen.SPOTLIGHT, Screen.GUIDE})


@pytest.mark.parametrize('screen', [Screen.MATCHING, Screen.SPOTLIGHT, Screen.UNKNOWN])
def test_start_rejects_other_screens_even_with_a_start_label(screen):
    task = make_task()
    task.ocr = MagicMock(return_value=[SimpleNamespace(name='Start')])
    task.click_relative = MagicMock()
    task.screenshot = MagicMock()
    with patch('src.task.CubieWarsTask.classify', return_value=screen):
        with pytest.raises(RuntimeError, match='before clicking Start'):
            task.start_round()
    task.click_relative.assert_not_called()


def test_start_does_not_guess_if_focused_label_is_unreadable():
    task = make_task()
    task._texts = [Text('Round 1 - Store', .57, .14), Text('Storage Box', .45, .92)]
    task.ocr = MagicMock(return_value=[])
    task.click_relative = MagicMock()
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='Start label'):
        task.start_round()
    task.click_relative.assert_not_called()


@pytest.mark.parametrize('missing', ['price', 'tooltip'])
def test_unreadable_recommended_offer_stops_before_spending_on_refresh(missing):
    task = make_task()
    task.executor.frame = cv2.imread(str(FIXTURES / 'live_recommended_shop.png'))
    task.observe = MagicMock(return_value=Screen.SHOP)
    task.synthesize = MagicMock()
    task.coins = MagicMock(return_value=1)
    task.number = MagicMock(return_value=(3, 6))
    task.ocr = MagicMock(side_effect=lambda *args, **kwargs:
                         [] if missing == 'price' or args == (.2, .075, .98, .7)
                         else [SimpleNamespace(name='1')])
    task.click_relative = MagicMock()
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match=f'{missing} is unreadable'):
        task.prepare_round()
    task.click_relative.assert_not_called()


def test_native_recommendation_is_attempted_with_last_coin_before_refresh():
    task = make_task()
    task.executor.method.width, task.executor.method.height = 1920, 1080
    task.executor.frame = cv2.imread(str(FIXTURES / 'live_recommended_shop.png'))
    task.observe = MagicMock(return_value=Screen.SHOP)
    task.synthesize = MagicMock()
    task.coins = MagicMock(side_effect=[1, 1, 0, 0, 0])
    task.number = MagicMock(side_effect=lambda region, fraction=False: (3, 6) if fraction else 2)
    case = next(c for c in json.loads((FIXTURES / 'item_categories_ocr.json').read_text())
                if c['category'] == 'Relic')
    tooltip = [SimpleNamespace(name=t['name'], x=t['x']*1920, y=t['y']*1080,
                               width=t['width']*1920, height=t['height']*1080)
               for t in case['texts']]
    task.ocr = MagicMock(side_effect=lambda *args, **kwargs:
                         tooltip if args == (.2, .075, .98, .7) else [SimpleNamespace(name='1')])
    task.drag_to_book = MagicMock(return_value=True)
    task.click_relative = MagicMock()
    assert task.prepare_round() is True
    # Uses real native thumb detection and a recorded tooltip. Both marked
    # offers are considered; the first affordable one is purchased, not rerolled.
    assert task.drag_to_book.call_count == 1
    assert task.drag_to_book.call_args.args[0] == task.SHOP_SLOTS[2]
    task.click_relative.assert_not_called()


def test_tooltip_can_appear_after_first_hover_frame():
    task = make_task()
    task.observe = MagicMock(return_value=Screen.SHOP)
    case = next(c for c in json.loads((FIXTURES / 'item_categories_ocr.json').read_text())
                if c['category'] == 'Relic')
    boxes = [SimpleNamespace(name=t['name'], x=t['x']*task.width, y=t['y']*task.height,
                             width=t['width']*task.width, height=t['height']*task.height)
             for t in case['texts']]
    task.ocr = MagicMock(side_effect=[[], boxes])
    assert task.shop_item(1).category == 'Relic'
    assert task.ocr.call_count == 2
    task.move_relative.assert_called_once_with(*task.SHOP_SLOTS[1])


def test_live_middle_thumb_is_detected_even_without_item_tooltip():
    image = cv2.imread(str(FIXTURES / 'live_recommended_middle.png'))
    assert [recommended_item(image, (x, .392 if index < 3 else .64))
            for index, (x, _) in enumerate(CubieWarsTask.SHOP_SLOTS)] == [False, True, False, False, False]


@pytest.mark.parametrize('source', ['texts', 'tooltip_texts'])
def test_live_crystal_category_below_affinity_is_accessory_not_weapon(source):
    item = parse_item([Text(**t) for t in LIVE_HOVER[source]])
    assert item.name == '"Random"Crystal'
    assert item.role == 'Adventurer'
    assert item.category == 'Accessory' and item.cost == 0
    assert item.purchase_rank('Adventurer', 3, 3, 1) is not None


def test_live_hover_remains_a_tooltip_in_the_store_when_round_label_is_hidden():
    texts = [Text(**t) for t in LIVE_HOVER['texts']]
    assert not any(re.search(r'Round\s*\d+.*Store', t.name, re.I) for t in texts)
    assert classify(texts) == Screen.ITEM_TOOLTIP
    # The card alone does not establish a Store screen elsewhere.
    assert classify([Text(**t) for t in LIVE_HOVER['tooltip_texts']]) == Screen.UNKNOWN


def test_live_crystal_targeted_ocr_is_accepted_on_first_hover_read():
    task = make_task()
    task.executor.method.width, task.executor.method.height = 1920, 1080
    task.ocr = MagicMock(return_value=[SimpleNamespace(
        name=t['name'], x=t['x']*1920, y=t['y']*1080,
        width=t['width']*1920, height=t['height']*1080)
        for t in LIVE_HOVER['tooltip_texts']])
    task.require_shop = MagicMock()
    assert task.shop_item(1).category == 'Accessory'
    task.ocr.assert_called_once()
    task.require_shop.assert_not_called()


def test_live_recommended_crystal_reaches_purchase_before_refresh():
    task = make_task()
    task.executor.method.width, task.executor.method.height = 1920, 1080
    task.config['Refreshes per round'] = 0
    clear = cv2.imread(str(FIXTURES / 'live_recommended_middle.png'))
    hover = cv2.imread(str(FIXTURES / 'live_hover_crystal.png'))
    task.executor.frame = clear
    task.synthesize = MagicMock()
    task.coins = MagicMock(side_effect=[5, 5, 4, 4])
    task.number = MagicMock(return_value=(3, 6))

    def move(x, y):
        task.executor.frame = hover if (x, y) == task.SHOP_SLOTS[1] else clear

    def observe():
        task._texts = [Text(**t) for t in LIVE_HOVER['texts']] if task.frame is hover else [
            Text('Stage Details', .03, .04), Text('Round 1 - Store', .6, .1),
            Text('Storage Box', .44, .9), Text('3/6', .14, .1)]
        return classify(task._texts)

    boxes = [SimpleNamespace(name=t['name'], x=t['x']*1920, y=t['y']*1080,
                             width=t['width']*1920, height=t['height']*1080)
             for t in LIVE_HOVER['tooltip_texts']]
    task.move_relative.side_effect = move
    task.observe = MagicMock(side_effect=observe)
    task.ocr = MagicMock(side_effect=lambda *args, **kwargs:
                         boxes if args == (.2, .075, .98, .7) else [SimpleNamespace(name='1')])
    task.drag_to_book = MagicMock(return_value=True)
    task.click_relative = MagicMock()
    assert task.prepare_round() is True
    task.drag_to_book.assert_called_once()
    assert task.drag_to_book.call_args.args[0] == task.SHOP_SLOTS[1]
    task.click_relative.assert_not_called()


@pytest.mark.parametrize('persistent', [False, True])
def test_active_tooltip_is_cleared_before_round_preparation_or_start(persistent):
    task = make_task()
    screens = iter([Screen.ITEM_TOOLTIP, Screen.SHOP, Screen.SHOP, Screen.STAGE_RESULT])

    def observe():
        screen = next(screens)
        labels = LIVE_PERSISTENT_ITEM if persistent else LIVE_HOVER['texts']
        task._texts = [Text(**t) for t in labels] if screen == Screen.ITEM_TOOLTIP else [
            Text('Round 1 - Store', .6, .1)]
        return screen

    task.observe = MagicMock(side_effect=observe)
    task.prepare_round = MagicMock(return_value=True)
    task.start_round = MagicMock()
    task.click_text = MagicMock()
    task.click_relative = MagicMock()
    task.play_stage('Story')
    task.move_relative.assert_called_once_with(.55, .78)
    task.prepare_round.assert_called_once()
    task.start_round.assert_called_once()
    if persistent:
        task.click_relative.assert_called_once_with(.5, .78, after_sleep=.35)
    else:
        task.click_relative.assert_not_called()


@pytest.mark.parametrize('following', [Screen.SHOP, Screen.ITEM_TOOLTIP, Screen.SPOTLIGHT])
def test_persistent_item_card_must_close_to_shop_before_retry(following):
    task = make_task()
    task._texts = [Text(**t) for t in LIVE_PERSISTENT_ITEM]
    assert classify(task._texts) == Screen.ITEM_TOOLTIP
    task.executor.frame = cv2.imread(str(FIXTURES / 'live_persistent_item.png'))
    task.observe = MagicMock(side_effect=[Screen.ITEM_TOOLTIP, following])
    task.click_relative = MagicMock()
    task.screenshot = MagicMock()
    if following == Screen.SHOP:
        task.require_shop()
    elif following == Screen.SPOTLIGHT:
        with pytest.raises(ShopInterrupted):
            task.require_shop()
    else:
        with pytest.raises(RuntimeError, match='Store changed'):
            task.require_shop()
    task.click_relative.assert_called_once_with(.5, .78, after_sleep=.35)
    assert task.observe.call_count == 2
    task.mouse_down.assert_not_called()


def test_pickup_does_not_retry_while_card_stays_open():
    task = make_task()
    del task.pick_up
    task.drag_active.return_value = False
    task._texts = [Text(**t) for t in LIVE_PERSISTENT_ITEM]
    task.observe = MagicMock(return_value=Screen.ITEM_TOOLTIP)
    task.click_relative = MagicMock()
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='Store changed'):
        task.pick_up(task.SHOP_SLOTS[4])
    task.mouse_down.assert_called_once()
    task.mouse_up.assert_called_once()
    task.click_relative.assert_called_once_with(.5, .78, after_sleep=.35)


@pytest.mark.parametrize('allow', [True, False])
def test_tooltip_is_allowed_only_while_reading_an_offer(allow):
    task = make_task()
    task.observe = MagicMock(return_value=Screen.ITEM_TOOLTIP)
    task.screenshot = MagicMock()
    if allow:
        task.require_shop(allow_tooltip=True)
    else:
        with pytest.raises(RuntimeError, match='Store changed'):
            task.require_shop()


def test_descriptive_weapon_mention_below_affinity_is_not_a_category():
    texts = [Text('Crystal', .43, .10), Text('Adventurer', .45, .16),
             Text('Used to synthesize Rare and Epic Weapons.', .43, .20)]
    item = parse_item(texts)
    assert item.category == '' and item.cost is None


def test_tutorial_during_hover_interrupts_before_purchase():
    task = make_task()
    task.observe = MagicMock(return_value=Screen.SPOTLIGHT)
    task.ocr = MagicMock(return_value=[])
    with pytest.raises(ShopInterrupted):
        task.shop_item(1)
    task.mouse_down.assert_not_called()


def test_shop_waits_for_recommendations_after_animation_before_refresh():
    task = make_task()
    empty = frame('live_shop')
    marked = cv2.imread(str(FIXTURES / 'live_recommended_shop.png'))
    sequence = iter([empty, empty, marked])

    def observe():
        task.executor.frame = next(sequence)
        return Screen.SHOP

    task.observe = MagicMock(side_effect=observe)
    task.screenshot = MagicMock()
    assert task.scan_recommendations() == [False, False, True, False, True]
    assert task.observe.call_count == 3
    assert [call.args for call in task.sleep.call_args_list] == [(.6,), (.6,)]
    diagnostic = task.screenshot.call_args.kwargs['frame']
    assert diagnostic.shape == (669, 787, 3)


def test_missed_visible_hands_stop_instead_of_spending_all_coins_on_refresh():
    task = make_task()
    task.executor.frame = cv2.imread(str(FIXTURES / 'live_recommended_shop_settled.png'))
    task.observe = MagicMock(return_value=Screen.SHOP)
    task.synthesize = MagicMock()
    task.screenshot = MagicMock()
    task.coins = MagicMock(return_value=6)
    task.number = MagicMock(return_value=(3, 6))
    task.click_relative = MagicMock()
    # Reproduce the live failure independently of the template correction.
    # Gold marks are unresolved, so neither refresh nor Start is permitted.
    with patch('src.task.CubieWarsTask.recommended_item', return_value=False):
        with pytest.raises(RuntimeError, match=r'marks in slots \[3, 5\]'):
            task.prepare_round()
    task.click_relative.assert_not_called()


@pytest.mark.parametrize('name', ['live_shop', 'shop', 'matching'])
def test_unmarked_shop_gold_does_not_trigger_uncertain_recommendation_guard(name):
    image = frame(name)
    points = [(x, .392 if index < 3 else .64)
              for index, (x, _) in enumerate(CubieWarsTask.SHOP_SLOTS)]
    assert not any(possible_recommendation(image, point) for point in points)


@pytest.mark.parametrize('after_click', [False, True])
def test_late_coin_tutorial_interrupts_refresh_even_when_resources_are_readable(after_click):
    task = make_task()
    task.executor.frame = frame('live_shop')
    # Initial Store, then three settled empty scans, then a fresh check before
    # refresh. The tutorial may also arrive just after the allowed click.
    screens = [Screen.SHOP]*4 + ([Screen.SHOP, Screen.SPOTLIGHT] if after_click else [Screen.SPOTLIGHT])
    task.observe = MagicMock(side_effect=screens)
    task.synthesize = MagicMock()
    task.screenshot = MagicMock()
    task.coins = MagicMock(return_value=11)
    task.number = MagicMock(side_effect=lambda region, fraction=False: (3, 7) if fraction else 1)
    task.ocr = MagicMock(return_value=[SimpleNamespace(name='1')])
    task.shop_item = MagicMock(return_value=Item('Crystal', 'Adventurer', False, 0, 0, 1, '', 'Accessory'))
    task.click_relative = MagicMock()
    with pytest.raises(ShopInterrupted):
        task.prepare_round()
    assert task.click_relative.call_count == int(after_click)
    assert task.coins.call_count == 2  # No false coin-change assertion under the overlay.


@pytest.mark.parametrize('initial,following,clicks', [
    ('1.0X', ['1.5X', '2.0X'], 2),
    ('1,5x', ['2.0X'], 1),
    ('2.0X', [], 0),
])
def test_speed_advances_to_two_and_never_cycles_back(initial, following, clicks):
    task = make_task()
    task._texts = [Text(initial, .93, .16)]
    sequence = iter(following)

    def observe():
        task._texts = [Text(next(sequence), .93, .16)]
        return Screen.COMBAT

    task.observe = MagicMock(side_effect=observe)
    task.click_relative = MagicMock()
    task.ensure_combat_speed()
    assert task.click_relative.call_count == clicks


def test_speed_clicks_have_a_limit_if_game_does_not_advance():
    task = make_task()
    task._texts = [Text('1.0X', .93, .16)]
    task.observe = MagicMock(return_value=Screen.COMBAT)
    task.click_relative = MagicMock()
    task.screenshot = MagicMock()
    with pytest.raises(RuntimeError, match='after three clicks'):
        task.ensure_combat_speed()
    assert task.click_relative.call_count == 3


def test_speed_stops_if_combat_ends_during_adjustment():
    task = make_task()
    task._texts = [Text('1.0X', .93, .16)]
    task.observe = MagicMock(return_value=Screen.ROUND_RESULT)
    task.click_relative = MagicMock()
    task.ensure_combat_speed()
    task.click_relative.assert_called_once()


def test_first_result_trophy_tip_takes_priority_over_continue_prompt():
    # Actual labels in the 04:50 live OCR log; the tooltip hides the usual
    # Current Victories and Retries Available labels until it is dismissed.
    texts = [Text('Lose', .2, .2), Text('Round1', .45, .1), Text('WIN', .7, .2),
             Text('Win duels to earn Trophies. Collect every Trophy for', .2, .5),
             Text('complete victory', .2, .54), Text('Click anywhere to continue', .4, .9)]
    # Supplied story-stage screenshots show that this tip highlights the trophy,
    # which must be clicked before the ordinary result can be continued.
    assert classify(texts) == Screen.SPOTLIGHT
    assert spotlight_instruction(texts)[1] == (.5, .487)


@pytest.mark.parametrize('case', json.loads((FIXTURES/'item_categories_ocr.json').read_text(encoding='utf-8')),
                         ids=lambda case: case['name'])
def test_recorded_item_categories(case):
    item = parse_item([Text(**t) for t in case['texts']])
    assert item.category == case['category']
    if item.category != 'Sheet':
        assert item.cost == 0
    assert not re.search(r'\d+/\d+', item.name)


def test_purchase_order_is_sheet_weapon_accessory_relic_item():
    ordered = [Item(kind, 'Adventurer', kind == 'Sheet', 0, 0, 1, '', kind)
               for kind in ('Sheet', 'Weapon', 'Accessory', 'Relic', 'Item')]
    ranks = [item.purchase_rank('Adventurer', 6, 5, 1) for item in ordered]
    assert ranks == sorted(ranks, reverse=True)
    full = Item('Sword', 'Rapier', False, 3, 6, 2, '', 'Weapon')
    assert full.purchase_rank('Rapier', 2, 5, 1) is None


def test_accessory_category_is_read_from_header_not_weapon_text_in_description():
    item = parse_item([Text('Accessory name', .3, .1), Text('Adventurer', .3, .15),
                       Text('Accessory', .45, .15), Text('Grants Weapon DMG', .3, .25)])
    assert item.category == 'Accessory' and item.cost == 0


def test_shop_attempts_unmarked_sheets_then_weapons_then_recommended_accessories():
    task = make_task()
    task.executor.frame = frame('live_shop')
    task.config['Refreshes per round'] = 0
    task.observe = MagicMock(return_value=Screen.SHOP)
    task.synthesize = MagicMock()
    task.coins = MagicMock(return_value=6)
    task.number = MagicMock(return_value=(3, 6))
    task.ocr = MagicMock(side_effect=lambda *args, **kwargs:
                         [] if args == (.2, .075, .98, .7) else [SimpleNamespace(name='3')])
    task.drag_to_book = MagicMock(return_value=False)
    task._placement_reason = 'no_space'
    kinds = ['Weapon', 'Sheet', 'Accessory', 'Relic', 'Item']
    task.shop_item = MagicMock(side_effect=lambda index:
                              Item(kinds[index], 'Adventurer', kinds[index] == 'Sheet', 0, 0, 1, '', kinds[index]))
    task.scan_recommendations = MagicMock(return_value=[False, False, True, False, False])
    assert task.prepare_round() is True
    assert [call.args[0] for call in task.drag_to_book.call_args_list] == [
        task.SHOP_SLOTS[1], task.SHOP_SLOTS[0], task.SHOP_SLOTS[2]]


@pytest.mark.parametrize('reason,message', [('unknown', 'legal placement'),
                                           ('not_picked_up', 'after three attempts')])
def test_unreadable_placement_stops_before_rerolling_recommended_item(reason, message):
    task = make_task()
    task.executor.frame = frame('live_shop')
    task.observe = MagicMock(return_value=Screen.SHOP)
    task.synthesize = MagicMock()
    task.coins = MagicMock(return_value=6)
    task.number = MagicMock(return_value=(3, 6))
    task.ocr = MagicMock(return_value=[SimpleNamespace(name='1')])
    task.shop_item = MagicMock(return_value=Item('Crystal', 'Adventurer', False, 0, 0, 1, '', 'Accessory'))
    task.scan_recommendations = MagicMock(return_value=[True, False, False, False, False])
    task.drag_to_book = MagicMock(return_value=False)
    task._placement_reason = reason
    task.screenshot = MagicMock()
    task.click_relative = MagicMock()
    with pytest.raises(RuntimeError, match=message):
        task.prepare_round()
    task.click_relative.assert_not_called()


def test_sheet_purchase_expands_capacity_before_buying_unmarked_weapon():
    task = make_task()
    task.executor.frame = frame('live_shop')
    task.config['Refreshes per round'] = 0
    task.observe = MagicMock(return_value=Screen.SHOP)
    task.synthesize = MagicMock()
    # Resource readings before/after each drag, including rescans after buys.
    task.coins = MagicMock(side_effect=[6, 6, 5, 5, 5, 4, 4])
    bought = []
    task.number = MagicMock(side_effect=lambda *args, **kwargs: (3, 6 if bought else 3))
    task.ocr = MagicMock(return_value=[SimpleNamespace(name='1')])
    weapon = Item('Sword', 'Adventurer', False, 3, 6, 2, '', 'Weapon')
    sheet = Item('Sheet', 'Adventurer', True, 0, 0, 1, '', 'Sheet')
    task.shop_item = MagicMock(side_effect=lambda index: weapon if index == 0 else sheet)
    def scan():
        task._texts = [Text('Sold', *task.SHOP_SLOTS[i]) for i in range(5)
                       if i >= 2 or task.SHOP_SLOTS[i] in bought]
        return [False] * 5
    task.scan_recommendations = MagicMock(side_effect=scan)
    task.drag_to_book = MagicMock(side_effect=lambda source, *args: bought.append(source) or True)
    assert task.prepare_round() is True
    assert [call.args[0] for call in task.drag_to_book.call_args_list] == [
        task.SHOP_SLOTS[1], task.SHOP_SLOTS[0]]


def test_unmarked_accessories_are_inspected_but_not_bought_before_refresh():
    task = make_task()
    task.executor.frame = frame('live_shop')
    task.config['Refreshes per round'] = 2
    task.observe = MagicMock(return_value=Screen.SHOP)
    task.synthesize = MagicMock()
    task.coins = MagicMock(side_effect=[6, 6, 5, 5, 5, 4, 4])
    task.number = MagicMock(side_effect=lambda region, fraction=False: (3, 6) if fraction else 1)
    task.ocr = MagicMock(return_value=[SimpleNamespace(name='1')])
    task.shop_item = MagicMock(return_value=Item('Crystal', 'Adventurer', False, 0, 0, 1, '', 'Accessory'))
    task.drag_to_book = MagicMock()
    task.click_relative = MagicMock()
    assert task.prepare_round() is True
    assert task.shop_item.call_count == 15
    task.drag_to_book.assert_not_called()
    assert task.click_relative.call_count == 2
    assert all(call.args == (.895, .574) for call in task.click_relative.call_args_list)


def test_actual_coin_crop_ocr_works_after_enlarging():
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr
    engine = ONNXPaddleOcr(use_openvino=True, use_npu=True)
    tile = cv2.imread(str(FIXTURES/'live_coins_crop.png'))
    assert tile.shape == (44, 61, 3)
    processed = number_frame(tile)
    assert processed.shape == (132, 183, 3)
    labels = [(value, confidence) for _, (value, confidence) in engine.ocr(processed)[0]]
    assert len(labels) == 1 and labels[0][0] == '6' and labels[0][1] > .65
    price = cv2.imread(str(FIXTURES/'live_price_crop.png'))
    prices = [(value, confidence) for _, (value, confidence) in engine.ocr(number_frame(price))[0]]
    assert len(prices) == 1 and prices[0][0] == '3' and prices[0][1] > .65
    # The full-screen log read this native button as Stari. Replay the exact
    # focused crop (same rounding as the framework) through the real OCR engine.
    image = cv2.imread(str(FIXTURES / 'live_recommended_shop.png'))
    start = image[954:1004, 1642:1790]
    labels = [(value, confidence) for _, (value, confidence) in engine.ocr(number_frame(start))[0]]
    assert len(labels) == 1 and labels[0][0] == 'Start' and labels[0][1] > .75
