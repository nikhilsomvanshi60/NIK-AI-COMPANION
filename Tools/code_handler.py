import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
import asyncio
import requests
import json
import threading
import time
import os
import re
from datetime import datetime
from livekit.agents import function_tool


# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

GROQ_API_KEY  = ""
GROQ_URL      = "https://api.groq.com/openai/v1/chat/completions"
MAX_CODE_LINES = 500
MAX_RETRIES    = 3

# Groq models ordered by capability
GROQ_MODELS = {
    "llama-3.3-70b-versatile":  "Llama 3.3 70B (Best)",
    "llama-3.1-70b-versatile":  "Llama 3.1 70B (Strong)",
    "llama-3.1-8b-instant":     "Llama 3.1 8B (Fast)",
    "mixtral-8x7b-32768":       "Mixtral 8x7B (Large ctx)",
    "gemma2-9b-it":             "Gemma2 9B (Google)",
}

# Fix modes with custom prompts
FIX_MODES = {
    "fix_only":       "Fix errors only — minimal changes",
    "fix_optimize":   "Fix + Optimize performance",
    "fix_refactor":   "Fix + Refactor & clean up code",
    "fix_secure":     "Fix + Add security hardening",
    "fix_document":   "Fix + Add full docstrings & comments",
    "explain_fix":    "Fix + Explain every change in detail",
}

LANGUAGE_EXTENSIONS = {
    "python": "py", "javascript": "js", "typescript": "ts",
    "java": "java", "cpp": "cpp", "c": "c", "csharp": "cs",
    "php": "php", "ruby": "rb", "go": "go", "rust": "rs",
    "swift": "swift", "kotlin": "kt", "html": "html",
    "css": "css", "sql": "sql", "bash": "sh", "r": "r",
    "scala": "scala", "dart": "dart",
}

DARK_BG      = "#0d1117"
PANEL_BG     = "#161b22"
BORDER_COLOR = "#30363d"
ACCENT       = "#58a6ff"
GREEN        = "#3fb950"
RED          = "#f85149"
YELLOW       = "#d29922"
PURPLE       = "#bc8cff"
MUTED        = "#8b949e"
TEXT_PRIMARY = "#e6edf3"
TEXT_CODE    = "#79c0ff"


# ─────────────────────────────────────────────────────────────────────────────
#  SESSION HISTORY  (in-memory, survives multiple calls per session)
# ─────────────────────────────────────────────────────────────────────────────

_session_history: list[dict] = []   # [{timestamp, language, model, mode, code, error, fixed_code, tokens}]


# ─────────────────────────────────────────────────────────────────────────────
#  UTILITY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _darken(hex_color: str, amount: int = 25) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(
        max(0, r - amount), max(0, g - amount), max(0, b - amount)
    )


def _simple_diff(original: str, fixed: str) -> list[tuple[str, str]]:
    """
    Returns list of (line, tag) where tag is 'same' | 'added' | 'removed'.
    Uses a basic LCS-based line diff.
    """
    orig_lines  = original.splitlines()
    fixed_lines = fixed.splitlines()
    result = []

    # Build LCS table
    m, n = len(orig_lines), len(fixed_lines)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            if orig_lines[i] == fixed_lines[j]:
                dp[i][j] = dp[i + 1][j + 1] + 1
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])

    i, j = 0, 0
    while i < m or j < n:
        if i < m and j < n and orig_lines[i] == fixed_lines[j]:
            result.append((orig_lines[i], "same"))
            i += 1; j += 1
        elif j < n and (i >= m or dp[i][j + 1] >= dp[i + 1][j]):
            result.append((fixed_lines[j], "added"))
            j += 1
        else:
            result.append((orig_lines[i], "removed"))
            i += 1
    return result


def _estimate_tokens(text: str) -> int:
    """~4 chars per token rough estimate."""
    return max(1, len(text) // 4)


def _build_prompt(language: str, code: str, error: str, mode: str) -> str:
    base = f"""You are an expert {language} developer. A user has a bug in their code.

ORIGINAL {language.upper()} CODE:
```{language}
{code}
```

ERROR MESSAGE:
{error}
"""
    instructions = {
        "fix_only": f"""
Fix ONLY the errors. Make minimal changes.
Return ONLY the corrected {language} code.
Add brief inline comments prefixed with "# FIX:" where you changed something.
No prose, no markdown fences, just raw code.
""",
        "fix_optimize": f"""
1. Fix all errors.
2. Optimize for performance (better algorithms, avoid unnecessary loops, cache results).
3. Add "# OPTIMIZE:" comments where you optimized.
Return ONLY the corrected, optimized {language} code with inline comments.
""",
        "fix_refactor": f"""
1. Fix all errors.
2. Refactor: rename unclear variables, extract repeated code into functions, improve structure.
3. Follow {language} best practices and style guide (PEP8, Google Style, etc.).
4. Add "# REFACTOR:" comments explaining structural changes.
Return ONLY the cleaned-up {language} code.
""",
        "fix_secure": f"""
1. Fix all errors.
2. Identify and fix security vulnerabilities (injection, hardcoded secrets, input validation, etc.).
3. Add "# SECURITY:" comments for each security improvement.
Return ONLY the hardened {language} code.
""",
        "fix_document": f"""
1. Fix all errors.
2. Add comprehensive docstrings/JSDoc to every function and class.
3. Add inline comments explaining complex logic.
Return ONLY the fully documented {language} code.
""",
        "explain_fix": f"""
1. Fix all errors.
2. After the code, add a CHANGES section as comments:
   # ── CHANGES ──────────────────────────────
   # 1. [Line X] What was wrong and why you changed it
   # 2. [Line Y] ...
3. Be detailed — explain root cause for each fix.
Return the corrected {language} code followed by the CHANGES comment block.
""",
    }
    return base + instructions.get(mode, instructions["fix_only"])


# ─────────────────────────────────────────────────────────────────────────────
#  GROQ AI CALLER  (sync, runs in thread)
# ─────────────────────────────────────────────────────────────────────────────

def _call_groq_sync(
    language: str,
    code: str,
    error: str,
    mode: str,
    model: str,
    retries: int = MAX_RETRIES,
) -> dict:
    """
    Returns {
        "fixed_code": str,
        "model": str,
        "tokens_in": int,
        "tokens_out": int,
        "latency_ms": int,
        "error": str | None
    }
    """
    prompt = _build_prompt(language, code, error, mode)
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.25,
        "max_tokens": 4096,
        "top_p": 0.9,
    }

    last_error = None
    for attempt in range(retries):
        try:
            t0 = time.time()
            resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
            latency_ms = int((time.time() - t0) * 1000)

            if resp.status_code == 429:
                wait = 2 ** attempt
                time.sleep(wait)
                last_error = f"Rate limited (attempt {attempt + 1})"
                continue

            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                continue

            data = resp.json()
            raw   = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})

            # Strip markdown fences if present
            raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw, flags=re.MULTILINE)
            raw = re.sub(r"\n?```$", "", raw, flags=re.MULTILINE)

            return {
                "fixed_code":  raw.strip(),
                "model":       model,
                "tokens_in":   usage.get("prompt_tokens",     _estimate_tokens(prompt)),
                "tokens_out":  usage.get("completion_tokens", _estimate_tokens(raw)),
                "latency_ms":  latency_ms,
                "error":       None,
            }

        except requests.exceptions.Timeout:
            last_error = f"Timeout on attempt {attempt + 1}"
        except Exception as exc:
            last_error = str(exc)

    return {
        "fixed_code":  "",
        "model":       model,
        "tokens_in":   0,
        "tokens_out":  0,
        "latency_ms":  0,
        "error":       last_error or "Unknown error",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  THEMED WIDGET FACTORY
# ─────────────────────────────────────────────────────────────────────────────

class Theme:
    @staticmethod
    def label(parent, text, size=11, bold=False, color=TEXT_PRIMARY, **kw):
        font_weight = "bold" if bold else "normal"
        return tk.Label(parent, text=text,
                        font=("JetBrains Mono", size, font_weight) if bold
                        else ("Segoe UI", size),
                        fg=color, bg=kw.pop("bg", parent["bg"]), **kw)

    @staticmethod
    def button(parent, text, command, bg=ACCENT, fg=DARK_BG, size=10, **kw):
        btn = tk.Button(parent, text=text, command=command,
                        bg=bg, fg=fg,
                        font=("Segoe UI", size, "bold"),
                        relief="flat", bd=0, cursor="hand2",
                        activebackground=_darken(bg),
                        activeforeground=fg,
                        padx=kw.pop("padx", 14),
                        pady=kw.pop("pady", 8),
                        **kw)
        hover_bg = _darken(bg)
        btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    @staticmethod
    def code_area(parent, height=18, width=60, fg=TEXT_CODE):
        frame = tk.Frame(parent, bg=BORDER_COLOR, padx=1, pady=1)
        txt = scrolledtext.ScrolledText(
            frame, height=height, width=width,
            font=("JetBrains Mono", 10),
            bg="#010409", fg=fg,
            insertbackground=ACCENT,
            selectbackground=ACCENT,
            selectforeground=DARK_BG,
            relief="flat", padx=12, pady=10,
            wrap=tk.NONE,
            undo=True,
        )
        txt.pack(fill="both", expand=True)
        return frame, txt

    @staticmethod
    def dropdown(parent, variable, options, width=22):
        om = tk.OptionMenu(parent, variable, *options)
        om.config(width=width, font=("Segoe UI", 10),
                  bg=PANEL_BG, fg=TEXT_PRIMARY,
                  activebackground=ACCENT, activeforeground=DARK_BG,
                  relief="flat", highlightthickness=1,
                  highlightbackground=BORDER_COLOR)
        om["menu"].config(bg=PANEL_BG, fg=TEXT_PRIMARY,
                          activebackground=ACCENT, activeforeground=DARK_BG,
                          relief="flat")
        return om


# ─────────────────────────────────────────────────────────────────────────────
#  INPUT WINDOW
# ─────────────────────────────────────────────────────────────────────────────

class InputWindow:
    def __init__(self):
        self.result = None

    def run(self) -> tuple[str, str, str, str, str] | tuple[None, ...]:
        root = tk.Tk()
        root.title("Nova AI — Code Fixer Pro")
        root.geometry("1080x760")
        root.configure(bg=DARK_BG)
        root.resizable(True, True)
        root.eval("tk::PlaceWindow . center")

        # ── Top bar ──────────────────────────────────────────────────────────
        top = tk.Frame(root, bg=PANEL_BG, height=64)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Label(top, text="⚡ Nova AI  Code Fixer Pro",
                 font=("JetBrains Mono", 16, "bold"),
                 fg=ACCENT, bg=PANEL_BG).pack(side="left", padx=24, pady=16)

        # History badge
        hist_count = len(_session_history)
        if hist_count:
            tk.Label(top, text=f"🕓 {hist_count} session fix{'es' if hist_count > 1 else ''}",
                     font=("Segoe UI", 10), fg=YELLOW, bg=PANEL_BG).pack(side="right", padx=20)

        # ── Options row ───────────────────────────────────────────────────────
        opt_row = tk.Frame(root, bg=DARK_BG)
        opt_row.pack(fill="x", padx=20, pady=(12, 0))

        # Language
        tk.Label(opt_row, text="Language", font=("Segoe UI", 10, "bold"),
                 fg=MUTED, bg=DARK_BG).grid(row=0, column=0, sticky="w", padx=(0, 6))
        lang_var = tk.StringVar(value="python")
        Theme.dropdown(opt_row, lang_var, list(LANGUAGE_EXTENSIONS.keys()), width=16).grid(
            row=1, column=0, sticky="w", padx=(0, 20))

        # Model
        tk.Label(opt_row, text="Model", font=("Segoe UI", 10, "bold"),
                 fg=MUTED, bg=DARK_BG).grid(row=0, column=1, sticky="w", padx=(0, 6))
        model_var = tk.StringVar(value=list(GROQ_MODELS.keys())[0])
        Theme.dropdown(opt_row, model_var,
                       [f"{v}  |  {k}" for k, v in GROQ_MODELS.items()],
                       width=30).grid(row=1, column=1, sticky="w", padx=(0, 20))

        # Fix mode
        tk.Label(opt_row, text="Fix Mode", font=("Segoe UI", 10, "bold"),
                 fg=MUTED, bg=DARK_BG).grid(row=0, column=2, sticky="w", padx=(0, 6))
        mode_display_var = tk.StringVar(
            value=list(FIX_MODES.values())[0])
        Theme.dropdown(opt_row, mode_display_var,
                       list(FIX_MODES.values()), width=32).grid(
            row=1, column=2, sticky="w")

        # ── Code + Error panels ───────────────────────────────────────────────
        panels = tk.Frame(root, bg=DARK_BG)
        panels.pack(fill="both", expand=True, padx=20, pady=12)

        # Code panel
        code_panel = tk.Frame(panels, bg=PANEL_BG, relief="flat")
        code_panel.pack(side="left", fill="both", expand=True, padx=(0, 8))
        tk.Label(code_panel, text="📝  Your Code   (max 500 lines)",
                 font=("Segoe UI", 10, "bold"), fg=GREEN, bg=PANEL_BG,
                 anchor="w").pack(fill="x", padx=12, pady=(10, 4))
        _cf, code_txt = Theme.code_area(code_panel, height=20, width=50, fg=TEXT_CODE)
        _cf.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Line counter label
        line_lbl = tk.Label(code_panel, text="0 / 500 lines",
                            font=("Segoe UI", 9), fg=MUTED, bg=PANEL_BG, anchor="e")
        line_lbl.pack(fill="x", padx=12, pady=(0, 8))

        def _update_line_count(event=None):
            lines = int(code_txt.index("end-1c").split(".")[0])
            color = RED if lines > MAX_CODE_LINES else MUTED
            line_lbl.config(text=f"{lines} / {MAX_CODE_LINES} lines", fg=color)

        code_txt.bind("<KeyRelease>", _update_line_count)

        # Error panel
        err_panel = tk.Frame(panels, bg=PANEL_BG)
        err_panel.pack(side="right", fill="both", expand=True)
        tk.Label(err_panel, text="❌  Error / Traceback",
                 font=("Segoe UI", 10, "bold"), fg=RED, bg=PANEL_BG,
                 anchor="w").pack(fill="x", padx=12, pady=(10, 4))
        _ef, err_txt = Theme.code_area(err_panel, height=20, width=50, fg="#ff7b72")
        _ef.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Clear buttons
        clr_row = tk.Frame(err_panel, bg=PANEL_BG)
        clr_row.pack(fill="x", padx=10, pady=(0, 8))
        Theme.button(clr_row, "Clear code", lambda: code_txt.delete("1.0", "end"),
                     bg=PANEL_BG, fg=MUTED, size=9, padx=8, pady=4).pack(side="left")
        Theme.button(clr_row, "Clear error", lambda: err_txt.delete("1.0", "end"),
                     bg=PANEL_BG, fg=MUTED, size=9, padx=8, pady=4).pack(side="left", padx=8)

        # ── Submit bar ────────────────────────────────────────────────────────
        submit_bar = tk.Frame(root, bg=PANEL_BG, height=70)
        submit_bar.pack(fill="x")
        submit_bar.pack_propagate(False)

        status_lbl = tk.Label(submit_bar, text="",
                              font=("Segoe UI", 10), fg=YELLOW, bg=PANEL_BG)
        status_lbl.pack(side="left", padx=20)

        def _submit():
            lang  = lang_var.get().strip()
            code  = code_txt.get("1.0", "end").strip()
            error = err_txt.get("1.0", "end").strip()

            # Resolve model key from display string
            model_display = model_var.get()
            model_key = list(GROQ_MODELS.keys())[0]
            for k, v in GROQ_MODELS.items():
                if v in model_display:
                    model_key = k
                    break

            # Resolve mode key
            mode_display = mode_display_var.get()
            mode_key = list(FIX_MODES.keys())[0]
            for k, v in FIX_MODES.items():
                if v == mode_display:
                    mode_key = k
                    break

            if not code:
                status_lbl.config(text="⚠  Please paste your code.", fg=YELLOW)
                return
            if not error:
                status_lbl.config(text="⚠  Please paste the error message.", fg=YELLOW)
                return

            lines = len(code.splitlines())
            if lines > MAX_CODE_LINES:
                status_lbl.config(
                    text=f"✖  Code too large ({lines} lines). Max {MAX_CODE_LINES}.", fg=RED)
                return

            self.result = (lang, code, error, model_key, mode_key)
            root.destroy()

        Theme.button(submit_bar, "⚡  Fix My Code",
                     _submit, bg=GREEN, fg=DARK_BG, size=13,
                     padx=36, pady=14).pack(side="right", padx=20, pady=10)

        root.mainloop()

        if self.result:
            return self.result
        return None, None, None, None, None


# ─────────────────────────────────────────────────────────────────────────────
#  PROCESSING WINDOW  (non-blocking spinner)
# ─────────────────────────────────────────────────────────────────────────────

class ProcessingWindow:
    def __init__(self, model_name: str, mode_label: str):
        self._root = None
        self._model_name  = model_name
        self._mode_label  = mode_label
        self._msg_var     = None
        self._bar         = None
        self._running     = True

    def show(self):
        def _build():
            self._root = tk.Tk()
            self._root.title("Nova AI — Fixing…")
            self._root.geometry("480x200")
            self._root.configure(bg=PANEL_BG)
            self._root.resizable(False, False)
            self._root.eval("tk::PlaceWindow . center")
            self._root.protocol("WM_DELETE_WINDOW", lambda: None)

            tk.Label(self._root, text="⚙  Fixing your code…",
                     font=("JetBrains Mono", 14, "bold"),
                     fg=ACCENT, bg=PANEL_BG).pack(pady=(28, 4))

            self._msg_var = tk.StringVar(value=f"Model: {self._model_name}  |  Mode: {self._mode_label}")
            tk.Label(self._root, textvariable=self._msg_var,
                     font=("Segoe UI", 10), fg=MUTED, bg=PANEL_BG).pack()

            style = ttk.Style(self._root)
            style.theme_use("clam")
            style.configure("Nova.Horizontal.TProgressbar",
                            troughcolor=DARK_BG, background=ACCENT,
                            thickness=6, borderwidth=0)

            self._bar = ttk.Progressbar(self._root, mode="indeterminate",
                                         style="Nova.Horizontal.TProgressbar",
                                         length=380)
            self._bar.pack(pady=20)
            self._bar.start(12)

            self._root.mainloop()

        t = threading.Thread(target=_build, daemon=True)
        t.start()
        time.sleep(0.15)   # Let window appear

    def update_msg(self, msg: str):
        if self._msg_var:
            try:
                self._msg_var.set(msg)
            except Exception:
                pass

    def close(self):
        self._running = False
        if self._root:
            try:
                self._root.quit()
                self._root.destroy()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
#  RESULT WINDOW
# ─────────────────────────────────────────────────────────────────────────────

class ResultWindow:
    def __init__(self, original_code: str, ai_result: dict,
                 language: str, mode_key: str):
        self._orig    = original_code
        self._result  = ai_result
        self._lang    = language
        self._mode    = mode_key
        self._fixed   = ai_result["fixed_code"]
        self._active_tab = tk.StringVar(value="fixed")

    def run(self):
        root = tk.Tk()
        ext  = LANGUAGE_EXTENSIONS.get(self._lang, self._lang)
        root.title(f"✅ Nova AI — {self._lang.upper()} Fixed")
        root.geometry("1100x820")
        root.configure(bg=DARK_BG)
        root.eval("tk::PlaceWindow . center")

        # ── Top bar ───────────────────────────────────────────────────────────
        top = tk.Frame(root, bg=PANEL_BG, height=60)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Label(top, text="✅  Code Fixed",
                 font=("JetBrains Mono", 15, "bold"),
                 fg=GREEN, bg=PANEL_BG).pack(side="left", padx=22, pady=14)

        # Stats chips
        stats = [
            (f"🤖 {GROQ_MODELS.get(self._result['model'], self._result['model'])}", ACCENT),
            (f"⏱ {self._result['latency_ms']} ms",   YELLOW),
            (f"📥 {self._result['tokens_in']} tok",   PURPLE),
            (f"📤 {self._result['tokens_out']} tok",  GREEN),
            (f"📄 {self._fixed.count(chr(10))+1} lines", MUTED),
        ]
        for label, color in stats:
            tk.Label(top, text=label,
                     font=("Segoe UI", 9, "bold"),
                     fg=color, bg=PANEL_BG,
                     padx=10, pady=5,
                     relief="flat").pack(side="left", padx=4, pady=14)

        # ── Tab bar ───────────────────────────────────────────────────────────
        tab_bar = tk.Frame(root, bg=DARK_BG)
        tab_bar.pack(fill="x", padx=0, pady=0)

        content_area = tk.Frame(root, bg=DARK_BG)
        content_area.pack(fill="both", expand=True, padx=20, pady=(8, 0))

        # We'll swap frames on tab click
        frames: dict[str, tk.Frame] = {}

        def _show_tab(name: str):
            self._active_tab.set(name)
            for n, f in frames.items():
                if n == name:
                    f.pack(fill="both", expand=True)
                else:
                    f.pack_forget()
            # Update tab button styles
            for btn_name, btn_w in tab_buttons.items():
                if btn_name == name:
                    btn_w.config(bg=ACCENT, fg=DARK_BG)
                else:
                    btn_w.config(bg=PANEL_BG, fg=MUTED)

        tab_buttons: dict[str, tk.Button] = {}
        for tab_name, tab_label in [
            ("fixed",    "📄 Fixed Code"),
            ("original", "🗒 Original"),
            ("diff",     "🔀 Diff View"),
            ("history",  "🕓 History"),
        ]:
            btn = tk.Button(tab_bar, text=tab_label,
                            font=("Segoe UI", 10, "bold"),
                            bg=PANEL_BG, fg=MUTED,
                            relief="flat", bd=0, cursor="hand2",
                            padx=18, pady=10,
                            command=lambda n=tab_name: _show_tab(n))
            btn.pack(side="left")
            tab_buttons[tab_name] = btn

        # ── TAB: Fixed Code ───────────────────────────────────────────────────
        f_fixed = tk.Frame(content_area, bg=DARK_BG)
        frames["fixed"] = f_fixed

        # File-like header
        fhdr = tk.Frame(f_fixed, bg=PANEL_BG)
        fhdr.pack(fill="x")
        tk.Label(fhdr, text=f"  📄  fixed_code.{ext}",
                 font=("JetBrains Mono", 11, "bold"),
                 fg=GREEN, bg=PANEL_BG, padx=10, pady=8).pack(side="left")

        def _copy():
            root.clipboard_clear()
            root.clipboard_append(self._fixed)
            _flash(fhdr, "✅ Copied!")

        def _flash(parent, msg):
            lbl = tk.Label(parent, text=msg,
                           font=("Segoe UI", 9, "bold"),
                           fg=GREEN, bg=PANEL_BG, padx=12)
            lbl.pack(side="right", pady=8)
            root.after(2000, lbl.destroy)

        def _save():
            from tkinter.filedialog import asksaveasfilename
            fn = asksaveasfilename(
                defaultextension=f".{ext}",
                filetypes=[("All files", "*.*"),
                           (f"{self._lang.upper()} files", f"*.{ext}")],
                title="Save Fixed Code",
                initialfile=f"fixed_code.{ext}",
            )
            if fn:
                try:
                    with open(fn, "w", encoding="utf-8") as f:
                        f.write(self._fixed)
                    messagebox.showinfo("Saved", f"✅ Saved to:\n{os.path.basename(fn)}")
                except Exception as exc:
                    messagebox.showerror("Error", str(exc))

        Theme.button(fhdr, "📋 Copy",  _copy,  bg="#388bfd", size=9, padx=10, pady=5).pack(side="right", padx=4, pady=6)
        Theme.button(fhdr, "💾 Save",  _save,  bg=YELLOW,    size=9, padx=10, pady=5).pack(side="right", padx=4, pady=6)

        _ff, fixed_txt = Theme.code_area(f_fixed, height=26, width=110)
        _ff.pack(fill="both", expand=True, pady=(2, 0))
        fixed_txt.insert("1.0", self._fixed)
        fixed_txt.config(state="normal")   # allow copy

        # ── TAB: Original Code ────────────────────────────────────────────────
        f_orig = tk.Frame(content_area, bg=DARK_BG)
        frames["original"] = f_orig

        tk.Label(f_orig, text="  🗒  original_code.{ext}",
                 font=("JetBrains Mono", 11), fg=MUTED, bg=PANEL_BG,
                 padx=10, pady=8).pack(fill="x")

        _of, orig_txt = Theme.code_area(f_orig, height=26, width=110, fg="#8b949e")
        _of.pack(fill="both", expand=True, pady=(2, 0))
        orig_txt.insert("1.0", self._orig)
        orig_txt.config(state="disabled")

        # ── TAB: Diff View ────────────────────────────────────────────────────
        f_diff = tk.Frame(content_area, bg=DARK_BG)
        frames["diff"] = f_diff

        diff_legend = tk.Frame(f_diff, bg=PANEL_BG)
        diff_legend.pack(fill="x", pady=(0, 2))
        for sym, label, color in [
            ("+ ", "Added",   "#196c2e"),
            ("- ", "Removed", "#67060c"),
            ("  ", "Same",    PANEL_BG),
        ]:
            tk.Label(diff_legend, text=f"{sym}{label}",
                     font=("JetBrains Mono", 9, "bold"),
                     fg=TEXT_PRIMARY, bg=color,
                     padx=12, pady=5).pack(side="left", padx=2)

        _df = tk.Frame(f_diff, bg=BORDER_COLOR, padx=1, pady=1)
        _df.pack(fill="both", expand=True)
        diff_txt = scrolledtext.ScrolledText(
            _df, font=("JetBrains Mono", 10),
            bg="#010409", fg=TEXT_PRIMARY,
            relief="flat", padx=12, pady=10,
            wrap=tk.NONE, state="disabled",
        )
        diff_txt.pack(fill="both", expand=True)

        diff_txt.tag_config("added",   background="#196c2e", foreground="#aff5b4")
        diff_txt.tag_config("removed", background="#67060c", foreground="#ffa198")
        diff_txt.tag_config("same",    foreground=MUTED)

        diff_txt.config(state="normal")
        diff_lines = _simple_diff(self._orig, self._fixed)
        for line, tag in diff_lines:
            prefix = "+ " if tag == "added" else ("- " if tag == "removed" else "  ")
            diff_txt.insert("end", prefix + line + "\n", tag)
        diff_txt.config(state="disabled")

        # Diff summary
        added   = sum(1 for _, t in diff_lines if t == "added")
        removed = sum(1 for _, t in diff_lines if t == "removed")
        tk.Label(f_diff, text=f"  +{added} added   -{removed} removed   "
                               f"{len(diff_lines)} total lines",
                 font=("Segoe UI", 9), fg=MUTED, bg=DARK_BG).pack(anchor="w", padx=4, pady=4)

        # ── TAB: History ──────────────────────────────────────────────────────
        f_hist = tk.Frame(content_area, bg=DARK_BG)
        frames["history"] = f_hist

        if not _session_history:
            tk.Label(f_hist, text="No history yet in this session.",
                     font=("Segoe UI", 11), fg=MUTED, bg=DARK_BG).pack(pady=40)
        else:
            canvas = tk.Canvas(f_hist, bg=DARK_BG, highlightthickness=0)
            vsb = tk.Scrollbar(f_hist, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=vsb.set)
            vsb.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)

            hist_inner = tk.Frame(canvas, bg=DARK_BG)
            canvas.create_window((0, 0), window=hist_inner, anchor="nw")

            for i, entry in enumerate(reversed(_session_history), 1):
                card = tk.Frame(hist_inner, bg=PANEL_BG, relief="flat",
                                padx=16, pady=12)
                card.pack(fill="x", padx=8, pady=4)

                info = (f"#{len(_session_history)-i+1}  •  "
                        f"{entry['timestamp']}  •  "
                        f"{entry['language'].upper()}  •  "
                        f"{GROQ_MODELS.get(entry['model'], entry['model'])}  •  "
                        f"{entry['tokens_out']} tokens out  •  "
                        f"{entry['latency_ms']} ms")
                tk.Label(card, text=info, font=("Segoe UI", 9),
                         fg=MUTED, bg=PANEL_BG).pack(anchor="w")
                tk.Label(card,
                         text=entry["fixed_code"][:120].replace("\n", " ") + "…",
                         font=("JetBrains Mono", 9),
                         fg=TEXT_CODE, bg=PANEL_BG,
                         anchor="w").pack(fill="x", pady=(4, 0))

            def _on_configure(e):
                canvas.configure(scrollregion=canvas.bbox("all"))
            hist_inner.bind("<Configure>", _on_configure)

        # ── Bottom bar ────────────────────────────────────────────────────────
        bot = tk.Frame(root, bg=PANEL_BG, height=58)
        bot.pack(fill="x", side="bottom")
        bot.pack_propagate(False)

        Theme.button(bot, "🔄 Fix Another",
                     root.destroy,
                     bg="#1f6feb", size=11,
                     padx=24, pady=12).pack(side="left", padx=16, pady=10)

        Theme.button(bot, "❌ Close",
                     root.destroy,
                     bg="#30363d", fg=TEXT_PRIMARY,
                     size=11, padx=24, pady=12).pack(side="right", padx=16, pady=10)

        # ── Init first tab ────────────────────────────────────────────────────
        _show_tab("fixed")

        root.mainloop()


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN ASYNC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

@function_tool()
async def fix_code_error() -> str:
    """
    Advanced Code Error Solver — Nova AI Code Fixer Pro

    Opens a GUI where the user can:
      • Select language (20+ supported)
      • Choose Groq model (5 options)
      • Choose fix mode: fix-only / optimize / refactor / secure / document / explain
      • Paste code (up to 500 lines) and error message

    After AI processing (with retry logic and rate-limit handling) shows:
      • Fixed code tab with copy/save
      • Original code tab
      • Side-by-side diff view (added/removed lines)
      • Session history tab

    Returns a status string for the agent.
    """
    # ── 1. Collect input ─────────────────────────────────────────────────────
    lang, code, error, model, mode = InputWindow().run()

    if not lang:
        return "❌ Cancelled by user."

    # ── 2. Show processing spinner ───────────────────────────────────────────
    model_label = GROQ_MODELS.get(model, model)
    mode_label  = FIX_MODES.get(mode, mode)
    spinner = ProcessingWindow(model_label, mode_label)
    spinner.show()

    # ── 3. Call Groq in thread pool (non-blocking) ───────────────────────────
    loop = asyncio.get_event_loop()
    ai_result = await loop.run_in_executor(
        None, _call_groq_sync, lang, code, error, mode, model
    )

    spinner.close()
    await asyncio.sleep(0.15)   # Let window destroy cleanly

    # ── 4. Handle AI error ───────────────────────────────────────────────────
    if ai_result["error"]:
        messagebox.showerror(
            "Nova AI — Error",
            f"AI call failed after {MAX_RETRIES} retries:\n\n{ai_result['error']}"
        )
        return f"❌ AI error: {ai_result['error']}"

    # ── 5. Save to session history ───────────────────────────────────────────
    _session_history.append({
        "timestamp":  datetime.now().strftime("%H:%M:%S"),
        "language":   lang,
        "model":      model,
        "mode":       mode,
        "code":       code,
        "error":      error,
        "fixed_code": ai_result["fixed_code"],
        "tokens_in":  ai_result["tokens_in"],
        "tokens_out": ai_result["tokens_out"],
        "latency_ms": ai_result["latency_ms"],
    })

    # ── 6. Show result window ────────────────────────────────────────────────
    ResultWindow(code, ai_result, lang, mode).run()

    return (
        f"✅ {lang.capitalize()} code fixed successfully "
        f"using {model_label} ({mode_label}). "
        f"Tokens: {ai_result['tokens_in']} in / {ai_result['tokens_out']} out. "
        f"Latency: {ai_result['latency_ms']} ms."
    )