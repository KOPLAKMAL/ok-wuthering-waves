"""Foreground cursor movement for the Cubie Wars inventory interface."""

from contextlib import contextmanager
import math
import time

import win32con
import pydirectinput

from ok.device.interaction_methods.post_message import PostMessageInteraction
from ok.device.interaction_methods.pydirect import PyDirectInteraction


class CubieWarsInteraction(PostMessageInteraction):
    """Use one foreground native input stream for the inventory UI."""

    BUTTON_MASKS = {"left": win32con.MK_LBUTTON, "middle": win32con.MK_MBUTTON,
                    "right": win32con.MK_RBUTTON}

    def __init__(self, capture, hwnd_window):
        super().__init__(capture, hwnd_window)
        self.cursor = PyDirectInteraction(capture, hwnd_window)
        self.held_button = 0
        self._held_keys = set()

    def activate(self, hwnd=None):
        # WWOneTimeTask.run calls activate before entering the task. Keep this
        # path native too, rather than posting a synthetic WM_ACTIVATE.
        self.try_activate()

    def try_activate(self):
        if not self.hwnd_window.is_foreground():
            if self.held_button:
                raise RuntimeError("Cubie Wars lost foreground during a held drag")
            self.hwnd_window.bring_to_front()
        if not self.hwnd_window.is_foreground():
            raise RuntimeError("Cubie Wars could not bring the game to the foreground")

    def move(self, x, y, down_btn=0):
        self.try_activate()
        if x == -1 or y == -1:
            return
        x, y = self.capture.get_abs_cords(x, y)
        self._move_absolute(x, y)

    def _move_absolute(self, x, y):
        if self.held_button:
            # Feed intermediate native motion events rather than teleporting
            # between cells. Recheck focus before every injected movement.
            start_x, start_y = pydirectinput.position()
            # Leave room for integer rounding to keep every segment <=16px.
            steps = max(1, math.ceil(math.hypot(x - start_x, y - start_y) / 14))
            for step in range(1, steps + 1):
                self.try_activate()
                pydirectinput.moveTo(round(start_x + (x - start_x) * step / steps),
                                     round(start_y + (y - start_y) * step / steps), _pause=False)
                if step < steps:
                    time.sleep(.01)
        else:
            pydirectinput.moveTo(x, y, _pause=False)

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        mask = self.BUTTON_MASKS[key]
        if key in self._held_keys:
            raise RuntimeError(f"Cubie Wars is already holding the {key} mouse button")
        self.try_activate()
        self.move(x, y)
        self._held_keys.add(key)
        self.held_button |= mask
        try:
            pydirectinput.mouseDown(button=key, _pause=False)
        except BaseException:
            self.mouse_up(key)
            raise

    def mouse_up(self, key="left"):
        # Match the native press at the current cursor position. The framework
        # mouse_up skips release after focus loss; cleanup must always release.
        try:
            pydirectinput.mouseUp(button=key, _pause=False)
        finally:
            self._held_keys.discard(key)
            self.held_button &= ~self.BUTTON_MASKS[key]

    def release_buttons(self):
        """Release every native button, including an interrupted rotation chord."""
        error = None
        for key in tuple(self._held_keys):
            try:
                self.mouse_up(key)
            except BaseException as exc:
                error = error or exc
        if error is not None:
            raise error

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=.01, move=True, key="left"):
        if key in self._held_keys:
            raise RuntimeError(f"Cubie Wars is already holding the {key} mouse button")
        self.try_activate()
        origin = pydirectinput.position() if move_back else None
        if move:
            self.move(x, y)
        try:
            self.mouse_down(key=key)
            time.sleep(down_time)
        finally:
            if key in self._held_keys:
                self.mouse_up(key)
        if origin is not None:
            self.try_activate()
            self._move_absolute(*origin)

    def right_click(self, x=-1, y=-1, move_back=False, name=None):
        return self.click(x, y, move_back=move_back, name=name, key="right")

    def send_key(self, key, down_time=.01):
        self.try_activate()
        return self.cursor.send_key(key, down_time)

    def send_key_down(self, key, activate=True):
        self.try_activate()
        return self.cursor.send_key_down(key)

    def send_key_up(self, key):
        self.try_activate()
        return self.cursor.send_key_up(key)

    def scroll(self, x, y, scroll_amount):
        self.try_activate()
        if self.held_button:
            raise RuntimeError("Cubie Wars cannot scroll while holding an item")
        return self.cursor.scroll(x, y, scroll_amount)


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
                interaction.release_buttons()
        finally:
            executor.device_manager.interaction = original
