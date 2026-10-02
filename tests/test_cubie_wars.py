import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import pytest

from src.task.CubieWarsTask import CubieWarsTask
from src.task.cubie_wars.model import (
    ADVENTURE_COUNT, ASTRITE_TOTAL, Screen, Text, classify, next_stage, parse_item,
)
from src.task.cubie_wars.vision import (
    capacity_tag, green_check, placement_points, recipe_available,
    valid_preview, white_check, yellow_button,
)


FIXTURES = Path(__file__).parent / 'images' / 'cubie_wars'
CASES = json.loads((FIXTURES / 'ocr.json').read_text(encoding='utf-8'))


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
