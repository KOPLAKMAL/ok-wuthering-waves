import json
import re
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import pytest

from src.task.CubieWarsTask import CubieWarsTask, ShopInterrupted
from src.task.cubie_wars.model import (
    ADVENTURE_COUNT, ASTRITE_TOTAL, Item, Screen, Text, classify, next_stage, parse_item,
    spotlight_instruction,
)
from src.task.cubie_wars.vision import (
    capacity_tag, green_check, number_frame, placement_points, possible_recommendation,
    recipe_available, recommended_item,
    spotlight_target, stage_label_frame, valid_preview, white_check, yellow_button,
)


FIXTURES = Path(__file__).parent / 'images' / 'cubie_wars'
CASES = json.loads((FIXTURES / 'ocr.json').read_text(encoding='utf-8'))
LIVE_HOVER = json.loads((FIXTURES / 'live_hover_ocr.json').read_text(encoding='utf-8'))


def frame(name):
    return cv2.imread(str(FIXTURES / (name + '.jpg')))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['name'])
def test_recording_screen_recognition(case):
    assert classify([Text(**t) for t in case['texts']]) == Screen[case['expected']]


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
    task.config = dict(task.default_config)
    task.executor.method.width = 1280
    task.executor.method.height = 720
    task.move_relative = MagicMock()
    task.sleep = MagicMock()
    task.next_frame = MagicMock()
    task.mouse_down = MagicMock()
    task.mouse_up = MagicMock()
    task.send_key = MagicMock()
    return task


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


def test_failed_drag_returns_to_source_rotates_with_r_and_releases():
    task = make_task()
    with patch('src.task.CubieWarsTask.placement_points', return_value=[(.3, .3)]), \
            patch('src.task.CubieWarsTask.valid_preview', return_value=False):
        assert not task.drag_to_book((.636, .278), frame('shop'))
    task.mouse_down.assert_called_once_with(814, 200)
    assert task.send_key.call_count == 4
    assert all(call.args == ('r',) for call in task.send_key.call_args_list)
    task.move_relative.assert_called_with(.636, .278)
    task.mouse_up.assert_called_once()


def test_stop_during_drag_still_releases_mouse():
    task = make_task()
    task.next_frame.side_effect = RuntimeError('Stopped')
    with patch('src.task.CubieWarsTask.placement_points', return_value=[(.3, .3)]):
        with pytest.raises(RuntimeError, match='Stopped'):
            task.drag_to_book((.636, .278), frame('shop'))
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


def test_resume_story_rejoins_stage_verification_and_rewards():
    task = make_task()
    task.config['Mode'] = 'Resume Story stage'
    task.observe = MagicMock(return_value=Screen.GUIDE)
    task.is_browser = MagicMock(return_value=False)
    task.play_stage = MagicMock()
    task.wait_screen = MagicMock()
    task.close_page = MagicMock()
    task.complete_mode = MagicMock()
    task.claim_rewards = MagicMock()
    with patch('src.task.CubieWarsTask.is_admin', return_value=True), \
            patch('src.task.CubieWarsTask.WWOneTimeTask.run'):
        task.run()
    task.play_stage.assert_called_once_with('Story')
    assert [call.args for call in task.complete_mode.call_args_list] == [('Story',), ('Adventure',)]
    task.claim_rewards.assert_called_once()


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
                         [] if missing == 'price' or args == (.2, .075, .68, .7)
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
                         tooltip if args == (.2, .075, .68, .7) else [SimpleNamespace(name='1')])
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
                         boxes if args == (.2, .075, .68, .7) else [SimpleNamespace(name='1')])
    task.drag_to_book = MagicMock(return_value=True)
    task.click_relative = MagicMock()
    assert task.prepare_round() is True
    task.drag_to_book.assert_called_once()
    assert task.drag_to_book.call_args.args[0] == task.SHOP_SLOTS[1]
    task.click_relative.assert_not_called()


def test_active_tooltip_is_cleared_before_round_preparation_or_start():
    task = make_task()
    screens = iter([Screen.ITEM_TOOLTIP, Screen.SHOP, Screen.SHOP, Screen.STAGE_RESULT])

    def observe():
        screen = next(screens)
        task._texts = [Text(**t) for t in LIVE_HOVER['texts']] if screen == Screen.ITEM_TOOLTIP else [
            Text('Round 1 - Store', .6, .1)]
        return screen

    task.observe = MagicMock(side_effect=observe)
    task.prepare_round = MagicMock(return_value=True)
    task.start_round = MagicMock()
    task.click_text = MagicMock()
    task.play_stage('Story')
    task.move_relative.assert_called_once_with(.55, .78)
    task.prepare_round.assert_called_once()
    task.start_round.assert_called_once()


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


def test_first_result_trophy_tip_does_not_hide_the_continue_screen():
    # Actual labels in the 04:50 live OCR log; the tooltip hides the usual
    # Current Victories and Retries Available labels until it is dismissed.
    texts = [Text('Lose', .2, .2), Text('Round1', .45, .1), Text('WIN', .7, .2),
             Text('Win duels to earn Trophies. Collect every Trophy for', .2, .5),
             Text('complete victory', .2, .54), Text('Click anywhere to continue', .4, .9)]
    assert classify(texts) == Screen.ROUND_RESULT


@pytest.mark.parametrize('case', json.loads((FIXTURES/'item_categories_ocr.json').read_text(encoding='utf-8')),
                         ids=lambda case: case['name'])
def test_recorded_item_categories(case):
    item = parse_item([Text(**t) for t in case['texts']])
    assert item.category == case['category']
    if item.category != 'Sheet':
        assert item.cost == 0
    assert not re.search(r'\d+/\d+', item.name)


def test_purchase_order_is_weapon_sheet_accessory_relic_item():
    ordered = [Item(kind, 'Adventurer', kind == 'Sheet', 0, 0, 1, '', kind)
               for kind in ('Weapon', 'Sheet', 'Accessory', 'Relic', 'Item')]
    ranks = [item.purchase_rank('Adventurer', 6, 5, 1) for item in ordered]
    assert ranks == sorted(ranks, reverse=True)
    full = Item('Sword', 'Rapier', False, 3, 6, 2, '', 'Weapon')
    assert full.purchase_rank('Rapier', 2, 5, 1) is None


def test_accessory_category_is_read_from_header_not_weapon_text_in_description():
    item = parse_item([Text('Accessory name', .3, .1), Text('Adventurer', .3, .15),
                       Text('Accessory', .45, .15), Text('Grants Weapon DMG', .3, .25)])
    assert item.category == 'Accessory' and item.cost == 0


def test_shop_attempts_recommended_weapons_before_sheets_and_accessories():
    task = make_task()
    task.executor.frame = frame('live_shop')
    task.config['Refreshes per round'] = 0
    task.observe = MagicMock(return_value=Screen.SHOP)
    task.synthesize = MagicMock()
    task.coins = MagicMock(return_value=6)
    task.number = MagicMock(return_value=(3, 6))
    task.ocr = MagicMock(side_effect=lambda *args, **kwargs:
                         [] if args == (.2, .075, .68, .7) else [SimpleNamespace(name='3')])
    task.drag_to_book = MagicMock(return_value=False)
    items = {x: Item(kind, 'Adventurer', kind == 'Sheet', 0, 0, 1, '', kind)
             for x, kind in zip((.636, .766, .895), ('Weapon', 'Sheet', 'Accessory'))}
    with patch('src.task.CubieWarsTask.recommended_item', side_effect=lambda image, point: point[1] == .392), \
            patch('src.task.CubieWarsTask.parse_item', side_effect=lambda texts:
                  items[task.move_relative.call_args.args[0]]):
        assert task.prepare_round() is True
    assert [call.args[0] for call in task.drag_to_book.call_args_list] == list(task.SHOP_SLOTS[:3])


def test_no_thumb_skips_tooltips_and_refreshes_before_combat():
    task = make_task()
    task.executor.frame = frame('live_shop')
    task.config['Refreshes per round'] = 2
    task.observe = MagicMock(return_value=Screen.SHOP)
    task.synthesize = MagicMock()
    task.coins = MagicMock(side_effect=[6, 6, 5, 5, 5, 4, 4])
    task.number = MagicMock(side_effect=lambda region, fraction=False: (3, 6) if fraction else 1)
    task.ocr = MagicMock()
    task.drag_to_book = MagicMock()
    task.click_relative = MagicMock()
    assert task.prepare_round() is True
    task.ocr.assert_not_called()
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
