"""Enregistre la dernière phrase tapée (sans bloquer le clavier)."""

from __future__ import annotations

import threading
import time

from pynput import keyboard
from pynput.keyboard import Key

try:
    from Xlib import X, display
    from Xlib.protocol import event as xevent

    _HAS_XLIB = True
except Exception:  # noqa: BLE001
    _HAS_XLIB = False

_MOD_CTRL = {Key.ctrl, Key.ctrl_l, Key.ctrl_r}
_MOD_ALT = {Key.alt, Key.alt_l, Key.alt_r}
_MOD_CMD = {Key.cmd, Key.cmd_l, Key.cmd_r}
_MOD_ALL = _MOD_CTRL | _MOD_ALT | _MOD_CMD | {Key.alt_gr}


class TypingBuffer:
    def __init__(self) -> None:
        self._chars: list[str] = []
        self._lock = threading.Lock()
        self._listener: keyboard.Listener | None = None
        self._controller = keyboard.Controller()
        self._injecting = False
        self._last_window_id: int | None = None
        self._buffer_window_id: int | None = None
        self._display = display.Display() if _HAS_XLIB else None
        self._mods: set = set()
        self._on_previous_line = False

    def start(self) -> None:
        if self._listener is not None:
            return
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def clear(self) -> None:
        with self._lock:
            self._chars.clear()
            self._buffer_window_id = None
            self._on_previous_line = False

    def get_text(self) -> str:
        with self._lock:
            return "".join(self._chars).strip()

    def _get_active_window(self) -> int | None:
        if not self._display:
            return None
        try:
            root = self._display.screen().root
            net_active = self._display.intern_atom("_NET_ACTIVE_WINDOW")
            prop = root.get_full_property(net_active, X.AnyPropertyType)
            if prop and prop.value:
                return int(prop.value[0])
        except Exception:
            pass
        return None

    def _is_shortcut_context(self) -> bool:
        if self._mods & _MOD_CTRL:
            return True
        if self._mods & _MOD_CMD:
            return True
        if (self._mods & _MOD_ALT) and Key.alt_gr not in self._mods:
            return True
        return False

    def _prepare_for_typing(self) -> None:
        wid = self._get_active_window()
        with self._lock:
            if self._on_previous_line:
                self._chars.clear()
                self._on_previous_line = False
            if wid is not None:
                if self._buffer_window_id is not None and wid != self._buffer_window_id:
                    self._chars.clear()
                    self._on_previous_line = False
                self._buffer_window_id = wid
                self._last_window_id = wid

    def _focus_last_window(self) -> None:
        if not self._display or not self._last_window_id:
            return
        try:
            root = self._display.screen().root
            win = self._display.create_resource_object("window", self._last_window_id)
            net_active = self._display.intern_atom("_NET_ACTIVE_WINDOW")
            ev = xevent.ClientMessage(
                window=win,
                client_type=net_active,
                data=(32, [2, X.CurrentTime, 0, 0, 0]),
            )
            mask = X.SubstructureRedirectMask | X.SubstructureNotifyMask
            root.send_event(ev, event_mask=mask)
            self._display.flush()
            time.sleep(0.15)
        except Exception:
            pass

    def _on_release(self, key) -> None:
        self._mods.discard(key)
        for group in (_MOD_CTRL, _MOD_ALT, _MOD_CMD):
            if key in group:
                self._mods -= group

    def _on_press(self, key) -> None:
        if self._injecting:
            return

        if key in _MOD_ALL:
            self._mods.add(key)
            return

        if self._is_shortcut_context():
            return

        try:
            if key == Key.backspace:
                with self._lock:
                    if self._on_previous_line:
                        self._on_previous_line = False
                        return
                    if self._chars:
                        self._chars.pop()
                wid = self._get_active_window()
                if wid is not None:
                    self._last_window_id = wid
                    self._buffer_window_id = wid
                return

            if key == Key.enter:
                with self._lock:
                    self._on_previous_line = bool(self._chars)
                return

            if key in (Key.esc, Key.tab):
                self.clear()
                return

            if key in (
                Key.up,
                Key.down,
                Key.left,
                Key.right,
                Key.home,
                Key.end,
                Key.page_up,
                Key.page_down,
            ):
                self.clear()
                return

            if key == Key.space:
                self._prepare_for_typing()
                with self._lock:
                    self._chars.append(" ")
                return

            char = getattr(key, "char", None)
            if not char or ord(char) < 32:
                return

            self._prepare_for_typing()
            with self._lock:
                self._chars.append(char)
        except Exception:
            pass

    def _tap(self, key) -> None:
        self._controller.press(key)
        self._controller.release(key)

    def replace_with(self, original: str, corrected: str, root=None) -> bool:
        """
        Remplace la phrase sans la dupliquer :
        sélectionne N caractères vers la gauche, puis Ctrl+V.
        """
        if not corrected or not original:
            return False
        # Sécurité anti-doublon côté modèle
        if corrected.startswith(original) and len(corrected) > len(original):
            rest = corrected[len(original) :].lstrip()
            if rest:
                corrected = rest if original.endswith(rest[:3]) else corrected

        on_prev = False
        with self._lock:
            on_prev = self._on_previous_line

        try:
            if root is not None:
                root.clipboard_clear()
                root.clipboard_append(corrected)
                root.update_idletasks()

            self._focus_last_window()
            time.sleep(0.1)
            self._injecting = True

            if on_prev:
                self._tap(Key.up)
                time.sleep(0.04)
                self._tap(Key.end)
                time.sleep(0.04)

            # Sélectionner exactement la phrase (curseur supposé à la fin)
            with self._controller.pressed(Key.shift):
                for _ in range(len(original)):
                    self._tap(Key.left)
                    time.sleep(0.001)
            time.sleep(0.04)

            # Coller = remplace la sélection (pas d'ajout à la suite)
            with self._controller.pressed(Key.ctrl):
                self._controller.press("v")
                self._controller.release("v")
            time.sleep(0.06)

            if on_prev:
                self._tap(Key.down)
                time.sleep(0.03)

            self.clear()
            return True
        except Exception:
            return False
        finally:
            self._injecting = False
