"""Foreground cursor movement for the Cubie Wars inventory interface."""

from contextlib import contextmanager

import win32con
import pydirectinput

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
        if not self.held_button:
            super().try_activate()

    def move(self, x, y, down_btn=0):
        self.try_activate()
        if self.held_button:
            # PyDirect.move uses SetCursorPos, while its press uses SendInput.
            # Deliver held movement through SendInput too so the game receives
            # actual mouse motion, with the capture's window offsets applied.
            x, y = self.capture.get_abs_cords(x, y)
            pydirectinput.moveTo(x, y, _pause=False)
            return None
        self.cursor.move(x, y)
        return super().move(x, y, down_btn=down_btn or self.held_button)

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        # Mark the native drag before moving: do not queue an unpressed
        # WM_MOUSEMOVE/WM_ACTIVATE immediately before the physical press.
        # A late posted hover event can contradict the native button state.
        self.held_button = {"left": win32con.MK_LBUTTON,
                            "middle": win32con.MK_MBUTTON,
                            "right": win32con.MK_RBUTTON}[key]
        self.move(x, y)
        self.cursor.mouse_down(x, y, name=name, key=key)

    def mouse_up(self, key="left"):
        # Match the native press at the current cursor position. The framework
        # mouse_up skips release after focus loss; cleanup must always release.
        try:
            pydirectinput.mouseUp(button=key)
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
