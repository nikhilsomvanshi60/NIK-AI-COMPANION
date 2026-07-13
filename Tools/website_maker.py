import os
import json
import re
import asyncio
from pathlib import Path
import aiohttp
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from livekit.agents import function_tool


import tkinter as tk
from tkinter import ttk
import threading

class WebsiteGeneratorUI:
    def __init__(self, total_files: int, project_name: str):
        self.cancelled = False
        self.total = total_files
        self.current = 0
        self._root = None
        self._done_event = threading.Event()
        
        # UI ko alag thread mein chalao (asyncio ke saath conflict na ho)
        self._thread = threading.Thread(target=self._build_ui, args=(project_name,), daemon=True)
        self._thread.start()
        # Window ready hone ka wait karo
        self._done_event.wait(timeout=3)

    def _build_ui(self, project_name: str):
        self._root = tk.Tk()
        self._root.title("Website Generator")
        self._root.geometry("480x320")
        self._root.resizable(False, False)
        self._root.configure(bg="#ffffff")
        self._root.attributes("-topmost", True)
        
        # Center on screen
        self._root.update_idletasks()
        x = (self._root.winfo_screenwidth() - 480) // 2
        y = (self._root.winfo_screenheight() - 320) // 2
        self._root.geometry(f"480x320+{x}+{y}")

        pad = {"padx": 28, "pady": 0}

        tk.Label(self._root, text="Generating Website...", font=("Helvetica", 14, "bold"),
                 bg="#ffffff", fg="#1a1a1a").pack(anchor="w", padx=28, pady=(22, 2))

        self._subtitle = tk.Label(self._root, text=f"{project_name} — Planning files",
                                   font=("Helvetica", 11), bg="#ffffff", fg="#666666")
        self._subtitle.pack(anchor="w", **pad)

        # Progress bar
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Custom.Horizontal.TProgressbar",
                        troughcolor="#f0f0f0", background="#534AB7",
                        thickness=8, borderwidth=0)
        
        self._progress = ttk.Progressbar(self._root, style="Custom.Horizontal.TProgressbar",
                                          orient="horizontal", length=424, mode="determinate",
                                          maximum=self.total + 1)
        self._progress.pack(padx=28, pady=(16, 6))

        meta_frame = tk.Frame(self._root, bg="#ffffff")
        meta_frame.pack(fill="x", padx=28)
        self._step_lbl = tk.Label(meta_frame, text="Step 0 of 0", font=("Helvetica", 10),
                                   bg="#ffffff", fg="#888888")
        self._step_lbl.pack(side="left")
        self._pct_lbl = tk.Label(meta_frame, text="0%", font=("Helvetica", 10),
                                  bg="#ffffff", fg="#888888")
        self._pct_lbl.pack(side="right")

        # Current file label
        self._file_lbl = tk.Label(self._root, text="Analyzing requirements...",
                                   font=("Courier", 10), bg="#f5f5f5", fg="#333333",
                                   anchor="w", width=52, relief="flat", padx=10, pady=6)
        self._file_lbl.pack(padx=28, pady=(12, 10), fill="x")

        # Log box
        self._log = tk.Text(self._root, height=4, font=("Courier", 9),
                             bg="#fafafa", fg="#555555", bd=0, relief="flat",
                             state="disabled", wrap="none")
        self._log.pack(padx=28, fill="x")
        self._log.tag_config("done", foreground="#1D9E75")
        self._log.tag_config("writing", foreground="#534AB7")

        # Cancel button
        cancel_btn = tk.Button(self._root, text="Cancel", font=("Helvetica", 11),
                                bg="#ffffff", fg="#333333", bd=1, relief="solid",
                                activebackground="#f5f5f5", cursor="hand2",
                                command=self._on_cancel, width=20, pady=6)
        cancel_btn.pack(pady=(12, 0))

        self._done_event.set()
        self._root.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._root.mainloop()

    def _on_cancel(self):
        self.cancelled = True
        if self._root:
            self._subtitle.config(text="Cancelled by user")
            self._file_lbl.config(text="Generation stopped.")
            self._root.after(1200, self._root.destroy)

    def _log_add(self, msg: str, tag: str = ""):
        self._log.config(state="normal")
        self._log.insert("1.0", msg + "\n", tag)
        self._log.config(state="disabled")

    def update(self, current_file: str, done_file: str = None):
        """Call karo har file ke write hone se pehle."""
        if not self._root or self.cancelled:
            return
        self.current += 1
        pct = int((self.current / (self.total + 1)) * 100)

        def _update():
            if done_file:
                self._log_add(f"Done: {done_file}", "done")
            self._log_add(f"Writing: {current_file}", "writing")
            self._progress["value"] = self.current
            self._pct_lbl.config(text=f"{pct}%")
            self._step_lbl.config(text=f"Step {self.current} of {self.total}")
            self._file_lbl.config(text=f"Writing: {current_file}")
            self._subtitle.config(text=f"File {self.current} of {self.total}")

        self._root.after(0, _update)

    def finish(self):
        """Sab kaam hone ke baad call karo — UI band ho jaayegi."""
        if not self._root:
            return
        def _finish():
            self._progress["value"] = self.total + 1
            self._pct_lbl.config(text="100%")
            self._file_lbl.config(text="Website generated successfully!")
            self._subtitle.config(text="Complete!")
            self._root.after(1200, self._root.destroy)
        self._root.after(0, _finish)

@function_tool()
async def create_website(
    project_name: str,
    description: str,
    pages: str,
    style: str = "modern",
    features: str = "none",
) -> str:
    """
    Creates a complete, fully-designed website project using Groq AI.
    Automatically decides which files are needed, writes all code,
    and saves everything in a new folder inside the current working directory.

    Args:
        project_name (str): Name of the project / folder to create.
        description  (str): What the website does (1-2 sentences).
        pages        (str): Comma-separated page names e.g. "Home, About, Contact".
        style        (str): Visual style — modern / dark / minimal / colorful / corporate.
        features     (str): Comma-separated extras — login / gallery / blog / dashboard / none.

    Returns:
        str: Success message with project path, or error details.
    """

    # ── Config ────────────────────────────────────────────────────────────────
    GROQ_API_URL  = "https://api.groq.com/openai/v1/chat/completions"
    GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
    MODEL         = "openai/gpt-oss-120b"

    # Rate limit: 20 req/min → 1 request har 3 seconds mein safe rehta hai
    DELAY_BETWEEN_REQUESTS = 3.5   # seconds
    MAX_RETRIES            = 3
    RETRY_WAIT             = 65    # seconds — agar 429 aaye toh 1 min baad retry

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }

    req = {
        "project_name": project_name,
        "description":  description,
        "pages":        [p.strip() for p in pages.split(",") if p.strip()],
        "style":        style,
        "features":     [f.strip().lower() for f in features.split(",") if f.strip()],
    }

    # ── Helper: Groq API call with retry on 429 ───────────────────────────────
    async def groq(system: str, user: str, max_tokens: int = 4096) -> str:
        payload = {
            "model":       MODEL,
            "temperature": 0.3,
            "max_tokens":  max_tokens,
            "top_p":       0.9,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        }

        for attempt in range(1, MAX_RETRIES + 1):
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    GROQ_API_URL, headers=headers, json=payload, timeout=120
                ) as res:
                    data = await res.json()

                    # Rate limit hit → wait aur retry
                    if res.status == 429:
                        wait = RETRY_WAIT
                        # Groq headers mein exact wait time bhi deta hai kabhi kabhi
                        retry_after = res.headers.get("retry-after")
                        if retry_after:
                            wait = int(retry_after) + 2
                        logger.warning(
                            f"⚠️  Rate limit hit (attempt {attempt}/{MAX_RETRIES}). "
                            f"{wait}s baad retry karunga…"
                        )
                        await asyncio.sleep(wait)
                        continue

                    if res.status != 200:
                        raise RuntimeError(f"Groq API error {res.status}: {data}")

                    raw = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
                    # strip markdown fences if model added them
                    if raw.startswith("```"):
                        lines = raw.split("\n")
                        raw = "\n".join(lines[1:-1])
                    return raw

        raise RuntimeError(f"Max retries ({MAX_RETRIES}) exhausted — rate limit nahi hata.")

    try:
        # ── STEP 1: Groq decides which files are needed ────────────────────────
        logger.info(f"📐 Planning file structure for '{project_name}'…")

        manifest_raw = await groq(
            system=(
                "You are an expert web architect. "
                "Return ONLY a valid JSON array — no prose, no markdown fences, nothing else."
            ),
            user=f"""
A user wants a complete website. Plan ALL required files.

Project requirements:
{json.dumps(req, indent=2)}

Return a JSON array. Each item must have:
  "path"        — relative file path (e.g. "index.html", "css/style.css", "js/main.js")
  "description" — one-line purpose of this file
  "depends_on"  — list of paths this file imports/links (empty list if none)

Include every file needed for a fully working project.
""",
            max_tokens=2048,
        )

        try:
            manifest = json.loads(manifest_raw)
        except json.JSONDecodeError:
            m = re.search(r"\[.*\]", manifest_raw, re.DOTALL)
            manifest = json.loads(m.group()) if m else []

        if not manifest:
            return "❌ Groq ne file structure nahi diya. Dobara try karo."

        logger.info(f"✅ {len(manifest)} files planned: {[f['path'] for f in manifest]}")

        # ── STEP 2: Groq writes each file — ek ek karke, delay ke saath ────────
        file_contents: dict[str, str] = {}

        ui = WebsiteGeneratorUI(total_files=len(manifest), project_name=project_name)

        # STEP 2 loop mein — har file se pehle UI update karo:
        for i, file_info in enumerate(manifest, 1):
            path = file_info["path"]
            
            # Cancel check
            if ui.cancelled:
                return "❌ User ne cancel kar diya."

            prev_file = manifest[i-2]["path"] if i > 1 else None
            ui.update(current_file=path, done_file=prev_file)  # <-- yeh add karo
            
            logger.info(f"✍️  [{i}/{len(manifest)}] Writing: {path}")


            try:
                code = await groq(
                    system=(
                        "You are an elite frontend developer. "
                        "Output ONLY raw file content — no explanations, no markdown fences, no preamble."
                    ),
                    user=f"""
Write the COMPLETE, production-ready code for this file.

Project:
{json.dumps(req, indent=2)}

All files in this project (link correctly):
{json.dumps([f["path"] for f in manifest], indent=2)}

File to write:
  path        : {path}
  description : {file_info['description']}
  depends_on  : {json.dumps(file_info.get('depends_on', []))}

Rules:
- COMPLETE code only — no placeholders, no TODO comments.
- Design style: {style}
- Visually stunning, NOT generic AI templates.
  • Unique Google Fonts (not Inter / Roboto / Arial).
  • CSS custom properties with a bold, memorable colour palette.
  • Smooth animations, hover effects, micro-interactions.
  • Fully responsive from 320px to 2000px.
- JS: ES2022+, classes, async/await. No jQuery.
- All internal links must match the file paths listed above exactly.
""",
                    max_tokens=4096,
                )
                file_contents[path] = code
                logger.info(f"✅ Done: {path}")

            except Exception as e:
                logger.warning(f"⚠️ Failed to generate {path}: {e}")
                file_contents[path] = f"<!-- Error generating {path}: {e} -->"

            # ⏳ Rate limit ke liye delay — last file ke baad delay nahi
            if i < len(manifest):
                logger.info(f"⏳ {DELAY_BETWEEN_REQUESTS}s wait (rate limit safe)…")
                await asyncio.sleep(DELAY_BETWEEN_REQUESTS)

        # ── STEP 3: Save all files to current directory ────────────────────────
        base = Path.cwd() / project_name.replace(" ", "_")
        base.mkdir(exist_ok=True)

        for file_info in manifest:
            full_path = base / file_info["path"]
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(file_contents.get(file_info["path"], ""), encoding="utf-8")

        # README
        readme = f"""# {project_name}

{description}

## Pages
{chr(10).join(f'- {p}' for p in req['pages'])}

## Style
{style}

## Run
Open `index.html` in your browser.

---
*Generated by AI Website Generator using Groq ({MODEL}).*
"""
        (base / "README.md").write_text(readme, encoding="utf-8")

        total = len(manifest) + 1
        logger.info(f"🎉 Project saved at: {base.absolute()}")

        ui.finish()

        return (
            f"✅ Website '{project_name}' ban gaya!\n"
            f"📁 Location: {base.absolute()}\n"
            f"📄 Total files: {total}\n"
            f"👉 Open karo: {base.absolute() / 'index.html'}"
        )

    except Exception as e:
        logger.error(f"❌ Website generation failed: {e}")
        return f"❌ Failed: {str(e)}"