"""
Camera Analysis Tool — Ollama + Modern Tkinter UI
==================================================
Clean, flat, modern design — macOS-style window chrome,
step indicators with icons, monospaced log, query display.

Install:
    pip install ollama opencv-python livekit-agents

Pull model:
    ollama pull qwen2.5:2b
"""

import asyncio
import os
import cv2
import time
import threading
from typing import Optional
from dataclasses import dataclass, field

import ollama
import tkinter as tk
from tkinter import font as tkfont

from livekit.agents import function_tool


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

@dataclass
class OllamaConfig:
    host:        str   = field(default_factory=lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    model:       str   = field(default_factory=lambda: os.getenv("OLLAMA_VISION_MODEL", "qwen3.5:2b"))
    temperature: float = 0.4
    max_tokens:  int   = 1024


@dataclass
class CameraConfig:
    width:         int = 1280
    height:        int = 720
    warmup_frames: int = 10
    jpeg_quality:  int = 92
    device_index:  int = 0


# ─────────────────────────────────────────────
# DESIGN TOKENS
# ─────────────────────────────────────────────

C = {
    "bg":           "#ffffff",
    "bg2":          "#f7f7f5",
    "bg3":          "#eeeeec",
    "border":       "#e5e5e3",
    "text":         "#1a1a1a",
    "muted":        "#888780",
    "hint":         "#b4b2a9",
    "purple":       "#534AB7",
    "purple_bg":    "#EEEDFE",
    "purple_text":  "#3C3489",
    "purple_border":"#AFA9EC",
    "green":        "#3B6D11",
    "green_bg":     "#EAF3DE",
    "green_text":   "#27500A",
    "green_border": "#97C459",
    "red":          "#A32D2D",
    "red_bg":       "#FCEBEB",
    "dot_red":      "#E24B4A",
    "dot_yellow":   "#EF9F27",
    "dot_green":    "#639922",
}

STEPS = [
    "Ollama check",
    "Camera open",
    "Warmup frames",
    "Frame capture",
    "Translate query",
    "Ollama inference",
    "Result ready",
]

W, H = 500, 560


# ─────────────────────────────────────────────
# MODERN TKINTER UI
# ─────────────────────────────────────────────

class CameraAnalysisUI:
    """
    Clean modern popup — daemon thread, asyncio-safe.
    All updates via root.after(0, fn).
    """

    def __init__(self, query: str, model: str):
        self.query     = query
        self.model     = model
        self.cancelled = False
        self._root     = None
        self._ready    = threading.Event()
        self._pbar_w   = W - 44

        t = threading.Thread(target=self._build, daemon=True)
        t.start()
        self._ready.wait(timeout=4)

    # ── build window ──────────────────────────────────────────────────────────

    def _build(self):
        root = tk.Tk()
        self._root = root
        root.title("")
        root.geometry(f"{W}x{H}")
        root.resizable(False, False)
        root.configure(bg=C["bg"])

        root.update_idletasks()
        x = (root.winfo_screenwidth()  - W) // 2
        y = (root.winfo_screenheight() - H) // 2
        root.geometry(f"{W}x{H}+{x}+{y}")

        # fonts
        self._fb  = tkfont.Font(family="Helvetica Neue", size=13, weight="normal")
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

        dots_f = tk.Frame(bar, bg=C["bg2"])
        dots_f.place(x=14, rely=0.5, anchor="w")
        for col in [C["dot_red"], C["dot_yellow"], C["dot_green"]]:
            cv = tk.Canvas(dots_f, width=12, height=12, bg=C["bg2"], highlightthickness=0)
            cv.pack(side="left", padx=3)
            cv.create_oval(1, 1, 11, 11, fill=col, outline="")

        tk.Label(bar, text="Camera Analysis", font=self._fb,
                 bg=C["bg2"], fg=C["muted"]).place(relx=0.5, rely=0.5, anchor="center")

        tk.Frame(root, bg=C["border"], height=1).pack(fill="x")

    def _draw_body(self, root):
        body = tk.Frame(root, bg=C["bg"], padx=22, pady=16)
        body.pack(fill="both", expand=True)

        # model row
        mr = tk.Frame(body, bg=C["bg"])
        mr.pack(fill="x", pady=(0, 10))

        dot_c = tk.Canvas(mr, width=8, height=8, bg=C["bg"], highlightthickness=0)
        dot_c.pack(side="left", padx=(0, 6))
        dot_c.create_oval(1, 1, 7, 7, fill=C["dot_green"], outline="")

        tk.Label(mr, text=self.model, font=self._fs,
                 bg=C["purple_bg"], fg=C["purple_text"],
                 padx=9, pady=3).pack(side="left")

        tk.Label(mr, text="Ollama", font=self._fs,
                 bg=C["bg2"], fg=C["muted"],
                 padx=9, pady=3).pack(side="left", padx=(5, 0))

        self._step_counter = tk.Label(mr, text="Step 0 of 7",
                                       font=self._fs, bg=C["bg"], fg=C["hint"])
        self._step_counter.pack(side="right")

        # progress bar
        pb = tk.Canvas(body, height=3, bg=C["bg2"], highlightthickness=0)
        pb.pack(fill="x", pady=(0, 14))
        self._pbar_canvas = pb
        self._pbar_fill   = pb.create_rectangle(0, 0, 0, 3, fill=C["purple"], width=0)

        def _on_resize(e):
            self._pbar_w = e.width
        pb.bind("<Configure>", _on_resize)

        # step rows
        sf = tk.Frame(body, bg=C["bg"])
        sf.pack(fill="x", pady=(0, 10))

        self._srows   = []
        self._sdots   = []
        self._snames  = []
        self._sdetails= []

        for name in STEPS:
            row = tk.Frame(sf, bg=C["bg2"])
            row.pack(fill="x", pady=2)

            dc = tk.Canvas(row, width=28, height=28, bg=C["bg2"], highlightthickness=0)
            dc.pack(side="left", padx=(6, 0), pady=3)
            dc.create_oval(5, 5, 23, 23, fill=C["bg3"], outline="", tags="circ")

            nl = tk.Label(row, text=name, font=self._fbm, bg=C["bg2"], fg=C["hint"])
            nl.pack(side="left", padx=(8, 0), pady=4)

            dl = tk.Label(row, text="waiting", font=self._fs, bg=C["bg2"], fg=C["hint"])
            dl.pack(side="right", padx=(0, 10), pady=4)

            self._srows.append(row)
            self._sdots.append(dc)
            self._snames.append(nl)
            self._sdetails.append(dl)

        # log
        log_wrap = tk.Frame(body, bg=C["bg2"])
        log_wrap.pack(fill="x", pady=(0, 10))

        self._log = tk.Text(log_wrap, height=4, font=self._fm,
                             bg=C["bg2"], fg=C["muted"],
                             bd=0, relief="flat", state="disabled",
                             wrap="none", padx=10, pady=8)
        self._log.pack(fill="x")
        self._log.tag_config("ok",     foreground=C["green"])
        self._log.tag_config("active", foreground=C["purple"])
        self._log.tag_config("err",    foreground=C["red"])
        self._log.tag_config("dim",    foreground=C["hint"])

        # query box
        qf = tk.Frame(body, bg=C["bg2"])
        qf.pack(fill="x", pady=(0, 12))
        tk.Label(qf, text="QUERY", font=self._fs,
                 bg=C["bg2"], fg=C["hint"], padx=10, pady=5).pack(side="left")
        q = self.query if len(self.query) <= 54 else self.query[:51] + "…"
        tk.Label(qf, text=q, font=self._fbm,
                 bg=C["bg2"], fg=C["text"], pady=5).pack(side="left")

        # cancel
        tk.Button(body, text="Cancel", font=self._fbm,
                  bg=C["bg"], fg=C["text"],
                  activebackground=C["bg2"], activeforeground=C["text"],
                  bd=1, relief="solid", highlightbackground=C["border"],
                  cursor="hand2", command=self._on_cancel,
                  width=18, pady=6).pack()

    # ── internal ──────────────────────────────────────────────────────────────

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
        colors = {
            "done":   (C["green"],  True,  False),
            "active": (C["purple"], False, True),
            "error":  (C["red"],    False, False),
            "idle":   (C["bg3"],    False, False),
        }
        fill, checkmark, inner = colors.get(state, colors["idle"])
        dc.config(bg=bg)
        dc.delete("all")
        dc.create_oval(5, 5, 23, 23, fill=fill, outline="")
        if checkmark:
            dc.create_line(9, 14, 12, 17, fill="white", width=2, capstyle="round")
            dc.create_line(12, 17, 19, 10, fill="white", width=2, capstyle="round")
        elif inner:
            dc.create_oval(10, 10, 18, 18, fill="white", outline="")

    # ── public API ────────────────────────────────────────────────────────────

    def set_step(self, idx: int, state: str = "active", detail: str = ""):
        if not self._root or self.cancelled:
            return

        style_map = {
            "done":   (C["green_bg"],  C["green_text"],  C["green"]),
            "active": (C["purple_bg"], C["purple_text"], C["purple"]),
            "error":  (C["red_bg"],    C["red"],         C["red"]),
            "idle":   (C["bg2"],       C["hint"],        C["hint"]),
        }

        def _do():
            self._pbar_canvas.coords(
                self._pbar_fill, 0, 0,
                int(self._pbar_w * idx / len(STEPS)), 3
            )
            self._step_counter.config(text=f"Step {idx} of {len(STEPS)}")

            for i in range(len(STEPS)):
                s = "done" if i < idx else (state if i == idx else "idle")
                bg, fg, dfg = style_map[s]

                self._srows[i].config(bg=bg)
                self._snames[i].config(bg=bg, fg=fg)
                self._sdetails[i].config(bg=bg, fg=dfg)
                self._draw_dot(self._sdots[i], s, bg)

                if i == idx:
                    self._sdetails[i].config(text=detail or "...")
                elif i < idx:
                    cur = self._sdetails[i].cget("text")
                    if cur in ("waiting", "..."):
                        self._sdetails[i].config(text="done")
                else:
                    self._sdetails[i].config(text="waiting")

        self._root.after(0, _do)

    def log(self, msg: str, tag: str = "dim"):
        self._log_add(msg, tag)

    def finish(self, result_preview: str = ""):
        if not self._root:
            return
        def _do():
            self._pbar_canvas.coords(self._pbar_fill, 0, 0, self._pbar_w, 3)
            self._step_counter.config(text=f"Step {len(STEPS)} of {len(STEPS)}")
            if result_preview:
                p = result_preview[:68] + ("…" if len(result_preview) > 68 else "")
                self._log_add("Result: " + p, "ok")
            self._root.after(2200, self._root.destroy)
        self._root.after(0, _do)

    def error(self, msg: str):
        self._log_add("Error: " + msg, "err")
        if self._root:
            self._root.after(2800, self._root.destroy)


# ─────────────────────────────────────────────
# TRANSLATION
# ─────────────────────────────────────────────

def is_english(text: str) -> bool:
    try:
        return all(ord(c) < 128 or c.isspace() or c in ".,!?;:'\"()" for c in text)
    except Exception:
        return True


async def translate_to_english(text: str) -> str:
    if not text.strip() or is_english(text):
        return text
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            url    = "https://translate.googleapis.com/translate_a/single"
            params = {"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": text}
            async with s.get(url, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                    t    = "".join(p[0] for p in data[0] if p[0])
                    if t:
                        return t
    except Exception:
        pass
    return text


# ─────────────────────────────────────────────
# CAMERA
# ─────────────────────────────────────────────

class CameraCapture:
    def __init__(self, config: Optional[CameraConfig] = None):
        self.config = config or CameraConfig()

    async def capture(self, ui: CameraAnalysisUI) -> Optional[bytes]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync, ui)

    def _sync(self, ui: CameraAnalysisUI) -> Optional[bytes]:
        cap = None
        try:
            cap = cv2.VideoCapture(self.config.device_index)
            if not cap.isOpened():
                ui.log("Camera device not found", "err")
                return None

            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.config.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
            cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
            ui.log(f"Camera opened ({self.config.width}x{self.config.height})", "ok")

            for i in range(self.config.warmup_frames):
                cap.read()
                ui.set_step(2, "active", f"frame {i+1}/{self.config.warmup_frames}")
                if ui.cancelled:
                    return None

            ui.log(f"Warmup done ({self.config.warmup_frames} frames)", "ok")

            ret, frame = cap.read()
            if not ret or frame is None:
                ui.log("Frame read failed", "err")
                return None

            params  = [cv2.IMWRITE_JPEG_QUALITY, self.config.jpeg_quality]
            ok, enc = cv2.imencode(".jpg", frame, params)
            if ok:
                kb = len(enc.tobytes()) // 1024
                ui.log(f"Captured ~{kb} KB JPEG", "ok")
                return enc.tobytes()
            return None

        except Exception as e:
            ui.log(f"Camera error: {e}", "err")
            return None
        finally:
            if cap:
                cap.release()


# ─────────────────────────────────────────────
# ANALYZER
# ─────────────────────────────────────────────

class OllamaVisionAnalyzer:
    def __init__(
        self,
        ollama_config: Optional[OllamaConfig] = None,
        camera_config: Optional[CameraConfig] = None,
    ):
        self.cfg    = ollama_config or OllamaConfig()
        self.camera = CameraCapture(camera_config)
        self.client = ollama.Client(host=self.cfg.host)

    def is_running(self) -> bool:
        try:
            self.client.list()
            return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            return [m.model for m in self.client.list().models]
        except Exception:
            return []

    def _infer(self, query: str, image_bytes: bytes) -> str:
        try:
            r = self.client.chat(
                model=self.cfg.model,
                messages=[{
                    "role":    "user",
                    "content": query,
                    "images":  [image_bytes],
                }],
                options={
                    "temperature": self.cfg.temperature,
                    "num_predict": self.cfg.max_tokens,
                },
            )
            return r.message.content.strip()
        except ollama.ResponseError as e:
            if "not found" in str(e).lower():
                return f"Model '{self.cfg.model}' not found. Run: ollama pull {self.cfg.model}"
            return f"Ollama error: {e}"
        except Exception as e:
            return f"Error: {e}"

    async def analyze(self, query: str, image_bytes: bytes) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._infer, query, image_bytes)

    async def run_with_ui(self, query: str) -> str:
        ui = CameraAnalysisUI(query=query, model=self.cfg.model)

        try:
            # Step 0 — Ollama
            ui.set_step(0, "active", "pinging...")
            ui.log("Checking Ollama server...", "active")

            if not self.is_running():
                ui.set_step(0, "error", "not found")
                ui.log(f"Cannot reach {self.cfg.host}", "err")
                ui.error("Ollama not running")
                return f"Ollama not running.\nStart: ollama serve\nPull: ollama pull {self.cfg.model}"

            models = self.list_models()
            ui.set_step(0, "done", "ok")
            ui.log(f"Ollama ready — {len(models)} model(s)", "ok")

            # Step 1 — Camera
            ui.set_step(1, "active", "opening...")
            ui.log("Opening camera...", "active")

            # Steps 2+3 handled inside CameraCapture._sync
            ui.set_step(2, "active", "settling...")
            image_bytes = await self.camera.capture(ui)

            if ui.cancelled:
                return "Cancelled."

            if not image_bytes:
                ui.set_step(1, "error", "failed")
                ui.error("Camera not available")
                return "Camera capture failed."

            ui.set_step(1, "done", "1280×720")
            ui.set_step(2, "done", "10 frames")
            ui.set_step(3, "done", "captured")

            # Step 4 — Translate
            ui.set_step(4, "active", "checking...")
            ui.log("Checking query language...", "active")

            if not is_english(query):
                ui.log("Non-English detected — translating...", "active")
                query = await translate_to_english(query) or query
                ui.log(f"Translated: {query[:50]}", "ok")
            else:
                ui.log("English query — no translation needed", "dim")

            ui.set_step(4, "done", "ready")

            # Step 5 — Inference
            ui.set_step(5, "active", "running...")
            ui.log(f"Sending to {self.cfg.model}...", "active")

            t0      = time.time()
            result  = await self.analyze(query, image_bytes)
            elapsed = f"{round(time.time() - t0, 1)}s"

            ui.set_step(5, "done", elapsed)
            ui.log(f"Inference done in {elapsed}", "ok")

            # Step 6 — Done
            ui.set_step(6, "done", "complete")
            ui.log("Result ready", "ok")
            ui.finish(result_preview=result)

            return result

        except Exception as e:
            ui.error(str(e))
            return f"Unexpected error: {e}"


# ─────────────────────────────────────────────
# SINGLETON + LIVEKIT TOOLS
# ─────────────────────────────────────────────

_analyzer = OllamaVisionAnalyzer()


@function_tool()
async def camera_analysis(query: str) -> str:
    """
    Capture a photo from the webcam and analyze it using a local Ollama vision model.
    Shows a real-time progress window during the pipeline.

    Args:
        query: What to analyze or ask about the image (any language).

    Returns:
        Text description or answer from the local vision model.
    """
    return await _analyzer.run_with_ui(query)


@function_tool()
async def list_available_models() -> str:
    """List all models available in local Ollama installation."""
    models = _analyzer.list_models()
    if not models:
        return "No models found or Ollama is not running. Run: ollama serve"
    return "Available:\n" + "\n".join(f"  {m}" for m in models)


@function_tool()
async def switch_vision_model(model_name: str) -> str:
    """
    Switch active Ollama vision model at runtime.

    Args:
        model_name: e.g. 'llava', 'moondream', 'qwen2.5:2b'
    """
    available = _analyzer.list_models()
    if model_name not in available:
        return (
            f"'{model_name}' not found locally.\n"
            f"Pull: ollama pull {model_name}\n"
            f"Available: {', '.join(available) or 'none'}"
        )
    _analyzer.cfg.model = model_name
    return f"Switched to: {model_name}"