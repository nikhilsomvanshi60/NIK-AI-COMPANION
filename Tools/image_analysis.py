"""
Image Analysis Tool — Ollama + Modern Tkinter UI
=================================================
Camera Analysis Tool jaisa hi pattern:
  - Daemon thread pe Tkinter window
  - Step indicators with icons
  - Monospaced log, query display
  - asyncio-safe updates via root.after(0, fn)

Install:
    pip install ollama pillow aiohttp livekit-agents

Pull model:
    ollama pull llava
    ollama pull moondream
    ollama pull qwen2.5:2b
"""

import asyncio
import os
import time
import threading
import mimetypes
import io
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path

import ollama
import aiohttp
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog
from PIL import Image, ImageTk

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
class ImageConfig:
    max_size_mb:           float = 20.0
    supported_formats:     tuple = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff')
    preview_size:          tuple = (260, 220)
    compress_threshold_mb: float = 5.0
    jpeg_quality:          int   = 85


# ─────────────────────────────────────────────
# DESIGN TOKENS  (camera tool se same — identical look)
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
    "File select",
    "Validate image",
    "Read file",
    "Translate query",
    "Ollama inference",
    "Result ready",
]

W, H = 500, 600


# ─────────────────────────────────────────────
# MODERN TKINTER UI  (camera tool jaisa hi)
# ─────────────────────────────────────────────

class ImageAnalysisUI:
    """
    Clean modern popup — daemon thread, asyncio-safe.
    All updates via root.after(0, fn).
    Camera Analysis UI ka same pattern — sirf title aur steps alag hain.
    """

    def __init__(self, query: str, model: str):
        self.query     = query
        self.model     = model
        self.cancelled = False
        self._root     = None
        self._ready    = threading.Event()
        self._pbar_w   = W - 44

        # File selection results — events se asyncio ko signal karo
        self._selected_file:  Optional[str]  = None
        self._file_confirmed: Optional[bool] = None
        self._file_event      = threading.Event()
        self._confirm_event   = threading.Event()

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

        tk.Label(bar, text="Image Analysis", font=self._fb,
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

        self._srows    = []
        self._sdots    = []
        self._snames   = []
        self._sdetails = []

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
        # Waiting events unblock karo
        self._file_event.set()
        self._confirm_event.set()
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

    # ── Dialog helpers (Tkinter thread pe chalte hain) ────────────────────────

    def open_file_dialog(self):
        """
        File dialog Tkinter thread pe kholo.
        Result self._selected_file mein, phir _file_event set karo.
        """
        def _do():
            path = filedialog.askopenfilename(
                parent=self._root,
                title="Select an image to analyze",
                filetypes=[
                    ("Image files", "*.jpg *.jpeg *.png *.gif *.bmp *.webp *.tiff"),
                    ("JPEG files",  "*.jpg *.jpeg"),
                    ("PNG files",   "*.png"),
                    ("All files",   "*.*"),
                ],
                initialdir=str(Path.home() / "Pictures"),
            )
            self._selected_file = path if path else None
            self._file_event.set()

        if self._root and not self.cancelled:
            self._root.after(0, _do)

    def show_confirm_dialog(self, image_info: Dict[str, Any]):
        """
        Preview + Confirm dialog Tkinter thread pe dikhao.
        Result self._file_confirmed mein, phir _confirm_event set karo.
        """
        def _do():
            dlg = tk.Toplevel(self._root)
            dlg.title("Confirm Image")
            dlg.geometry("380x460")
            dlg.resizable(False, False)
            dlg.configure(bg=C["bg"])
            dlg.attributes("-topmost", True)

            px = self._root.winfo_x()
            py = self._root.winfo_y()
            dlg.geometry(f"380x460+{px + 60}+{py + 60}")

            tk.Label(dlg, text="Selected Image", font=self._fb,
                     bg=C["bg"], fg=C["text"]).pack(pady=(16, 8))

            # Image preview
            try:
                img = Image.open(image_info["path"])
                img.thumbnail((260, 220), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                lbl = tk.Label(dlg, image=photo, bg=C["bg2"])
                lbl.image = photo  # GC se bachao
                lbl.pack(pady=6)
            except Exception:
                tk.Label(dlg, text="(preview unavailable)",
                         font=self._fs, bg=C["bg"], fg=C["hint"]).pack(pady=6)

            # File details
            df = tk.Frame(dlg, bg=C["bg2"], padx=12, pady=8)
            df.pack(fill="x", padx=20, pady=6)
            fname = Path(image_info["path"]).name
            fname_short = fname if len(fname) <= 36 else fname[:33] + "…"
            w, h = image_info["dimensions"]
            for line in [
                f"File:  {fname_short}",
                f"Size:  {w} × {h}   •   {image_info['size_mb']:.1f} MB",
                f"Fmt:   {image_info.get('format', 'Unknown')}",
            ]:
                tk.Label(df, text=line, font=self._fm,
                         bg=C["bg2"], fg=C["muted"], anchor="w").pack(fill="x")

            # Buttons
            bf = tk.Frame(dlg, bg=C["bg"])
            bf.pack(pady=14)
            confirmed = {"v": False}

            def on_ok():
                confirmed["v"] = True
                dlg.destroy()

            def on_no():
                confirmed["v"] = False
                dlg.destroy()

            tk.Button(bf, text="Analyze", font=self._fbm,
                      bg=C["purple"], fg="white",
                      activebackground=C["purple_text"], activeforeground="white",
                      bd=0, relief="flat", cursor="hand2",
                      command=on_ok, padx=20, pady=7).pack(side="left", padx=8)

            tk.Button(bf, text="Cancel", font=self._fbm,
                      bg=C["bg"], fg=C["text"],
                      activebackground=C["bg2"], activeforeground=C["text"],
                      bd=1, relief="solid", highlightbackground=C["border"],
                      cursor="hand2", command=on_no,
                      padx=20, pady=6).pack(side="left", padx=8)

            dlg.protocol("WM_DELETE_WINDOW", on_no)
            dlg.grab_set()
            dlg.wait_window()

            self._file_confirmed = confirmed["v"]
            self._confirm_event.set()

        if self._root and not self.cancelled:
            self._root.after(0, _do)

    # ── public API  (camera tool jaisa — set_step / log / finish / error) ─────

    def set_step(self, idx: int, state: str = "active", detail: str = ""):
        if not self._root or self.cancelled:
            return

        style_map = {
            "done":   (C["green_bg"],  C["green_text"], C["green"]),
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
# TRANSLATION  (camera tool se same logic — aiohttp + Google)
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
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            url    = "https://translate.googleapis.com/translate_a/single"
            params = {"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": text}
            async with s.get(url, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                    t = "".join(p[0] for p in data[0] if p[0])
                    if t:
                        return t
    except Exception:
        pass
    return text


# ─────────────────────────────────────────────
# IMAGE FILE HANDLER
# ─────────────────────────────────────────────

class ImageFileHandler:
    def __init__(self, config: Optional[ImageConfig] = None):
        self.config = config or ImageConfig()

    def validate(self, file_path: str) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            return {"valid": False, "error": "File does not exist"}

        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if size_mb > self.config.max_size_mb:
            return {"valid": False, "error": f"Too large ({size_mb:.1f} MB). Max: {self.config.max_size_mb} MB"}

        ext = Path(file_path).suffix.lower()
        if ext not in self.config.supported_formats:
            return {"valid": False, "error": f"Unsupported format: {ext}"}

        try:
            with Image.open(file_path) as img:
                img.verify()
            with Image.open(file_path) as img:
                w, h = img.size
                fmt  = img.format
            return {"valid": True, "path": file_path, "size_mb": size_mb,
                    "dimensions": (w, h), "format": fmt}
        except Exception as e:
            return {"valid": False, "error": f"Invalid image: {e}"}

    def read_as_bytes(self, file_path: str) -> Optional[bytes]:
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            if len(data) > self.config.compress_threshold_mb * 1024 * 1024:
                data = self._compress(data)
            return data
        except Exception:
            return None

    def _compress(self, data: bytes) -> bytes:
        try:
            img = Image.open(io.BytesIO(data))
            if img.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                mask = img.split()[-1] if img.mode in ("RGBA", "LA") else None
                if img.mode == "P":
                    img = img.convert("RGBA")
                    mask = img.split()[-1]
                bg.paste(img, mask=mask)
                img = bg
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=self.config.jpeg_quality, optimize=True)
            return out.getvalue()
        except Exception:
            return data

    def get_mime_type(self, file_path: str) -> str:
        mt, _ = mimetypes.guess_type(file_path)
        return mt or "image/jpeg"


# ─────────────────────────────────────────────
# ANALYZER  (camera tool ka OllamaVisionAnalyzer jaisa)
# ─────────────────────────────────────────────

class OllamaImageAnalyzer:
    def __init__(
        self,
        ollama_config: Optional[OllamaConfig] = None,
        image_config:  Optional[ImageConfig]  = None,
    ):
        self.cfg     = ollama_config or OllamaConfig()
        self.handler = ImageFileHandler(image_config)
        self.client  = ollama.Client(host=self.cfg.host)

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
        ui   = ImageAnalysisUI(query=query, model=self.cfg.model)
        loop = asyncio.get_event_loop()

        try:
            # Step 0 — Ollama check
            ui.set_step(0, "active", "pinging...")
            ui.log("Checking Ollama server...", "active")

            if not self.is_running():
                ui.set_step(0, "error", "not found")
                ui.log(f"Cannot reach {self.cfg.host}", "err")
                ui.error("Ollama not running")
                return (
                    f"Ollama not running.\n"
                    f"Start: ollama serve\n"
                    f"Pull:  ollama pull {self.cfg.model}"
                )

            models = self.list_models()
            ui.set_step(0, "done", "ok")
            ui.log(f"Ollama ready — {len(models)} model(s)", "ok")

            # Step 1 — File select
            ui.set_step(1, "active", "waiting...")
            ui.log("Opening file dialog...", "active")

            ui._file_event.clear()
            ui.open_file_dialog()
            await loop.run_in_executor(None, ui._file_event.wait)

            if ui.cancelled or not ui._selected_file:
                ui.set_step(1, "error", "cancelled")
                return "File selection cancelled."

            fname = Path(ui._selected_file).name
            ui.log(f"Selected: {fname}", "ok")

            # Step 2 — Validate + confirm dialog
            ui.set_step(2, "active", "checking...")
            ui.log("Validating image file...", "active")

            info = await loop.run_in_executor(
                None, self.handler.validate, ui._selected_file
            )

            if not info["valid"]:
                ui.set_step(2, "error", "invalid")
                ui.log(info["error"], "err")
                ui.error(info["error"])
                return f"Invalid image: {info['error']}"

            w, h = info["dimensions"]
            ui.log(f"Valid — {w}×{h}  {info['size_mb']:.1f} MB", "ok")

            # Preview + confirm dialog dikhao
            ui._confirm_event.clear()
            ui.show_confirm_dialog(info)
            await loop.run_in_executor(None, ui._confirm_event.wait)

            if ui.cancelled or not ui._file_confirmed:
                ui.set_step(2, "error", "cancelled")
                return "Analysis cancelled by user."

            ui.set_step(2, "done", f"{w}×{h}")

            # Step 3 — Read file
            ui.set_step(3, "active", "reading...")
            ui.log("Reading image bytes...", "active")

            image_bytes = await loop.run_in_executor(
                None, self.handler.read_as_bytes, ui._selected_file
            )

            if ui.cancelled:
                return "Cancelled."

            if not image_bytes:
                ui.set_step(3, "error", "failed")
                ui.error("Could not read image file")
                return "Failed to read image file."

            kb = len(image_bytes) // 1024
            ui.set_step(3, "done", f"{kb} KB")
            ui.log(f"Read {kb} KB", "ok")

            # Step 4 — Translate query
            ui.set_step(4, "active", "checking...")
            ui.log("Checking query language...", "active")

            if not is_english(query):
                ui.log("Non-English detected — translating...", "active")
                query = await translate_to_english(query) or query
                ui.log(f"Translated: {query[:50]}", "ok")
            else:
                ui.log("English query — no translation needed", "dim")

            ui.set_step(4, "done", "ready")

            # Step 5 — Ollama inference
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

            file_info = f"\n\n[File: {fname}  |  {w}×{h}  |  {info['size_mb']:.1f} MB]"
            ui.finish(result_preview=result)

            return result + file_info

        except Exception as e:
            ui.error(str(e))
            return f"Unexpected error: {e}"


# ─────────────────────────────────────────────
# SINGLETON + LIVEKIT TOOLS
# ─────────────────────────────────────────────

_analyzer = OllamaImageAnalyzer()


@function_tool()
async def analyze_local_image(query: str = "What do you see in this image?") -> str:
    """
    File dialog se local image select karo aur local Ollama vision model se analyze karo.
    Real-time progress window dikhata hai pipeline ke dauran.

    Args:
        query: Image ke baare mein kya jaanna hai (kisi bhi language mein).

    Returns:
        Local vision model se text description ya answer.
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
    Active Ollama vision model runtime pe switch karo.

    Args:
        model_name: e.g. 'llava', 'moondream', 'qwen3.5:2b', 'bakllava'
    """
    available = _analyzer.list_models()
    if model_name not in available:
        return (
            f"'{model_name}' locally nahi mila.\n"
            f"Pull karo: ollama pull {model_name}\n"
            f"Available: {', '.join(available) or 'none'}"
        )
    _analyzer.cfg.model = model_name
    return f"Switched to: {model_name}"


@function_tool()
async def identify_objects_in_image() -> str:
    """Image select karo aur saare objects, log aur scenes identify karo."""
    return await _analyzer.run_with_ui(
        "Identify all objects, people, animals, buildings, vehicles, and scenes "
        "in this image. List them clearly with descriptions."
    )


@function_tool()
async def extract_text_from_image() -> str:
    """Image select karo aur usme se saara readable text extract karo."""
    return await _analyzer.run_with_ui(
        "Extract and read ALL text visible in this image. "
        "Preserve exact wording and layout as much as possible."
    )


@function_tool()
async def describe_image_for_accessibility() -> str:
    """Visually impaired users ke liye image ki detailed description do."""
    return await _analyzer.run_with_ui(
        "Provide a detailed description of this image suitable for someone who cannot see it. "
        "Describe the scene, colors, objects, people, actions, emotions, and overall context."
    )