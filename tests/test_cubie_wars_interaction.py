from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import win32api
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
    window.get_top_window_cords.side_effect = lambda x, y: (x, y)
    with patch('src.task.cubie_wars.interaction.PyDirectInteraction') as cursor, \
            patch('win32gui.PostMessage') as post, \
            patch('win32gui.ClientToScreen', side_effect=lambda handle, point: point), \
            patch('win32gui.ScreenToClient', side_effect=lambda handle, point: point):
        with patch('src.task.cubie_wars.interaction.pydirectinput.mouseUp') as release, \
                patch('src.task.cubie_wars.interaction.pydirectinput.moveTo') as motion:
            capture.native_motion = motion
            yield capture, window, cursor.return_value, post, release


def test_hover_moves_real_cursor_then_sends_window_position(windows):
    capture, window, cursor, post, release = windows
    interaction = CubieWarsInteraction(capture, window)
    interaction.move(1471, 300)
    cursor.move.assert_called_once_with(1471, 300)
    capture.native_motion.assert_not_called()
    assert post.call_args.args == (17, win32con.WM_MOUSEMOVE, 0, win32api.MAKELONG(1471, 300))


def test_drag_keeps_left_button_and_releases_at_drop_not_origin(windows):
    capture, window, cursor, post, release = windows
    interaction = CubieWarsInteraction(capture, window)
    interaction.mouse_down(1471, 300)
    cursor.mouse_down.assert_called_once_with(1471, 300, name=None, key='left')
    # No queued unpressed hover or activation may race the native press.
    post.assert_not_called()
    post.reset_mock()
    interaction.move(780, 430)
    cursor.move.assert_not_called()
    assert [c.args for c in capture.native_motion.call_args_list] == [(1471, 300), (780, 430)]
    assert all(c.kwargs == {'_pause': False} for c in capture.native_motion.call_args_list)
    post.assert_not_called()
    # Even a lost focus must not prevent the button-up cleanup.
    window.is_foreground.return_value = False
    interaction.mouse_up()
    release.assert_called_once_with(button='left')
    post.assert_not_called()
    assert interaction.held_button == 0


def test_unavailable_foreground_stops_before_mouse_movement(windows):
    capture, window, cursor, post, release = windows
    window.is_foreground.return_value = False
    with pytest.raises(RuntimeError, match='foreground'):
        CubieWarsInteraction(capture, window).move(1471, 300)
    window.bring_to_front.assert_called_once()
    cursor.move.assert_not_called()
    capture.native_motion.assert_not_called()
    post.assert_not_called()


def test_backend_restores_and_releases_when_task_is_stopped(windows):
    capture, window, cursor, post, release = windows
    original = PostMessageInteraction(capture, window)
    # Exercise the real read-only executor.interaction property.
    executor = object.__new__(TaskExecutor)
    executor.device_manager = SimpleNamespace(interaction=original)
    with pytest.raises(RuntimeError, match='Stopped'):
        with cubie_cursor(executor):
            assert isinstance(executor.interaction, CubieWarsInteraction)
            executor.interaction.mouse_down(1471, 300)
            executor.interaction.move(780, 430)
            raise RuntimeError('Stopped')
    assert executor.interaction is original
    release.assert_called_once_with(button='left')


def test_browser_backend_is_preserved():
    original = SimpleNamespace()
    executor = object.__new__(TaskExecutor)
    executor.device_manager = SimpleNamespace(interaction=original)
    with cubie_cursor(executor):
        assert executor.interaction is original
    assert executor.interaction is original


def test_held_motion_uses_capture_window_offsets_without_posted_hover(windows):
    capture, window, cursor, post, release = windows
    capture.get_abs_cords.side_effect = lambda x, y: (x+319, y+180)
    interaction = CubieWarsInteraction(capture, window)
    interaction.mouse_down(100, 200)
    interaction.move(300, 400)
    assert [c.args for c in capture.native_motion.call_args_list] == [(419, 380), (619, 580)]
    assert interaction.held_button == win32con.MK_LBUTTON
    cursor.move.assert_not_called()
    post.assert_not_called()
    interaction.mouse_up()
    release.assert_called_once_with(button='left')


def test_focus_failure_during_held_motion_releases_without_moving(windows):
    capture, window, cursor, post, release = windows
    interaction = CubieWarsInteraction(capture, window)
    interaction.mouse_down(100, 200)
    capture.native_motion.reset_mock()
    window.is_foreground.return_value = False
    try:
        with pytest.raises(RuntimeError, match='foreground'):
            interaction.move(300, 400)
    finally:
        interaction.mouse_up()
    capture.native_motion.assert_not_called()
    release.assert_called_once_with(button='left')
