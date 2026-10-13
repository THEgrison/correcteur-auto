"""Lecture / remplacement d'une sélection (PRIMARY + AT-SPI)."""

from __future__ import annotations

import subprocess
import time

from pynput.keyboard import Controller, Key

try:
    import gi

    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi

    _HAS_ATSPI = True
except Exception:  # noqa: BLE001
    _HAS_ATSPI = False

try:
    from Xlib import X, display
    from Xlib.protocol import event as xevent

    _HAS_XLIB = True
except Exception:  # noqa: BLE001
    _HAS_XLIB = False


def get_primary_selection() -> str:
    for cmd in (
        ["xclip", "-o", "-selection", "primary"],
        ["xsel", "-o"],
    ):
        try:
            out = subprocess.check_output(
                cmd, text=True, stderr=subprocess.DEVNULL, timeout=1
            )
            if out and out.strip():
                return out
        except Exception:
            pass
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, Gtk

        clip = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
        text = clip.wait_for_text()
        if text and text.strip():
            return text
    except Exception:
        pass
    return ""


def get_active_window_id() -> int | None:
    if not _HAS_XLIB:
        return None
    try:
        d = display.Display()
        root = d.screen().root
        atom = d.intern_atom("_NET_ACTIVE_WINDOW")
        prop = root.get_full_property(atom, X.AnyPropertyType)
        if prop and prop.value:
            return int(prop.value[0])
    except Exception:
        pass
    return None


def focus_window(window_id: int | None) -> None:
    if not _HAS_XLIB or not window_id:
        return
    try:
        d = display.Display()
        root = d.screen().root
        win = d.create_resource_object("window", window_id)
        atom = d.intern_atom("_NET_ACTIVE_WINDOW")
        ev = xevent.ClientMessage(
            window=win,
            client_type=atom,
            data=(32, [2, X.CurrentTime, 0, 0, 0]),
        )
        root.send_event(
            ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask
        )
        d.flush()
        time.sleep(0.12)
    except Exception:
        pass


def _find_focused_text():
    if not _HAS_ATSPI:
        return None
    try:
        Atspi.init()
        desktop = Atspi.get_desktop(0)
    except Exception:
        return None

    def walk(acc, depth=0):
        if acc is None or depth > 40:
            return None
        try:
            st = acc.get_state_set()
            if st.contains(Atspi.StateType.FOCUSED) and (
                acc.is_text() or acc.is_editable_text()
            ):
                return acc
        except Exception:
            pass
        try:
            n = min(acc.get_child_count(), 80 if depth < 3 else 40)
        except Exception:
            return None
        for i in range(n):
            try:
                found = walk(acc.get_child_at_index(i), depth + 1)
            except Exception:
                continue
            if found is not None:
                return found
        return None

    try:
        for i in range(desktop.get_child_count()):
            found = walk(desktop.get_child_at_index(i))
            if found is not None:
                return found
    except Exception:
        pass
    return None


def _atspi_replace_string(original: str, corrected: str) -> bool:
    """Remplace original par corrected dans le champ focus (évite les doublons)."""
    acc = _find_focused_text()
    if acc is None or not original:
        return False
    try:
        full = acc.get_text(0, -1) or ""
        caret = int(acc.get_caret_offset())
    except Exception:
        return False

    # Chercher près du caret d'abord, puis dans tout le texte
    idx = -1
    window = full[max(0, caret - len(original) - 20) : caret + 20]
    local = window.rfind(original)
    if local >= 0:
        idx = max(0, caret - len(original) - 20) + local
    if idx < 0:
        idx = full.rfind(original)
    if idx < 0:
        idx = full.find(original)
    if idx < 0:
        return False

    try:
        acc.delete_text(idx, idx + len(original))
        acc.insert_text(idx, corrected, len(corrected))
        try:
            acc.set_caret_offset(idx + len(corrected))
        except Exception:
            pass
        return True
    except Exception:
        return False


def replace_selection(
    original: str, corrected: str, window_id: int | None, root=None
) -> bool:
    """Remplace la sélection / occurrence — sans dupliquer le texte."""
    if not corrected or not original:
        return False

    if root is not None:
        try:
            root.clipboard_clear()
            root.clipboard_append(corrected)
            root.update_idletasks()
        except Exception:
            pass

    focus_window(window_id)
    time.sleep(0.1)

    # 1) AT-SPI : remplacement exact dans le champ (le plus fiable)
    if _atspi_replace_string(original, corrected):
        return True

    # 2) Repli clavier : resélectionner N caractères vers la gauche puis coller
    #    (uniquement si le curseur est juste après la sélection d'origine)
    ctrl = Controller()
    try:
        with ctrl.pressed(Key.shift):
            for _ in range(len(original)):
                ctrl.press(Key.left)
                ctrl.release(Key.left)
                time.sleep(0.002)
        time.sleep(0.04)
        with ctrl.pressed(Key.ctrl):
            ctrl.press("v")
            ctrl.release("v")
        time.sleep(0.05)
        return True
    except Exception:
        return False
