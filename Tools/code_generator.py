"""
Code Generation & Modification Tools — Groq AI + Modern Tkinter UI
====================================================================
Camera Analysis Tool jaisa hi pattern:
  - Daemon thread pe Tkinter window
  - Step indicators with icons
  - Monospaced log, progress bar
  - asyncio-safe updates via root.after(0, fn)

Install:
    pip install aiohttp pyautogui pyperclip livekit-agents

Set env:
    export GROQ_API_KEY="your_key_here"
"""

import os
import asyncio
import subprocess
import tempfile
import threading
import time
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field

import aiohttp
import pyautogui
import pyperclip
import tkinter as tk
from tkinter import font as tkfont

from livekit.agents import function_tool

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

@dataclass
class GroqConfig:
    api_url: str = "https://api.groq.com/openai/v1/chat/completions"
    api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    model:   str = "llama-3.3-70b-versatile"
    temperature: float = 0.3
    max_tokens:  int   = 8192
    timeout:     int   = 120

    # Fallback models in order
    fallback_models: List[str] = field(default_factory=lambda: [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "qwen/qwen3-32b",
    ])


# ─────────────────────────────────────────────
# LANGUAGE CONFIG
# ─────────────────────────────────────────────

LANG_CONFIG: Dict[str, Dict] = {
    "python":     {"ext": "py",   "formatter": "black",    "syntax_check": ["python", "-m", "py_compile"]},
    "javascript": {"ext": "js",   "formatter": "prettier", "syntax_check": ["node", "--check"]},
    "typescript": {"ext": "ts",   "formatter": "prettier", "syntax_check": None},
    "html":       {"ext": "html", "formatter": "prettier", "syntax_check": None},
    "css":        {"ext": "css",  "formatter": "prettier", "syntax_check": None},
    "java":       {"ext": "java", "formatter": None,       "syntax_check": ["javac"]},
    "cpp":        {"ext": "cpp",  "formatter": "clang-format", "syntax_check": ["g++", "-fsyntax-only"]},
    "c":          {"ext": "c",    "formatter": "clang-format", "syntax_check": ["gcc", "-fsyntax-only"]},
    "go":         {"ext": "go",   "formatter": "gofmt",    "syntax_check": ["go", "vet"]},
    "rust":       {"ext": "rs",   "formatter": "rustfmt",  "syntax_check": ["rustc", "--edition=2021"]},
    "php":        {"ext": "php",  "formatter": None,       "syntax_check": ["php", "-l"]},
    "kotlin":     {"ext": "kt",   "formatter": "ktlint",   "syntax_check": None},
    "ruby":       {"ext": "rb",   "formatter": None,       "syntax_check": ["ruby", "-c"]},
    "swift":      {"ext": "swift","formatter": None,       "syntax_check": None},
    "bash":       {"ext": "sh",   "formatter": None,       "syntax_check": ["bash", "-n"]},
}

EXT_TO_LANG: Dict[str, str] = {
    f".{v['ext']}": k for k, v in LANG_CONFIG.items()
} | {".jsx": "javascript", ".tsx": "typescript", ".vue": "javascript"}

LANG_KEYWORDS: Dict[str, List[str]] = {
    "python":     ["python", "py", "pandas", "numpy", "django", "flask", "fastapi"],
    "javascript": ["javascript", "js", "node", "react", "vue", "angular", "express"],
    "typescript": ["typescript", "ts"],
    "html":       ["html", "webpage", "website"],
    "css":        ["css", "stylesheet", "styling"],
    "java":       ["java", "spring", "android"],
    "cpp":        ["c++", "cpp", "stl"],
    "c":          [" c program", "c language"],
    "go":         ["golang", "go lang"],
    "rust":       ["rust", "cargo"],
    "php":        ["php", "wordpress", "laravel"],
    "kotlin":     ["kotlin"],
    "ruby":       ["ruby", "rails"],
    "bash":       ["bash", "shell script", "sh"],
}


# ─────────────────────────────────────────────
# DESIGN TOKENS  (camera tool se identical)
# ─────────────────────────────────────────────

C = {
    "bg":          "#ffffff",
    "bg2":         "#f7f7f5",
    "bg3":         "#eeeeec",
    "border":      "#e5e5e3",
    "text":        "#1a1a1a",
    "muted":       "#888780",
    "hint":        "#b4b2a9",
    "purple":      "#534AB7",
    "purple_bg":   "#EEEDFE",
    "purple_text": "#3C3489",
    "green":       "#3B6D11",
    "green_bg":    "#EAF3DE",
    "green_text":  "#27500A",
    "red":         "#A32D2D",
    "red_bg":      "#FCEBEB",
    "dot_red":     "#E24B4A",
    "dot_yellow":  "#EF9F27",
    "dot_green":   "#639922",
}

W, H_BASE = 520, 44  # height is dynamic based on steps


# ─────────────────────────────────────────────
# MODERN TKINTER UI
# ─────────────────────────────────────────────

class CodeToolUI:
    """
    Modern popup UI — camera tool jaisa.
    Steps, progress bar, log, query display.
    Dynamic height based on number of steps.
    """

    def __init__(self, title: str, query: str, steps: List[str], subtitle: str = "Groq AI"):
        self.query     = query
        self.steps     = steps
        self.subtitle  = subtitle
        self.title_txt = title
        self.cancelled = False
        self._root     = None
        self._ready    = threading.Event()
        self._pbar_w   = W - 44

        # Height: topbar(44) + body padding(32) + model row(32) + pbar(20)
        #       + steps(34 each) + log(80) + query(36) + button(44) + margins
        H = 44 + 32 + 32 + 20 + len(steps) * 34 + 80 + 36 + 52 + 30
        self._H = max(H, 400)

        t = threading.Thread(target=self._build, daemon=True)
        t.start()
        self._ready.wait(timeout=4)

    # ── build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = tk.Tk()
        self._root = root
        root.title("")
        root.geometry(f"{W}x{self._H}")
        root.resizable(False, False)
        root.configure(bg=C["bg"])

        root.update_idletasks()
        sx = (root.winfo_screenwidth()  - W) // 2
        sy = (root.winfo_screenheight() - self._H) // 2
        root.geometry(f"{W}x{self._H}+{sx}+{sy}")

        self._fb  = tkfont.Font(family="Helvetica Neue", size=13)
        self._fbm = tkfont.Font(family="Helvetica Neue", size=12)
        self._fs  = tkfont.Font(family="Helvetica Neue", size=10)
        self._fm  = tkfont.Font(family="Menlo",          size=9)

        self._draw_topbar(root)
        self._draw_body(root)

        self._ready.set()
        root.protocol("WM_DELETE_WINDOW", self._on_cancel)
        root.mainloop()

    def _draw_topbar(self, root):
        bar = tk.Frame(root, bg=C["bg2"], height=44)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        dots = tk.Frame(bar, bg=C["bg2"])
        dots.place(x=14, rely=0.5, anchor="w")
        for col in [C["dot_red"], C["dot_yellow"], C["dot_green"]]:
            cv = tk.Canvas(dots, width=12, height=12, bg=C["bg2"], highlightthickness=0)
            cv.pack(side="left", padx=3)
            cv.create_oval(1, 1, 11, 11, fill=col, outline="")

        tk.Label(bar, text=self.title_txt, font=self._fb,
                 bg=C["bg2"], fg=C["muted"]).place(relx=0.5, rely=0.5, anchor="center")
        tk.Frame(root, bg=C["border"], height=1).pack(fill="x")

    def _draw_body(self, root):
        body = tk.Frame(root, bg=C["bg"], padx=22, pady=16)
        body.pack(fill="both", expand=True)

        # top row: model badge + step counter
        mr = tk.Frame(body, bg=C["bg"])
        mr.pack(fill="x", pady=(0, 10))

        dot = tk.Canvas(mr, width=8, height=8, bg=C["bg"], highlightthickness=0)
        dot.pack(side="left", padx=(0, 6))
        dot.create_oval(1, 1, 7, 7, fill=C["dot_green"], outline="")

        tk.Label(mr, text=self.subtitle, font=self._fs,
                 bg=C["purple_bg"], fg=C["purple_text"],
                 padx=9, pady=3).pack(side="left")

        self._step_counter = tk.Label(mr, text=f"Step 0 of {len(self.steps)}",
                                       font=self._fs, bg=C["bg"], fg=C["hint"])
        self._step_counter.pack(side="right")

        # progress bar
        pb = tk.Canvas(body, height=3, bg=C["bg2"], highlightthickness=0)
        pb.pack(fill="x", pady=(0, 12))
        self._pbar_canvas = pb
        self._pbar_fill   = pb.create_rectangle(0, 0, 0, 3, fill=C["purple"], width=0)
        pb.bind("<Configure>", lambda e: setattr(self, "_pbar_w", e.width))

        # step rows
        sf = tk.Frame(body, bg=C["bg"])
        sf.pack(fill="x", pady=(0, 10))

        self._srows, self._sdots, self._snames, self._sdetails = [], [], [], []
        for name in self.steps:
            row = tk.Frame(sf, bg=C["bg2"])
            row.pack(fill="x", pady=2)

            dc = tk.Canvas(row, width=28, height=28, bg=C["bg2"], highlightthickness=0)
            dc.pack(side="left", padx=(6, 0), pady=3)
            dc.create_oval(5, 5, 23, 23, fill=C["bg3"], outline="")

            nl = tk.Label(row, text=name, font=self._fbm, bg=C["bg2"], fg=C["hint"])
            nl.pack(side="left", padx=(8, 0), pady=4)

            dl = tk.Label(row, text="waiting", font=self._fs, bg=C["bg2"], fg=C["hint"])
            dl.pack(side="right", padx=(0, 10), pady=4)

            self._srows.append(row);  self._sdots.append(dc)
            self._snames.append(nl);  self._sdetails.append(dl)

        # log
        lw = tk.Frame(body, bg=C["bg2"])
        lw.pack(fill="x", pady=(0, 8))
        self._log = tk.Text(lw, height=4, font=self._fm,
                             bg=C["bg2"], fg=C["muted"],
                             bd=0, relief="flat", state="disabled",
                             wrap="none", padx=10, pady=8)
        self._log.pack(fill="x")
        self._log.tag_config("ok",     foreground=C["green"])
        self._log.tag_config("active", foreground=C["purple"])
        self._log.tag_config("err",    foreground=C["red"])
        self._log.tag_config("dim",    foreground=C["hint"])

        # query display
        qf = tk.Frame(body, bg=C["bg2"])
        qf.pack(fill="x", pady=(0, 12))
        tk.Label(qf, text="TASK", font=self._fs,
                 bg=C["bg2"], fg=C["hint"], padx=10, pady=5).pack(side="left")
        q = self.query if len(self.query) <= 52 else self.query[:49] + "…"
        tk.Label(qf, text=q, font=self._fbm,
                 bg=C["bg2"], fg=C["text"], pady=5).pack(side="left")

        # cancel button
        tk.Button(body, text="Cancel", font=self._fbm,
                  bg=C["bg"], fg=C["text"],
                  activebackground=C["bg2"], activeforeground=C["text"],
                  bd=1, relief="solid", highlightbackground=C["border"],
                  cursor="hand2", command=self._on_cancel,
                  width=18, pady=6).pack()

    # ── internals ─────────────────────────────────────────────────────────────

    def _on_cancel(self):
        self.cancelled = True
        if self._root:
            self._root.after(1200, self._root.destroy)

    def _log_add(self, msg: str, tag: str):
        def _do():
            self._log.config(state="normal")
            ts = time.strftime("%H:%M:%S")
            self._log.insert("1.0", f"{ts}  {msg}\n", tag)
            self._log.config(state="disabled")
        if self._root:
            self._root.after(0, _do)

    def _draw_dot(self, dc: tk.Canvas, state: str, bg: str):
        fill, check, inner = {
            "done":   (C["green"],  True,  False),
            "active": (C["purple"], False, True),
            "error":  (C["red"],    False, False),
            "idle":   (C["bg3"],    False, False),
        }.get(state, (C["bg3"], False, False))
        dc.config(bg=bg); dc.delete("all")
        dc.create_oval(5, 5, 23, 23, fill=fill, outline="")
        if check:
            dc.create_line(9, 14, 12, 17, fill="white", width=2, capstyle="round")
            dc.create_line(12, 17, 19, 10, fill="white", width=2, capstyle="round")
        elif inner:
            dc.create_oval(10, 10, 18, 18, fill="white", outline="")

    # ── public API ────────────────────────────────────────────────────────────

    def set_step(self, idx: int, state: str = "active", detail: str = ""):
        if not self._root or self.cancelled:
            return
        sm = {
            "done":   (C["green_bg"],  C["green_text"], C["green"]),
            "active": (C["purple_bg"], C["purple_text"], C["purple"]),
            "error":  (C["red_bg"],    C["red"],         C["red"]),
            "idle":   (C["bg2"],       C["hint"],        C["hint"]),
        }
        def _do():
            self._pbar_canvas.coords(
                self._pbar_fill, 0, 0,
                int(self._pbar_w * idx / len(self.steps)), 3)
            self._step_counter.config(text=f"Step {idx} of {len(self.steps)}")
            for i in range(len(self.steps)):
                s = "done" if i < idx else (state if i == idx else "idle")
                bg, fg, dfg = sm[s]
                self._srows[i].config(bg=bg)
                self._snames[i].config(bg=bg, fg=fg)
                self._sdetails[i].config(bg=bg, fg=dfg)
                self._draw_dot(self._sdots[i], s, bg)
                if i == idx:
                    self._sdetails[i].config(text=detail or "...")
                elif i < idx and self._sdetails[i].cget("text") in ("waiting", "..."):
                    self._sdetails[i].config(text="done")
                elif i > idx:
                    self._sdetails[i].config(text="waiting")
        self._root.after(0, _do)

    def log(self, msg: str, tag: str = "dim"):
        self._log_add(msg, tag)

    def finish(self, preview: str = ""):
        if not self._root:
            return
        def _do():
            self._pbar_canvas.coords(self._pbar_fill, 0, 0, self._pbar_w, 3)
            self._step_counter.config(text=f"Step {len(self.steps)} of {len(self.steps)}")
            if preview:
                p = preview[:68] + ("…" if len(preview) > 68 else "")
                self._log_add(p, "ok")
            self._root.after(2200, self._root.destroy)
        self._root.after(0, _do)

    def error(self, msg: str):
        self._log_add(f"Error: {msg}", "err")
        if self._root:
            self._root.after(2800, self._root.destroy)


# ─────────────────────────────────────────────
# GROQ CLIENT
# ─────────────────────────────────────────────

class GroqClient:
    def __init__(self, config: Optional[GroqConfig] = None):
        self.cfg = config or GroqConfig()

    async def complete(self, system: str, user: str, ui: Optional[CodeToolUI] = None) -> str:
        """API call with automatic model fallback."""
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type":  "application/json",
        }
        last_error = ""
        for model in self.cfg.fallback_models:
            try:
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    "temperature": self.cfg.temperature,
                    "max_tokens":  self.cfg.max_tokens,
                    "top_p": 0.9,
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.cfg.api_url, headers=headers, json=payload,
                        timeout=aiohttp.ClientTimeout(total=self.cfg.timeout)
                    ) as res:
                        data = await res.json()
                        if res.status == 200:
                            raw = (data.get("choices", [{}])[0]
                                       .get("message", {})
                                       .get("content", "")
                                       .strip())
                            return self._strip_markdown(raw)
                        # Rate limit — try next model
                        if res.status == 429:
                            if ui:
                                ui.log(f"Rate limit on {model}, trying next...", "dim")
                            continue
                        last_error = f"API {res.status}: {data}"
            except asyncio.TimeoutError:
                last_error = f"Timeout on {model}"
                if ui:
                    ui.log(f"Timeout on {model}, trying next...", "dim")
                continue
            except Exception as e:
                last_error = str(e)
                continue
        raise RuntimeError(f"All models failed. Last error: {last_error}")

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Remove ```lang ... ``` wrappers."""
        if not text.startswith("```"):
            return text
        lines = text.split("\n")
        # Drop first line (```python) and last line (```)
        end = len(lines) - 1
        while end > 0 and lines[end].strip() == "```":
            end -= 1
        return "\n".join(lines[1:end + 1]).strip()


# ─────────────────────────────────────────────
# LANGUAGE HELPERS
# ─────────────────────────────────────────────

def detect_language(prompt: str, forced: Optional[str] = None) -> str:
    if forced:
        return forced.lower()
    p = prompt.lower()
    for lang, keywords in LANG_KEYWORDS.items():
        if any(kw in p for kw in keywords):
            return lang
    return "python"


def lang_from_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return EXT_TO_LANG.get(ext, "python")


def validate_and_format(code: str, lang: str) -> Tuple[str, List[str]]:
    """
    Run syntax check + formatter (if available).
    Returns (formatted_code, list_of_notes).
    """
    cfg    = LANG_CONFIG.get(lang, {})
    notes  = []
    result = code

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=f".{cfg.get('ext', 'txt')}", delete=False
    ) as f:
        f.write(code)
        tmp = f.name

    try:
        # Syntax check
        sc = cfg.get("syntax_check")
        if sc:
            r = subprocess.run(sc + [tmp], capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                notes.append("syntax ok")
            else:
                notes.append(f"syntax warning: {r.stderr.strip()[:80]}")

        # Format
        fmt = cfg.get("formatter")
        if fmt == "black":
            r = subprocess.run(["black", "--quiet", tmp],
                                capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                with open(tmp) as f:
                    result = f.read()
                notes.append("formatted with black")
        elif fmt == "prettier":
            r = subprocess.run(["npx", "prettier", "--write", tmp],
                                capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                with open(tmp) as f:
                    result = f.read()
                notes.append("formatted with prettier")
        elif fmt == "gofmt":
            r = subprocess.run(["gofmt", "-w", tmp],
                                capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                with open(tmp) as f:
                    result = f.read()
                notes.append("formatted with gofmt")

    except (subprocess.TimeoutExpired, FileNotFoundError):
        notes.append("validation skipped (tools not installed)")
    finally:
        Path(tmp).unlink(missing_ok=True)

    return result, notes


def paste_to_editor(code: str):
    """Clipboard se paste karo — most reliable method."""
    pyperclip.copy(code)
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "v")


# ─────────────────────────────────────────────
# GENERATE AND TYPE TOOL
# ─────────────────────────────────────────────

GENERATE_STEPS = [
    "Detect language",
    "Groq API call",
    "Validate & format",
    "Open editor",
    "Paste & save",
]

_groq = GroqClient()


@function_tool()
async def generate_and_type_code(
    prompt:   str,
    filename: str,
    language: Optional[str] = None,
) -> str:
    """
    Generates complete, well-formatted code using Groq AI,
    pastes it into the editor, and saves the file.

    Args:
        prompt:   What code to generate.
        filename: File name to save as (e.g. 'app.py').
        language: Optional — force language ('python', 'javascript', etc.)
    """
    ui = CodeToolUI(
        title    = "Code Generator",
        query    = prompt,
        steps    = GENERATE_STEPS,
        subtitle = "Groq AI",
    )

    try:
        # Step 0 — Detect language
        ui.set_step(0, "active", "detecting...")
        lang     = detect_language(prompt, language) if language is None else language.lower()
        cfg      = LANG_CONFIG.get(lang, LANG_CONFIG["python"])
        ext      = cfg["ext"]
        # Auto-add extension if missing
        if not filename.endswith(f".{ext}"):
            filename = f"{Path(filename).stem}.{ext}"
        ui.set_step(0, "done", lang)
        ui.log(f"Language: {lang}  →  {filename}", "ok")

        if ui.cancelled:
            return "Cancelled."

        # Step 1 — Groq API call
        ui.set_step(1, "active", "generating...")
        ui.log(f"Sending prompt to {_groq.cfg.model}...", "active")

        system = f"""You are a professional {lang} developer.
Generate complete, runnable, well-formatted {lang} code.
Rules:
- Proper indentation per language style guide
- Meaningful variable/function names
- Necessary imports at the top
- Brief inline comments for non-obvious logic
- Error handling where appropriate
Return ONLY the code — no explanations, no markdown fences."""

        user = f"Write a complete {lang} program for: {prompt}"

        t0   = time.time()
        code = await _groq.complete(system, user, ui)
        t1   = round(time.time() - t0, 1)

        if not code.strip():
            ui.set_step(1, "error", "empty response")
            ui.error("Groq returned empty code")
            return "Code generation failed — empty response."

        ui.set_step(1, "done", f"{t1}s  {len(code.splitlines())} lines")
        ui.log(f"Generated {len(code.splitlines())} lines in {t1}s", "ok")

        if ui.cancelled:
            return "Cancelled."

        # Step 2 — Validate & format
        ui.set_step(2, "active", "checking...")
        ui.log("Running syntax check + formatter...", "active")

        code, notes = await asyncio.get_event_loop().run_in_executor(
            None, validate_and_format, code, lang
        )
        note_str = "  •  ".join(notes) if notes else "skipped"
        ui.set_step(2, "done", note_str[:30])
        ui.log(f"Validation: {note_str}", "ok")

        if ui.cancelled:
            return "Cancelled."

        # Step 3 — Open new editor tab
        ui.set_step(3, "active", "opening...")
        await asyncio.sleep(0.5)
        pyautogui.hotkey("ctrl", "n")
        await asyncio.sleep(1.5)
        ui.set_step(3, "done", "new tab")
        ui.log("New editor tab opened", "ok")

        # Step 4 — Paste + save
        ui.set_step(4, "active", "pasting...")
        ui.log("Pasting code via clipboard...", "active")

        await asyncio.get_event_loop().run_in_executor(None, paste_to_editor, code)
        await asyncio.sleep(0.8)

        # Save As
        pyautogui.hotkey("ctrl", "s")
        await asyncio.sleep(1)
        pyautogui.write(filename, interval=0.04)
        await asyncio.sleep(0.5)
        pyautogui.press("enter")
        await asyncio.sleep(0.5)

        ui.set_step(4, "done", "saved")
        ui.log(f"Saved as {filename}", "ok")
        ui.finish(preview=f"{lang} • {len(code.splitlines())} lines • {filename}")

        return (
            f"✅ {filename} generated and saved\n"
            f"   Language  : {lang}\n"
            f"   Lines     : {len(code.splitlines())}\n"
            f"   Validation: {note_str}\n"
            f"   API time  : {t1}s"
        )

    except Exception as e:
        ui.error(str(e))
        logger.error(f"generate_and_type_code failed: {e}")
        return f"❌ Failed: {e}"


# ─────────────────────────────────────────────
# MODIFY CODE FILE TOOL
# ─────────────────────────────────────────────

MODIFY_STEPS = [
    "Detect language",
    "Read current code",
    "Groq: generate changes",
    "Validate & format",
    "Paste & save",
]


@function_tool()
async def modify_code_file(file_search_term: str, change_request: str) -> str:
    """
    Opens a file by name, reads its current code, applies AI changes, and saves.

    Args:
        file_search_term: File name or path (e.g. 'app.py', 'src/index.js').
        change_request:   What to change (e.g. 'add input validation to all functions').
    """
    if not file_search_term.strip() or not change_request.strip():
        return "❌ Please provide both file name and change request."

    ui = CodeToolUI(
        title    = "Code Modifier",
        query    = change_request,
        steps    = MODIFY_STEPS,
        subtitle = "Groq AI",
    )

    try:
        # Step 0 — Detect language from extension
        ui.set_step(0, "active", "detecting...")
        lang = lang_from_ext(file_search_term)
        ui.set_step(0, "done", lang)
        ui.log(f"Language: {lang}  ({file_search_term})", "ok")

        if ui.cancelled:
            return "Cancelled."

        # Step 1 — Read current code
        ui.set_step(1, "active", "opening file...")
        ui.log("Searching and opening file...", "active")

        # Open via Windows search, then copy all
        await asyncio.sleep(0.3)
        pyautogui.hotkey("win", "s")
        await asyncio.sleep(0.8)
        pyautogui.write(file_search_term, interval=0.04)
        await asyncio.sleep(1.5)
        pyautogui.press("enter")
        await asyncio.sleep(2.0)

        # Select all + copy
        pyautogui.hotkey("ctrl", "a")
        await asyncio.sleep(0.4)
        pyautogui.hotkey("ctrl", "c")
        await asyncio.sleep(0.4)

        current_code = pyperclip.paste()
        if not current_code.strip():
            ui.set_step(1, "error", "empty")
            ui.error("File appears empty or could not be read")
            return f"❌ Could not read code from {file_search_term}"

        lines_before = len(current_code.splitlines())
        ui.set_step(1, "done", f"{lines_before} lines")
        ui.log(f"Read {lines_before} lines from {file_search_term}", "ok")

        if ui.cancelled:
            return "Cancelled."

        # Step 2 — Groq: generate modified code
        ui.set_step(2, "active", "generating...")
        ui.log("Sending to Groq for modification...", "active")

        system = f"""You are an expert {lang} developer modifying existing code.
Rules:
- Return the COMPLETE modified file — not just the diff
- Preserve all existing functionality unless the request says otherwise
- Follow {lang} style conventions
- Add brief comments near changed sections (prefix: # MODIFIED:)
- Keep the code syntactically correct and runnable
Return ONLY the code — no explanations, no markdown fences."""

        user = (
            f"CURRENT {lang.upper()} CODE:\n{current_code}\n\n"
            f"CHANGE REQUEST: {change_request}\n\n"
            f"Return the complete modified {lang} file."
        )

        t0           = time.time()
        modified     = await _groq.complete(system, user, ui)
        t1           = round(time.time() - t0, 1)
        lines_after  = len(modified.splitlines())

        ui.set_step(2, "done", f"{t1}s  Δ{lines_after - lines_before:+d} lines")
        ui.log(f"Modified in {t1}s: {lines_before} → {lines_after} lines", "ok")

        if ui.cancelled:
            return "Cancelled."

        # Step 3 — Validate & format
        ui.set_step(3, "active", "validating...")
        modified, notes = await asyncio.get_event_loop().run_in_executor(
            None, validate_and_format, modified, lang
        )
        note_str = "  •  ".join(notes) if notes else "skipped"
        ui.set_step(3, "done", note_str[:30])
        ui.log(f"Validation: {note_str}", "ok")

        if ui.cancelled:
            return "Cancelled."

        # Step 4 — Paste & save
        ui.set_step(4, "active", "replacing...")
        ui.log("Selecting all and pasting modified code...", "active")

        pyautogui.hotkey("ctrl", "a")
        await asyncio.sleep(0.3)
        pyautogui.press("delete")
        await asyncio.sleep(0.2)

        await asyncio.get_event_loop().run_in_executor(None, paste_to_editor, modified)
        await asyncio.sleep(0.5)
        pyautogui.hotkey("ctrl", "s")
        await asyncio.sleep(0.8)

        ui.set_step(4, "done", "saved")
        ui.log(f"File saved: {file_search_term}", "ok")
        ui.finish(preview=f"Modified {file_search_term}  {lines_before}→{lines_after} lines")

        return (
            f"✅ {file_search_term} modified\n"
            f"   Change    : {change_request}\n"
            f"   Lines     : {lines_before} → {lines_after} ({lines_after-lines_before:+d})\n"
            f"   Validation: {note_str}\n"
            f"   API time  : {t1}s"
        )

    except Exception as e:
        ui.error(str(e))
        logger.error(f"modify_code_file failed: {e}")
        return f"❌ Failed: {e}"


# ─────────────────────────────────────────────
# QUICK CODE CHANGE TOOL
# ─────────────────────────────────────────────

QUICK_STEPS = [
    "Read active file",
    "Groq: apply change",
    "Paste & save",
]


@function_tool()
async def quick_code_change(change_request: str) -> str:
    """
    Instantly modifies the currently open/active file without any search.
    Reads → modifies → saves in place.

    Args:
        change_request: What to change in the active file.
    """
    ui = CodeToolUI(
        title    = "Quick Modifier",
        query    = change_request,
        steps    = QUICK_STEPS,
        subtitle = "Groq AI",
    )

    try:
        # Step 0 — Read active file
        ui.set_step(0, "active", "reading...")
        ui.log("Saving and reading current file...", "active")

        pyautogui.hotkey("ctrl", "s")
        await asyncio.sleep(0.4)
        pyautogui.hotkey("ctrl", "a")
        await asyncio.sleep(0.3)
        pyautogui.hotkey("ctrl", "c")
        await asyncio.sleep(0.4)

        current_code = pyperclip.paste()
        if not current_code.strip():
            ui.set_step(0, "error", "empty")
            ui.error("No code found in active editor")
            return "❌ Active editor appears empty."

        lines_before = len(current_code.splitlines())
        ui.set_step(0, "done", f"{lines_before} lines")
        ui.log(f"Read {lines_before} lines", "ok")

        if ui.cancelled:
            return "Cancelled."

        # Step 1 — Groq: apply change
        ui.set_step(1, "active", "generating...")
        ui.log("Applying change via Groq...", "active")

        system = (
            "You are a code modification expert. Modify the provided code as requested.\n"
            "Return ONLY the complete modified code — no explanations, no markdown fences."
        )
        user = (
            f"CURRENT CODE:\n{current_code}\n\n"
            f"CHANGE: {change_request}\n\n"
            "Return the complete modified code."
        )

        t0       = time.time()
        modified = await _groq.complete(system, user, ui)
        t1       = round(time.time() - t0, 1)
        lines_after = len(modified.splitlines())

        ui.set_step(1, "done", f"{t1}s  Δ{lines_after - lines_before:+d}")
        ui.log(f"Done in {t1}s: {lines_before} → {lines_after} lines", "ok")

        if ui.cancelled:
            return "Cancelled."

        # Step 2 — Paste & save
        ui.set_step(2, "active", "replacing...")

        pyautogui.hotkey("ctrl", "a")
        await asyncio.sleep(0.2)
        pyautogui.press("delete")
        await asyncio.sleep(0.2)

        await asyncio.get_event_loop().run_in_executor(None, paste_to_editor, modified)
        await asyncio.sleep(0.4)
        pyautogui.hotkey("ctrl", "s")
        await asyncio.sleep(0.6)

        ui.set_step(2, "done", "saved")
        ui.log("File saved", "ok")
        ui.finish(preview=f"{change_request}")

        return (
            f"✅ Quick change applied\n"
            f"   Change : {change_request}\n"
            f"   Lines  : {lines_before} → {lines_after} ({lines_after - lines_before:+d})\n"
            f"   Time   : {t1}s"
        )

    except Exception as e:
        ui.error(str(e))
        logger.error(f"quick_code_change failed: {e}")
        return f"❌ Failed: {e}"


# ─────────────────────────────────────────────
# RUN FILE IN VSCODE TOOL
# ─────────────────────────────────────────────

RUN_STEPS = [
    "Detect file type",
    "Open terminal",
    "Execute command",
]

# Extension → (interpreter, needs_compile)
RUN_MAP: Dict[str, Tuple[str, bool]] = {
    ".py":   ("python",      False),
    ".js":   ("node",        False),
    ".ts":   ("ts-node",     False),
    ".rb":   ("ruby",        False),
    ".php":  ("php",         False),
    ".go":   ("go run",      False),
    ".sh":   ("bash",        False),
    ".ps1":  ("powershell",  False),
    ".java": ("javac",       True),
    ".cpp":  ("g++",         True),
    ".c":    ("gcc",         True),
    ".rs":   ("cargo run",   False),
    ".html": ("start",       False),   # open in browser (Windows)
}


@function_tool()
async def run_file_in_vscode(file_path: str) -> str:
    """
    Runs the specified file in VS Code's integrated terminal.
    Automatically detects language and builds compile + run commands.

    Args:
        file_path: Full or relative path to the file (e.g. 'app.py', 'src/Main.java').
    """
    ui = CodeToolUI(
        title    = "File Runner",
        query    = file_path,
        steps    = RUN_STEPS,
        subtitle = "VS Code Terminal",
    )

    try:
        # Step 0 — Detect file type
        ui.set_step(0, "active", "checking...")
        ext = Path(file_path).suffix.lower()

        if ext not in RUN_MAP:
            ui.set_step(0, "error", f"unknown: {ext}")
            ui.error(f"Unsupported extension: {ext}")
            return f"❌ Unsupported file type: {ext}"

        runner, needs_compile = RUN_MAP[ext]
        ui.set_step(0, "done", runner)
        ui.log(f"Runner: {runner}  compile={needs_compile}", "ok")

        # Step 1 — Open terminal
        ui.set_step(1, "active", "opening...")
        ui.log("Opening VS Code terminal...", "active")

        pyautogui.hotkey("ctrl", "`")
        await asyncio.sleep(1.0)
        pyautogui.hotkey("ctrl", "l")   # clear terminal
        await asyncio.sleep(0.4)
        ui.set_step(1, "done", "ready")
        ui.log("Terminal opened", "ok")

        # Step 2 — Execute
        ui.set_step(2, "active", "running...")

        stem = Path(file_path).stem

        if needs_compile:
            if ext == ".java":
                compile_cmd = f'javac "{file_path}"'
                run_cmd     = f'java "{stem}"'
            else:  # C / C++
                out = str(Path(file_path).with_suffix(""))
                compile_cmd = f'{runner} "{file_path}" -o "{out}"'
                run_cmd     = f'"{out}"'

            ui.log(f"Compiling: {compile_cmd}", "active")
            pyautogui.write(compile_cmd, interval=0.03)
            pyautogui.press("enter")
            await asyncio.sleep(3.0)  # compile time

            ui.log(f"Running: {run_cmd}", "active")
            pyautogui.write(run_cmd, interval=0.03)
            pyautogui.press("enter")

        elif ext == ".html":
            cmd = f'start "" "{file_path}"'
            pyautogui.write(cmd, interval=0.03)
            pyautogui.press("enter")
            ui.log("Opening in default browser", "ok")

        else:
            cmd = f'{runner} "{file_path}"'
            ui.log(f"Running: {cmd}", "active")
            pyautogui.write(cmd, interval=0.03)
            pyautogui.press("enter")

        ui.set_step(2, "done", "executing")
        ui.log(f"Executed: {file_path}", "ok")
        ui.finish(preview=f"Running {Path(file_path).name}")

        return (
            f"✅ Running {file_path}\n"
            f"   Runner  : {runner}\n"
            f"   Compile : {'yes' if needs_compile else 'no'}"
        )

    except Exception as e:
        ui.error(str(e))
        logger.error(f"run_file_in_vscode failed: {e}")
        return f"❌ Failed: {e}"