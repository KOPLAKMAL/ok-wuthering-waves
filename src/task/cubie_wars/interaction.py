"""Foreground cursor movement for the Cubie Wars inventory interface."""

from contextlib import contextmanager

import win32api
import win32con
import win32gui

from ok.device.interaction_methods.post_message import PostMessageInteraction
from ok.device.interaction_methods.pydirect import PyDirectInteraction


class CubieWarsInteraction(PostMessageInteraction):
    """Keep window messages, but move the real cursor for Unreal hover/drag."""

    def __init__(self, capture, hwnd_window):
        super().__init__(capture, hwnd_window)
        self.cursor = PyDirectInteraction(capture, hwnd_window)
        self.held_button = 0

    def try_activate(self):
        if not self.hwnd_window.is_foreground():
            self.hwnd_window.bring_to_front()
        if not self.hwnd_window.is_foreground():
            raise RuntimeError("Cubie Wars could not bring the game to the foreground")
        super().try_activate()

    def move(self, x, y, down_btn=0):
        self.try_activate()
        self.cursor.move(x, y)
        return super().move(x, y, down_btn=down_btn or self.held_button)

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        self.move(x, y)
        super().mouse_down(x, y, name=name, key=key)
        self.held_button = {"left": win32con.MK_LBUTTON,
                            "middle": win32con.MK_MBUTTON,
                            "right": win32con.MK_RBUTTON}[key]

    def mouse_up(self, key="left"):
        # The framework's PostMessage release uses mouse_pos=(0, 0), which
        # move() never updates. Release at the last target, including cancel.
        actions = {"left": win32con.WM_LBUTTONUP, "middle": win32con.WM_MBUTTONUP,
                   "right": win32con.WM_RBUTTONUP}
        try:
            x, y = self.bg_mouse_pos
            # bg_mouse_pos is already in top-window client coordinates.
            base = self.hwnd_window.top_hwnd or self.hwnd_window.hwnd
            local = win32gui.ScreenToClient(self.hwnd, win32gui.ClientToScreen(base, (x, y)))
            self.post(actions[key], 0, win32api.MAKELONG(*local))
        finally:
            self.held_button = 0


@contextmanager
def cubie_cursor(executor):
    """Restore the shared backend even when Stop or a game error interrupts."""
    original = executor.interaction
    if not isinstance(original, PostMessageInteraction):
        yield
        return
    interaction = CubieWarsInteraction(original.capture, original.hwnd_window)
    executor.device_manager.interaction = interaction
    try:
        yield
    finally:
        try:
            if interaction.held_button:
                interaction.mouse_up()
        finally:
            executor.device_manager.interaction = original
