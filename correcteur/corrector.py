"""Correction contextuelle via modèle IA local (Ollama)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

# Élisions FR à ne jamais « décomposer »
_ELISION_FIXES = (
    (r"\bje aime\b", "j'aime"),
    (r"\bJe aime\b", "J'aime"),
    (r"\bje ai\b", "j'ai"),
    (r"\bJe ai\b", "J'ai"),
    (r"\bje avais\b", "j'avais"),
    (r"\bje aurai\b", "j'aurai"),
    (r"\bje aurais\b", "j'aurais"),
    (r"\bje étais\b", "j'étais"),
    (r"\bje irai\b", "j'irai"),
    (r"\bce est\b", "c'est"),
    (r"\bCe est\b", "C'est"),
    (r"\bde le\b", "du"),
    (r"\bde les\b", "des"),
    (r"\bne a\b", "n'a"),
    (r"\bne est\b", "n'est"),
    (r"\bsi il\b", "s'il"),
    (r"\bSi il\b", "S'il"),
    (r"\bque il\b", "qu'il"),
    (r"\bque elle\b", "qu'elle"),
    (r"\bque on\b", "qu'on"),
    (r"\ble on\b", "l'on"),
)


class Corrector:
    def __init__(self) -> None:
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def status(self, cfg: dict) -> str:
        url = cfg.get("ollama_url", "http://127.0.0.1:11434").rstrip("/")
        try:
            with urllib.request.urlopen(url + "/api/tags", timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            wanted = cfg.get("ollama_model", "qwen2.5:1.5b")
            if any(wanted in m or m.startswith(wanted.split(":")[0]) for m in models):
                return f"Ollama prêt ({wanted})"
            if models:
                return f"Ollama tourne, modèle manquant. Lance : ollama pull {wanted}"
            return f"Ollama tourne sans modèle. Lance : ollama pull {wanted}"
        except Exception:
            return "Ollama indisponible — lance : ollama serve && ollama pull qwen2.5:1.5b"

    def correct(self, text: str, cfg: dict) -> str:
        text = text.strip()
        if len(text) < int(cfg.get("min_chars", 2)):
            return text

        self._last_error = None
        lang = self._resolve_language(text, cfg.get("language", "auto"))
        prompt = self._build_prompt(text, cfg, lang)
        model = cfg.get("ollama_model", "qwen2.5:1.5b")
        url = cfg.get("ollama_url", "http://127.0.0.1:11434").rstrip("/") + "/api/generate"

        temperature = 0.15 if cfg.get("allow_reformulation", False) else 0.0

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max(64, min(512, len(text) * 3)),
            },
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            out = (data.get("response") or "").strip()
            out = self._clean_output(out, text, lang)
            return out or text
        except urllib.error.URLError as exc:
            self._last_error = f"Ollama injoignable ({exc})"
            return text
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            return text

    def _resolve_language(self, text: str, mode: str) -> str:
        if mode in ("fr", "en"):
            return mode
        if re.search(r"[àâäéèêëïîôùûüçœæ']", text, re.I):
            return "fr"
        fr_hints = (
            r"\b(je|tu|il|elle|nous|vous|les|des|une|est|pas|pour|avec|"
            r"dans|sur|que|qui|bonjour|merci|très|tres|j'aime|aime|"
            r"manger|patates|orthographe|ça|sa|marche)\b"
        )
        en_hints = (
            r"\b(the|and|have|this|that|with|from|spelling|mistake|"
            r"sentence|is|are|was|were|not|you|your)\b"
        )
        fr_n = len(re.findall(fr_hints, text, re.I))
        en_n = len(re.findall(en_hints, text, re.I))
        if en_n > fr_n:
            return "en"
        if fr_n > 0:
            return "fr"
        return "fr"

    def _build_prompt(self, text: str, cfg: dict, lang: str) -> str:
        reform = bool(cfg.get("allow_reformulation", False))

        if lang == "en":
            lang_rule = (
                "The text is in ENGLISH. Output MUST stay in ENGLISH. "
                "Do NOT translate."
            )
            if reform:
                mode = (
                    "- You MAY lightly rephrase for clarity while keeping the same meaning.\n"
                    "- Fix spelling and grammar."
                )
            else:
                mode = (
                    "- Do NOT rephrase. Do NOT replace words with synonyms.\n"
                    "- Keep the SAME words and word order.\n"
                    "- ONLY fix spelling mistakes in words (typos / accents).\n"
                    "- Do NOT rewrite the sentence."
                )
            style = [mode]
            if not cfg.get("fix_commas", False):
                style.append("- Do NOT add commas.")
            if not cfg.get("fix_periods", False):
                style.append("- Do NOT add a final period if missing.")
            if not cfg.get("fix_capitals", False):
                style.append("- Do NOT change capitalization unless fixing a misspelled word.")
            style_txt = "\n".join(style)
            return (
                "You are a strict spelling corrector.\n"
                "Reply with ONLY the corrected text. No quotes. No explanation.\n"
                f"{lang_rule}\n"
                f"{style_txt}\n\n"
                f"Text:\n{text}\n\n"
                "Corrected:"
            )

        lang_rule = "Le texte est en français. Réponds en français. Ne traduis pas."
        elision = (
            "- IMPORTANT : conserve les élisions françaises.\n"
            "- Écris « j'aime » et NON « je aime ».\n"
            "- Écris « j'ai », « c'est », « n'est », « qu'il », « s'il » correctement.\n"
            "- Ne sépare JAMAIS une élision en deux mots (je + aime)."
        )
        if reform:
            mode = (
                "- Tu PEUX reformuler légèrement pour plus de clarté, en gardant le même sens.\n"
                "- Corrige l'orthographe et la grammaire.\n"
                f"{elision}"
            )
        else:
            mode = (
                "- Ne reformule PAS. Ne remplace PAS les mots par des synonymes.\n"
                "- Garde les MÊMES mots et le même ordre.\n"
                "- Corrige UNIQUEMENT les fautes d'orthographe (lettres / accents).\n"
                "- Ne réécris pas la phrase.\n"
                f"{elision}"
            )
        rules = [mode]
        if cfg.get("fix_commas", False):
            rules.append("- Tu peux ajouter ou corriger les virgules.")
        else:
            rules.append("- N'ajoute PAS de virgules.")
        if cfg.get("fix_periods", False):
            rules.append("- Tu peux ajouter ou corriger les points.")
        else:
            rules.append("- N'ajoute PAS de point final s'il n'y en a pas.")
        if cfg.get("fix_capitals", False):
            rules.append("- Corrige les majuscules.")
        else:
            rules.append("- Ne change PAS les majuscules sauf faute dans un mot.")

        rules_txt = "\n".join(rules)
        return (
            "Tu es un correcteur d'orthographe strict.\n"
            "Réponds UNIQUEMENT avec le texte corrigé, une seule fois, "
            "sans guillemets, sans commentaire, sans répéter le texte.\n"
            f"{lang_rule}\n"
            f"{rules_txt}\n\n"
            f"Texte à corriger :\n{text}\n\n"
            "Texte corrigé :"
        )

    @classmethod
    def _clean_output(cls, out: str, original: str, lang: str = "fr") -> str:
        out = out.strip()
        if out.startswith("```"):
            out = re.sub(r"^```[a-zA-Z]*\n?", "", out)
            out = re.sub(r"\n?```$", "", out).strip()
        if (out.startswith('"') and out.endswith('"')) or (
            out.startswith("«") and out.endswith("»")
        ):
            out = out[1:-1].strip()
        if out.lower().startswith("texte corrigé"):
            out = re.sub(r"^texte corrigé\s*:?\s*", "", out, flags=re.I).strip()
        if out.lower().startswith("corrected"):
            out = re.sub(r"^corrected\s*:?\s*", "", out, flags=re.I).strip()
        if "\n" in out and "\n" not in original:
            first = out.splitlines()[0].strip()
            if first:
                out = first

        # Anti-doublon : « phrasephrase » ou « phrase + phrase »
        out = cls._dedupe(out, original)

        if lang.startswith("fr"):
            for pattern, repl in _ELISION_FIXES:
                out = re.sub(pattern, repl, out)

        if original and len(out) > max(40, len(original) * 3):
            return original
        return out

    @staticmethod
    def _dedupe(out: str, original: str) -> str:
        if not out:
            return out
        # Cas : original collé devant/derrière la correction
        if original and out != original:
            if out.startswith(original) and len(out) > len(original):
                rest = out[len(original) :].lstrip(" \n")
                # « patatesj'aime… » ou « patates patates »
                if rest.lower().startswith(original[: max(3, len(original) // 3)].lower()) or (
                    len(rest) >= len(original) // 2
                ):
                    # Si le reste ressemble à une 2e copie / correction seule
                    if original.lower() in rest.lower() or len(rest) <= len(original) + 10:
                        # Préférer la partie corrigée seule si elle contient l'essentiel
                        if rest and not rest.lower().startswith(original.lower()):
                            return rest
                        return original if not rest else rest
            if out.endswith(original) and len(out) > len(original):
                head = out[: -len(original)].rstrip(" \n")
                if head:
                    return head
            # Deux fois le même bloc
            mid = len(out) // 2
            if mid > 4 and out[:mid].strip() == out[mid:].strip():
                return out[:mid].strip()
            glued = original + original
            if out.replace(" ", "") == glued.replace(" ", ""):
                return original
        return out
