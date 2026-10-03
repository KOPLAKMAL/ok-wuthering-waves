import math
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import win32con

from ok.device.interaction_methods.post_message import PostMessageInteraction
from ok.task.TaskExecutor import TaskExecutor
from src.task.cubie_wars.interaction import CubieWarsInteraction, cubie_cursor


@pytest.fixture
def windows():
    capture, window = MagicMock(), MagicMock()
    capture.get_abs_cords.side_effect = lambda x, y: (x, y)
    window.hwnd, window.top_hwnd, window.hwnds = 17, None, []
    window.is_foreground.return_value = True
    state = SimpleNamespace(position=(0, 0), buttons=set(), motions=[], events=[])
    # Mock the complete native namespace and framework cursor: these tests
    # must never activate a window, move the desktop cursor or send OS input.
    with patch('src.task.cubie_wars.interaction.pydirectinput') as native, \
            patch('src.task.cubie_wars.interaction.PyDirectInteraction') as cursor, \
            patch('src.task.cubie_wars.interaction.time.sleep') as sleep, \
            patch('win32gui.PostMessage') as post:
        native.position.side_effect = lambda: state.position

        def motion(x, y, **kwargs):
            state.position = (x, y)
            state.motions.append((x, y, frozenset(state.buttons)))
            state.events.append(('move', x, y))

        def press(button, **kwargs):
            state.buttons.add(button)
            state.events.append(('down', button, state.position))

        def release(button, **kwargs):
            state.buttons.discard(button)
            state.events.append(('up', button, state.position))

        native.moveTo.side_effect = motion
        native.mouseDown.side_effect = press
        native.mouseUp.side_effect = release
        yield SimpleNamespace(capture=capture, window=window, cursor=cursor.return_value,
                              native=native, state=state, post=post, sleep=sleep)


def adapter(windows):
    return CubieWarsInteraction(windows.capture, windows.window)


def test_hover_uses_native_offset_coordinates_without_window_messages(windows):
    windows.capture.get_abs_cords.side_effect = lambda x, y: (x + 319, y + 180)
    adapter(windows).move(1471, 300)
    windows.native.moveTo.assert_called_once_with(1790, 480, _pause=False)
    windows.cursor.move.assert_not_called()
    windows.post.assert_not_called()


@pytest.mark.parametrize('target', [(300, 400), (105, 203), (100, 200)])
def test_held_motion_is_bounded_reaches_endpoint_and_keeps_native_button(windows, target):
    interaction = adapter(windows)
    interaction.mouse_down(100, 200)
    windows.state.motions.clear()
    windows.sleep.reset_mock()
    interaction.move(*target)
    positions = [(100, 200)] + [(x, y) for x, y, _ in windows.state.motions]
    assert positions[-1] == target
    assert all(math.dist(a, b) <= 16 for a, b in zip(positions, positions[1:]))
    assert all(buttons == {'left'} for _, _, buttons in windows.state.motions)
    assert windows.sleep.call_count == max(0, len(windows.state.motions) - 1)
    assert all(call.args == (.01,) for call in windows.sleep.call_args_list)
    windows.post.assert_not_called()
    interaction.mouse_up()
    assert windows.state.events[-1] == ('up', 'left', target)
    assert not windows.state.buttons
    assert interaction.held_button == 0


def test_held_motion_applies_window_offset_exactly_once(windows):
    windows.capture.get_abs_cords.side_effect = lambda x, y: (x + 319, y + 180)
    interaction = adapter(windows)
    interaction.mouse_down(100, 200)
    interaction.move(300, 400)
    assert windows.state.position == (619, 580)
    assert windows.state.events[1] == ('down', 'left', (419, 380))
    assert interaction.held_button == win32con.MK_LBUTTON
    windows.post.assert_not_called()


def test_unavailable_foreground_stops_before_native_input(windows):
    windows.window.is_foreground.return_value = False
    with pytest.raises(RuntimeError, match='foreground'):
        adapter(windows).move(1471, 300)
    windows.window.bring_to_front.assert_called_once()
    windows.native.moveTo.assert_not_called()
    windows.post.assert_not_called()


def test_focus_loss_between_drag_steps_stops_motion_and_releases(windows):
    interaction = adapter(windows)
    interaction.mouse_down(100, 200)
    windows.state.motions.clear()
    windows.native.moveTo.reset_mock()

    def lose_focus(_):
        windows.window.is_foreground.return_value = False

    windows.sleep.side_effect = lose_focus
    try:
        with pytest.raises(RuntimeError, match='foreground'):
            interaction.move(300, 400)
    finally:
        interaction.mouse_up()
    assert len(windows.state.motions) == 1
    windows.window.bring_to_front.assert_not_called()
    assert not windows.state.buttons
    assert interaction.held_button == 0
    windows.post.assert_not_called()


@pytest.mark.parametrize('key', ['left', 'right', 'middle'])
def test_click_native_press_release_and_move_back(windows, key):
    windows.state.position = (50, 60)
    interaction = adapter(windows)
    interaction.click(100, 200, move_back=True, down_time=.2, key=key)
    assert windows.state.events == [('move', 100, 200), ('down', key, (100, 200)),
                                   ('up', key, (100, 200)), ('move', 50, 60)]
    windows.sleep.assert_called_once_with(.2)
    assert not windows.state.buttons
    windows.post.assert_not_called()


def test_click_move_false_uses_current_position(windows):
    windows.state.position = (50, 60)
    adapter(windows).click(100, 200, move=False)
    windows.native.moveTo.assert_not_called()
    assert windows.state.events == [('down', 'left', (50, 60)), ('up', 'left', (50, 60))]


def test_interrupted_click_always_releases_even_after_focus_loss(windows):
    interaction = adapter(windows)

    def interrupt(_):
        windows.window.is_foreground.return_value = False
        raise RuntimeError('Stopped')

    windows.sleep.side_effect = interrupt
    with pytest.raises(RuntimeError, match='Stopped'):
        interaction.click(100, 200)
    assert windows.state.events[-1] == ('up', 'left', (100, 200))
    assert not windows.state.buttons
    assert interaction.held_button == 0


def test_native_press_failure_still_attempts_matching_release(windows):
    windows.native.mouseDown.side_effect = RuntimeError('Native input failed')
    interaction = adapter(windows)
    with pytest.raises(RuntimeError, match='Native input failed'):
        interaction.mouse_down(100, 200, key='middle')
    windows.native.mouseUp.assert_called_once_with(button='middle', _pause=False)
    assert interaction.held_button == 0


def test_right_click_and_keys_never_post_window_messages(windows):
    interaction = adapter(windows)
    interaction.right_click(100, 200)
    interaction.mouse_down(100, 200)
    interaction.send_key('r', .05)
    interaction.send_key_down('r')
    interaction.send_key_up('r')
    windows.cursor.send_key.assert_called_once_with('r', .05)
    windows.cursor.send_key_down.assert_called_once_with('r')
    windows.cursor.send_key_up.assert_called_once_with('r')
    assert windows.state.events[1] == ('down', 'right', (100, 200))
    assert windows.state.buttons == {'left'}
    windows.post.assert_not_called()
    interaction.mouse_up()


def test_scroll_is_native_and_rejected_while_holding_item(windows):
    interaction = adapter(windows)
    interaction.scroll(100, 200, -2)
    windows.cursor.scroll.assert_called_once_with(100, 200, -2)
    interaction.mouse_down(100, 200)
    with pytest.raises(RuntimeError, match='scroll while holding'):
        interaction.scroll(100, 200, -2)
    assert windows.cursor.scroll.call_count == 1
    windows.post.assert_not_called()
    interaction.mouse_up()


@pytest.mark.parametrize('key', ['left', 'middle'])
def test_backend_restores_and_releases_actual_button_when_task_stops(windows, key):
    original = PostMessageInteraction(windows.capture, windows.window)
    executor = object.__new__(TaskExecutor)
    executor.device_manager = SimpleNamespace(interaction=original)
    with pytest.raises(RuntimeError, match='Stopped'):
        with cubie_cursor(executor):
            executor.interaction.mouse_down(100, 200, key=key)
            executor.interaction.move(300, 400)
            raise RuntimeError('Stopped')
    assert executor.interaction is original
    windows.native.mouseUp.assert_called_once_with(button=key, _pause=False)
    assert not windows.state.buttons
    windows.post.assert_not_called()


def test_browser_backend_is_preserved():
    original = SimpleNamespace()
    executor = object.__new__(TaskExecutor)
    executor.device_manager = SimpleNamespace(interaction=original)
    with cubie_cursor(executor):
        assert executor.interaction is original
    assert executor.interaction is original


def test_task_activation_checks_real_foreground_without_posting_messages(windows):
    interaction = adapter(windows)
    interaction.activate(999)
    windows.window.bring_to_front.assert_not_called()
    windows.post.assert_not_called()
    windows.window.is_foreground.side_effect = [False, True]
    interaction.activate()
    windows.window.bring_to_front.assert_called_once()
    windows.post.assert_not_called()


def test_task_activation_rejects_unavailable_foreground_without_posting(windows):
    windows.window.is_foreground.return_value = False
    with pytest.raises(RuntimeError, match='foreground'):
        adapter(windows).activate()
    windows.post.assert_not_called()
    windows.native.moveTo.assert_not_called()


def test_right_rotation_click_preserves_held_left_and_subsequent_drag(windows):
    interaction = adapter(windows)
    interaction.mouse_down(100, 200)
    interaction.click(move=False, key='right')
    assert windows.state.events == [('move', 100, 200), ('down', 'left', (100, 200)),
                                   ('down', 'right', (100, 200)), ('up', 'right', (100, 200))]
    assert interaction.held_button == win32con.MK_LBUTTON
    assert windows.state.buttons == {'left'}
    windows.state.motions.clear()
    interaction.move(300, 400)
    assert windows.state.position == (300, 400)
    assert all(buttons == {'left'} for _, _, buttons in windows.state.motions)
    interaction.release_buttons()
    assert windows.state.events[-1] == ('up', 'left', (300, 400))
    assert not windows.state.buttons
    windows.post.assert_not_called()


def test_two_button_hold_tracks_mask_and_releases_only_requested_button(windows):
    interaction = adapter(windows)
    interaction.mouse_down(100, 200)
    interaction.mouse_down(key='right')
    assert interaction.held_button == win32con.MK_LBUTTON | win32con.MK_RBUTTON
    assert windows.state.buttons == {'left', 'right'}
    interaction.mouse_up(key='right')
    assert interaction.held_button == win32con.MK_LBUTTON
    assert windows.state.buttons == {'left'}
    interaction.mouse_up()
    assert interaction.held_button == 0


def test_context_cleanup_releases_both_buttons_after_interrupted_chord(windows):
    original = PostMessageInteraction(windows.capture, windows.window)
    executor = object.__new__(TaskExecutor)
    executor.device_manager = SimpleNamespace(interaction=original)
    with pytest.raises(RuntimeError, match='Stopped'):
        with cubie_cursor(executor):
            executor.interaction.mouse_down(100, 200)
            executor.interaction.mouse_down(key='right')
            windows.window.is_foreground.return_value = False
            raise RuntimeError('Stopped')
    assert executor.interaction is original
    assert {call.kwargs['button'] for call in windows.native.mouseUp.call_args_list} == {'left', 'right'}
    assert not windows.state.buttons
    windows.post.assert_not_called()


def test_interrupted_right_click_releases_right_and_context_releases_left(windows):
    original = PostMessageInteraction(windows.capture, windows.window)
    executor = object.__new__(TaskExecutor)
    executor.device_manager = SimpleNamespace(interaction=original)
    with pytest.raises(RuntimeError, match='Stopped'):
        with cubie_cursor(executor):
            executor.interaction.mouse_down(100, 200)
            windows.sleep.side_effect = RuntimeError('Stopped')
            executor.interaction.click(key='right', move=False)
    assert [call.kwargs['button'] for call in windows.native.mouseUp.call_args_list] == ['right', 'left']
    assert executor.interaction is original
    assert not windows.state.buttons


def test_nested_left_click_is_rejected_without_releasing_existing_drag(windows):
    interaction = adapter(windows)
    interaction.mouse_down(100, 200)
    with pytest.raises(RuntimeError, match='already holding'):
        interaction.click(300, 400)
    assert windows.state.buttons == {'left'}
    assert interaction.held_button == win32con.MK_LBUTTON
    windows.native.mouseUp.assert_not_called()
    assert windows.state.position == (100, 200)
    interaction.release_buttons()


def test_failed_right_press_releases_right_preserves_existing_left(windows):
    interaction = adapter(windows)
    interaction.mouse_down(100, 200)
    windows.native.mouseDown.side_effect = RuntimeError('Native input failed')
    with pytest.raises(RuntimeError, match='Native input failed'):
        interaction.click(key='right', move=False)
    windows.native.mouseUp.assert_called_once_with(button='right', _pause=False)
    assert windows.state.buttons == {'left'}
    assert interaction.held_button == win32con.MK_LBUTTON
    interaction.release_buttons()


def test_context_restore_and_other_releases_survive_one_release_failure(windows):
    original = PostMessageInteraction(windows.capture, windows.window)
    executor = object.__new__(TaskExecutor)
    executor.device_manager = SimpleNamespace(interaction=original)
    windows.native.mouseUp.side_effect = [RuntimeError('Release failed'), None]
    with pytest.raises(RuntimeError, match='Release failed'):
        with cubie_cursor(executor):
            interaction = executor.interaction
            interaction.mouse_down(100, 200)
            interaction.mouse_down(key='right')
    assert {call.kwargs['button'] for call in windows.native.mouseUp.call_args_list} == {'left', 'right'}
    assert interaction.held_button == 0
    assert not interaction._held_keys
    assert executor.interaction is original
