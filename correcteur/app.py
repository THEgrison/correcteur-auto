"""Correcteur Auto — tout passe par l'icône (pas de popup flottant)."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path

import pystray
from pystray import MenuItem as Item
from pynput import keyboard

from correcteur import config
from correcteur.corrector import Corrector
from correcteur.icon import make_icon
from correcteur.selection import (
    get_active_window_id,
    get_primary_selection,
    replace_selection,
)
from correcteur.settings_ui import SettingsWindow
from correcteur.toast import show_toast
from correcteur.typing_buffer import TypingBuffer


class Application:
    def __init__(self) -> None:
        self.cfg = config.load()
        self.corrector = Corrector()
        self.buffer = TypingBuffer()
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.title("Correcteur Auto")
        self._busy = False
        self._hotkeys: keyboard.GlobalHotKeys | None = None
        # Dernière sélection capturée juste avant ouverture du menu
        self._last_selection = ""
        self._last_selection_window: int | None = None

        run_sh = str(Path(__file__).resolve().parent.parent / "run.sh")
        config.sync_autostart(bool(self.cfg.get("autostart", False)), run_sh)

        self.settings = SettingsWindow(
            get_config=lambda: self.cfg,
            save_config=self._save_cfg,
            on_changed=self._on_settings_changed,
            status_fn=lambda: self.corrector.status(self.cfg),
            buffer_fn=self.buffer.get_text,
            correct_fn=self.corrector.correct,
        )
        self.settings._clear_buffer_fn = self.buffer.clear  # noqa: SLF001

        self.icon = pystray.Icon(
            "correcteur-auto",
            make_icon(bool(self.cfg.get("enabled", True))),
            self._tooltip(),
            menu=self._build_menu(),
        )

    def run(self) -> None:
        self.buffer.start()
        self._start_hotkeys()
        # Capturer la sélection quand le menu de l'icône s'ouvre
        self._poll_selection_for_menu()
        threading.Thread(target=self.icon.run, daemon=True).start()
        self._root.mainloop()

    def _poll_selection_for_menu(self) -> None:
        """Mémorise régulièrement la sélection PRIMARY (pour le menu icône)."""

        def tick() -> None:
            if self.cfg.get("enabled", True) and not self._busy:
                sel = get_primary_selection()
                if sel and sel.strip():
                    self._last_selection = sel
                    wid = get_active_window_id()
                    if wid is not None:
                        self._last_selection_window = wid
            self._root.after(400, tick)

        self._root.after(400, tick)

    def _tooltip(self) -> str:
        preview = self.buffer.get_text()
        if preview:
            short = preview if len(preview) <= 40 else preview[:37] + "…"
            return f"Correcteur Auto — « {short} »"
        return "Correcteur Auto — clic droit sur l'icône pour corriger"

    def _build_menu(self) -> pystray.Menu:
        enabled = bool(self.cfg.get("enabled", True))
        can = enabled and not self._busy
        return pystray.Menu(
            Item(
                "Corriger la phrase tapée",
                self._correct_buffer,
                default=True,
                enabled=can,
            ),
            Item(
                "Corriger la sélection",
                self._correct_selection_from_menu,
                enabled=can,
            ),
            pystray.Menu.SEPARATOR,
            Item("Vider la mémoire", self._clear_buffer),
            Item("Désactiver" if enabled else "Activer", self._toggle_enabled),
            Item("Paramètres…", self._open_settings),
            pystray.Menu.SEPARATOR,
            Item("Quitter", self._quit),
        )

    def _start_hotkeys(self) -> None:
        self._stop_hotkeys()
        if not self.cfg.get("hotkey_enabled", True):
            return

        def on_phrase() -> None:
            self._root.after(0, self._correct_buffer)

        def on_selection() -> None:
            self._root.after(0, self._correct_selection_from_menu)

        try:
            self._hotkeys = keyboard.GlobalHotKeys(
                {
                    "<ctrl>+<shift>+<space>": on_phrase,
                    "<ctrl>+<shift>+c": on_selection,
                }
            )
            self._hotkeys.start()
        except Exception:
            self._hotkeys = None

    def _stop_hotkeys(self) -> None:
        if self._hotkeys is not None:
            try:
                self._hotkeys.stop()
            except Exception:
                pass
            self._hotkeys = None

    def _correct_buffer(self, _icon=None, _item=None) -> None:
        text = self.buffer.get_text()
        self._run_correction(
            text,
            mode="buffer",
            empty_msg="Rien en mémoire — tape une phrase d'abord",
        )

    def _correct_selection_from_menu(self, _icon=None, _item=None) -> None:
        # Préférer la sélection live, sinon celle mémorisée juste avant
        text = get_primary_selection() or self._last_selection
        wid = get_active_window_id() or self._last_selection_window
        if not (text or "").strip():
            self._notify(
                "Sélectionne du texte, puis clic droit sur l'icône → Corriger la sélection",
                "err",
            )
            self._flash_icon(ok=False)
            return
        self._run_correction(
            text,
            mode="selection",
            window_id=wid,
            empty_msg="Sélection vide",
        )

    def _run_correction(
        self,
        text: str,
        mode: str,
        empty_msg: str,
        window_id: int | None = None,
    ) -> None:
        if self._busy or not self.cfg.get("enabled", True):
            return

        text = (text or "").strip()
        if len(text) < int(self.cfg.get("min_chars", 2)):
            self._notify(empty_msg, "err")
            self._flash_icon(ok=False)
            return

        self._busy = True
        self._notify("Correction…", "busy")
        self._flash_icon(busy=True)

        def work() -> None:
            err = None
            try:
                corrected = self.corrector.correct(text, self.cfg)
                if self.corrector.last_error:
                    err = self.corrector.last_error
            except Exception as exc:  # noqa: BLE001
                corrected = text
                err = str(exc)

            def done() -> None:
                ok = False
                if corrected and corrected != text and not err:
                    if mode == "selection":
                        ok = replace_selection(
                            text, corrected, window_id, self._root
                        )
                    else:
                        ok = self.buffer.replace_with(text, corrected, self._root)
                self._busy = False
                if err:
                    self._notify(err, "err")
                    self._flash_icon(ok=False)
                elif corrected == text:
                    self._notify("Rien à changer", "ok")
                    self._flash_icon(ok=True)
                elif ok:
                    short = corrected if len(corrected) <= 60 else corrected[:57] + "…"
                    self._notify(f"Corrigé : {short}", "ok")
                    self._flash_icon(ok=True)
                    if mode == "selection":
                        self._last_selection = ""
                else:
                    try:
                        self._root.clipboard_clear()
                        self._root.clipboard_append(corrected)
                    except Exception:
                        pass
                    self._notify("Corrigé → resélectionne et Ctrl+V", "err")
                    self._flash_icon(ok=False)
                self._refresh_tray()

            self._root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _notify(self, msg: str, kind: str = "info") -> None:
        self.icon.title = f"Correcteur Auto — {msg}"
        if self.cfg.get("show_toast", True):
            try:
                show_toast(self._root, msg, kind=kind)
            except Exception:
                pass

    def _flash_icon(self, ok: bool = True, busy: bool = False) -> None:
        color = "busy" if busy else ("ok" if ok else "err")
        try:
            self.icon.icon = make_icon(
                enabled=bool(self.cfg.get("enabled", True)),
                state=color,
            )
            if not busy:
                self._root.after(
                    900,
                    lambda: setattr(
                        self.icon,
                        "icon",
                        make_icon(bool(self.cfg.get("enabled", True))),
                    ),
                )
        except Exception:
            pass

    def _clear_buffer(self, _icon=None, _item=None) -> None:
        self.buffer.clear()
        self._last_selection = ""
        self._notify("Mémoire vidée", "info")
        self._refresh_tray()

    def _toggle_enabled(self, _icon=None, _item=None) -> None:
        self.cfg["enabled"] = not bool(self.cfg.get("enabled", True))
        config.save(self.cfg)
        if not self.cfg["enabled"]:
            self.buffer.clear()
        self._refresh_tray()
        self._notify(
            "Correcteur activé" if self.cfg["enabled"] else "Correcteur désactivé",
            "ok" if self.cfg["enabled"] else "info",
        )

    def _open_settings(self, _icon=None, _item=None) -> None:
        self._root.after(0, self.settings.open)

    def _save_cfg(self, cfg: dict) -> None:
        self.cfg = cfg
        run_sh = str(Path(__file__).resolve().parent.parent / "run.sh")
        config.save(cfg)
        config.sync_autostart(bool(cfg.get("autostart", False)), run_sh)

    def _on_settings_changed(self) -> None:
        self._start_hotkeys()
        self._refresh_tray()

    def _refresh_tray(self) -> None:
        self.icon.icon = make_icon(bool(self.cfg.get("enabled", True)))
        self.icon.menu = self._build_menu()
        self.icon.title = self._tooltip()
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def _quit(self, _icon=None, _item=None) -> None:
        self._stop_hotkeys()
        self.buffer.stop()
        try:
            self.icon.stop()
        except Exception:
            pass
        self._root.after(0, self._root.destroy)


def main() -> None:
    Application().run()
