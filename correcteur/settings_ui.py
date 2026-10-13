"""Fenêtre de paramètres — style cohérent, fermable, sans gel UI."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

BLUE = "#1565C0"
BLUE_DARK = "#0D47A1"
BLUE_SOFT = "#E3F2FD"
TEXT = "#1A1A1A"
MUTED = "#5F6368"
CARD = "#FFFFFF"
BORDER = "#BBDEFB"
OK = "#2E7D32"
ERR = "#C62828"


class SettingsWindow:
    def __init__(
        self,
        get_config: Callable[[], dict],
        save_config: Callable[[dict], None],
        on_changed: Callable[[], None] | None = None,
        status_fn: Callable[[], str] | None = None,
        buffer_fn: Callable[[], str] | None = None,
        correct_fn: Callable[[str, dict], str] | None = None,
    ) -> None:
        self._get_config = get_config
        self._save_config = save_config
        self._on_changed = on_changed
        self._status_fn = status_fn
        self._buffer_fn = buffer_fn
        self._correct_fn = correct_fn
        self._root: tk.Toplevel | None = None
        self._vars: dict[str, tk.Variable] = {}
        self._preview: tk.Text | None = None
        self._test_out: tk.Label | None = None
        self._status_lbl: tk.Label | None = None
        self._testing = False
        self._canvas: tk.Canvas | None = None

    def open(self) -> None:
        if self._root is not None:
            try:
                if self._root.winfo_exists():
                    self._root.lift()
                    self._root.focus_force()
                    return
            except tk.TclError:
                self._root = None

        cfg = self._get_config()
        master = tk._default_root  # noqa: SLF001
        root = tk.Toplevel(master) if master else tk.Tk()
        self._root = root
        root.title("Correcteur Auto — Paramètres")
        root.configure(bg=BLUE_SOFT)
        root.resizable(True, True)
        # Au premier plan un instant, puis normal (évite de bloquer le bureau)
        root.attributes("-topmost", True)
        root.after(300, lambda: root.attributes("-topmost", False))

        root.update_idletasks()
        screen_h = root.winfo_screenheight()
        win_h = min(640, max(420, screen_h - 120))
        root.geometry(f"460x{win_h}")
        root.minsize(400, 360)

        header = tk.Frame(root, bg=BLUE, padx=20, pady=16)
        header.pack(fill="x")
        tk.Label(
            header,
            text="Aa  Correcteur Auto",
            bg=BLUE,
            fg="white",
            font=("DejaVu Sans", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Tout se passe via l'icône · Échap ou Annuler pour fermer",
            bg=BLUE,
            fg="#BBDEFB",
            font=("DejaVu Sans", 9),
        ).pack(anchor="w", pady=(4, 0))

        footer = tk.Frame(root, bg=BLUE_SOFT, padx=16, pady=12)
        footer.pack(side="bottom", fill="x")

        scroll_wrap = tk.Frame(root, bg=BLUE_SOFT)
        scroll_wrap.pack(fill="both", expand=True)

        canvas = tk.Canvas(scroll_wrap, bg=BLUE_SOFT, highlightthickness=0, borderwidth=0)
        self._canvas = canvas
        scrollbar = ttk.Scrollbar(scroll_wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg=BLUE_SOFT, padx=16, pady=14)
        body_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_body_configure(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event) -> None:
            canvas.itemconfigure(body_id, width=event.width)

        body.bind("<Configure>", _on_body_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Molette UNIQUEMENT sur le canvas (pas bind_all → ça bloquait l'UI)
        def _on_mousewheel(event) -> str:
            if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
                canvas.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
                canvas.yview_scroll(3, "units")
            return "break"

        for widget in (canvas, body, scroll_wrap):
            widget.bind("<MouseWheel>", _on_mousewheel)
            widget.bind("<Button-4>", _on_mousewheel)
            widget.bind("<Button-5>", _on_mousewheel)

        status = self._status_fn() if self._status_fn else ""
        self._status_lbl = tk.Label(
            body,
            text=status,
            bg=BLUE_SOFT,
            fg=MUTED,
            font=("DejaVu Sans", 9),
            wraplength=400,
            justify="left",
            anchor="w",
        )
        self._status_lbl.pack(fill="x", pady=(0, 10))

        self._vars = {}

        # —— Phrase / test ——
        card_preview = self._card(body, "Tester une phrase")
        tk.Label(
            card_preview,
            text="Écris ici une phrase à tester (ou charge la mémoire) :",
            bg=CARD,
            fg=MUTED,
            font=("DejaVu Sans", 8),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        self._preview = tk.Text(
            card_preview,
            height=3,
            width=48,
            wrap="word",
            font=("DejaVu Sans", 10),
            bg="#FAFAFA",
            fg=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=8,
            pady=6,
            # Éditable : plus de gel / state disabled
        )
        self._preview.pack(fill="x", pady=(0, 6))
        # Molette dans le Text = scroll du canvas si en haut/bas
        self._preview.bind("<Button-4>", _on_mousewheel)
        self._preview.bind("<Button-5>", _on_mousewheel)

        row_p = tk.Frame(card_preview, bg=CARD)
        row_p.pack(fill="x")
        self._btn(row_p, "Charger la mémoire", self._load_memory, side="left")
        self._btn(row_p, "Effacer", self._clear_preview_text, side="left", pad=(8, 0))
        self._btn(row_p, "Tester", self._run_test, side="right")

        self._test_out = tk.Label(
            card_preview,
            text="Astuce : tu peux taper une phrase ici même si la mémoire est vide.",
            bg=CARD,
            fg=MUTED,
            font=("DejaVu Sans", 9),
            wraplength=400,
            justify="left",
            anchor="w",
        )
        self._test_out.pack(fill="x", pady=(8, 0))

        # —— Général ——
        card_g = self._card(body, "Général")
        self._vars["enabled"] = tk.BooleanVar(value=bool(cfg.get("enabled", True)))
        self._check(card_g, "Correction activée", self._vars["enabled"])

        row = tk.Frame(card_g, bg=CARD)
        row.pack(fill="x", pady=(8, 0))
        tk.Label(row, text="Langue", bg=CARD, fg=TEXT, font=("DejaVu Sans", 9)).pack(
            side="left"
        )
        self._vars["language"] = tk.StringVar(value=str(cfg.get("language", "auto")))
        ttk.Combobox(
            row,
            textvariable=self._vars["language"],
            values=("auto", "fr", "en"),
            state="readonly",
            width=12,
        ).pack(side="right")

        # —— Correction ——
        card_c = self._card(body, "Correction")
        self._vars["allow_reformulation"] = tk.BooleanVar(
            value=bool(cfg.get("allow_reformulation", False))
        )
        self._check(
            card_c,
            "Autoriser la reformulation (réécrire / changer les mots)",
            self._vars["allow_reformulation"],
        )
        tk.Label(
            card_c,
            text="Décoché : garde tes mots, corrige seulement les fautes.",
            bg=CARD,
            fg=MUTED,
            font=("DejaVu Sans", 8),
            wraplength=400,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        self._vars["fix_spelling"] = tk.BooleanVar(
            value=bool(cfg.get("fix_spelling", True))
        )
        self._check(card_c, "Corriger l'orthographe", self._vars["fix_spelling"])
        self._vars["fix_commas"] = tk.BooleanVar(
            value=bool(cfg.get("fix_commas", False))
        )
        self._check(card_c, "Autoriser les virgules", self._vars["fix_commas"])
        self._vars["fix_periods"] = tk.BooleanVar(
            value=bool(cfg.get("fix_periods", False))
        )
        self._check(card_c, "Autoriser les points", self._vars["fix_periods"])
        self._vars["fix_capitals"] = tk.BooleanVar(
            value=bool(cfg.get("fix_capitals", False))
        )
        self._check(card_c, "Autoriser les majuscules", self._vars["fix_capitals"])

        # —— Confort ——
        card_u = self._card(body, "Confort")
        self._vars["hotkey_enabled"] = tk.BooleanVar(
            value=bool(cfg.get("hotkey_enabled", True))
        )
        self._check(
            card_u,
            "Raccourcis : Ctrl+Shift+Espace (phrase) / Ctrl+Shift+C (sélection)",
            self._vars["hotkey_enabled"],
        )
        self._vars["show_toast"] = tk.BooleanVar(
            value=bool(cfg.get("show_toast", True))
        )
        self._check(card_u, "Notification après correction", self._vars["show_toast"])
        self._vars["autostart"] = tk.BooleanVar(
            value=bool(cfg.get("autostart", False))
        )
        self._check(card_u, "Lancer au démarrage de la session", self._vars["autostart"])

        # —— IA ——
        card_ai = self._card(body, "IA locale (Ollama)")
        row_m = tk.Frame(card_ai, bg=CARD)
        row_m.pack(fill="x")
        tk.Label(row_m, text="Modèle", bg=CARD, fg=TEXT, font=("DejaVu Sans", 9)).pack(
            side="left"
        )
        self._vars["ollama_model"] = tk.StringVar(
            value=str(cfg.get("ollama_model", "qwen2.5:1.5b"))
        )
        ttk.Combobox(
            row_m,
            textvariable=self._vars["ollama_model"],
            values=(
                "qwen2.5:1.5b",
                "qwen2.5:3b",
                "llama3.2:1b",
                "llama3.2:3b",
                "gemma2:2b",
            ),
            width=16,
        ).pack(side="right")
        self._vars["ollama_url"] = tk.StringVar(
            value=str(cfg.get("ollama_url", "http://127.0.0.1:11434"))
        )

        def _close(_event=None) -> None:
            self._testing = False
            try:
                root.grab_release()
            except tk.TclError:
                pass
            try:
                root.destroy()
            except tk.TclError:
                pass
            self._root = None
            self._preview = None
            self._test_out = None
            self._canvas = None

        root.protocol("WM_DELETE_WINDOW", _close)
        root.bind("<Escape>", _close)
        self._btn(footer, "Fermer", _close, side="right", secondary=True)
        self._btn(
            footer, "Enregistrer", self._save, side="right", primary=True, pad=(0, 8)
        )

        # Préremplir avec la mémoire si dispo (sans bloquer)
        mem = (self._buffer_fn() or "").strip() if self._buffer_fn else ""
        if mem:
            self._preview.insert("1.0", mem)
        root.after(80, _on_body_configure)

    def _card(self, parent: tk.Frame, title: str) -> tk.Frame:
        wrap = tk.Frame(
            parent,
            bg=CARD,
            padx=14,
            pady=12,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        wrap.pack(fill="x", pady=(0, 10))
        tk.Label(
            wrap,
            text=title,
            bg=CARD,
            fg=BLUE_DARK,
            font=("DejaVu Sans", 10, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 8))
        return wrap

    def _check(self, parent: tk.Frame, label: str, var: tk.BooleanVar) -> None:
        tk.Checkbutton(
            parent,
            text=label,
            variable=var,
            bg=CARD,
            fg=TEXT,
            activebackground=CARD,
            activeforeground=TEXT,
            selectcolor=CARD,
            font=("DejaVu Sans", 9),
            anchor="w",
            highlightthickness=0,
        ).pack(fill="x", pady=2)

    def _btn(
        self,
        parent,
        text: str,
        command,
        side: str = "left",
        primary: bool = False,
        secondary: bool = False,
        pad=(0, 0),
    ) -> None:
        if primary:
            bg, fg = BLUE, "white"
        elif secondary:
            bg, fg = "#ECEFF1", TEXT
        else:
            bg, fg = BLUE_SOFT, BLUE_DARK
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=BLUE_DARK if primary else "#CFD8DC",
            activeforeground=fg,
            relief="flat",
            font=("DejaVu Sans", 9, "bold" if primary else "normal"),
            padx=12,
            pady=6,
            cursor="hand2",
        )
        btn.pack(side=side, padx=pad)

    def _preview_text(self) -> str:
        if self._preview is None:
            return ""
        return self._preview.get("1.0", "end").strip()

    def _load_memory(self) -> None:
        if self._preview is None:
            return
        mem = (self._buffer_fn() or "").strip() if self._buffer_fn else ""
        self._preview.delete("1.0", "end")
        if mem:
            self._preview.insert("1.0", mem)
            if self._test_out:
                self._test_out.configure(text="Mémoire chargée.", fg=MUTED)
        else:
            if self._test_out:
                self._test_out.configure(
                    text="Mémoire vide — tape une phrase dans le cadre ci-dessus.",
                    fg=ERR,
                )

    def _clear_preview_text(self) -> None:
        if self._preview is not None:
            self._preview.delete("1.0", "end")
        clear = getattr(self, "_clear_buffer_fn", None)
        if clear:
            clear()
        if self._test_out:
            self._test_out.configure(text="Effacé.", fg=MUTED)

    def _run_test(self) -> None:
        if self._testing:
            return
        if not self._correct_fn or not self._test_out:
            return

        text = self._preview_text()
        if not text:
            # Essayer la mémoire une fois
            mem = (self._buffer_fn() or "").strip() if self._buffer_fn else ""
            text = mem
        if not text:
            self._test_out.configure(
                text="Rien à tester — écris une phrase dans le cadre, puis Tester.",
                fg=ERR,
            )
            return

        self._testing = True
        self._test_out.configure(text="Test en cours… (tu peux fermer la fenêtre)", fg=MUTED)
        cfg = self._collect_cfg()

        def work() -> None:
            try:
                out = self._correct_fn(text, cfg)
            except Exception as exc:  # noqa: BLE001
                out = f"Erreur : {exc}"

            def done() -> None:
                self._testing = False
                if self._test_out is None or self._root is None:
                    return
                try:
                    if not self._root.winfo_exists():
                        return
                except tk.TclError:
                    return
                if out == text:
                    self._test_out.configure(text="Résultat : rien à changer", fg=MUTED)
                else:
                    self._test_out.configure(text=f"Résultat : {out}", fg=OK)

            # Toujours revenir sur le thread UI sans bloquer
            try:
                if self._root is not None and self._root.winfo_exists():
                    self._root.after(0, done)
            except tk.TclError:
                self._testing = False

        threading.Thread(target=work, daemon=True).start()

    def _collect_cfg(self) -> dict:
        cfg = dict(self._get_config())
        for key, var in self._vars.items():
            cfg[key] = var.get()
        cfg.setdefault("min_chars", self._get_config().get("min_chars", 2))
        return cfg

    def _save(self) -> None:
        cfg = self._collect_cfg()
        self._save_config(cfg)
        if self._on_changed:
            self._on_changed()
        if self._root is not None:
            try:
                self._root.destroy()
            except tk.TclError:
                pass
            self._root = None
            self._preview = None
            self._test_out = None
