import os
import re
import time
import requests
from datetime import datetime

import pdfplumber
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_CENTER

from livekit.agents import function_tool

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False

GROQ_API_KEY = ""
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "openai/gpt-oss-120b"

# palette
BG      = "#0D1117"
BG2     = "#161B22"
BG3     = "#21262D"
ACCENT  = "#58A6FF"
GREEN   = "#3FB950"
RED     = "#F85149"
YELLOW  = "#D29922"
TEXT    = "#E6EDF3"
TEXT2   = "#8B949E"
TEXT3   = "#484F58"
BORDER  = "#30363D"
BORDER2 = "#21262D"


# ══════════════════════════════════════════════════════════════════════════════
#  PREMIUM DARK UI  (Windows-safe — zero tuple paddings)
# ══════════════════════════════════════════════════════════════════════════════

class SolverUI:

    STAGES = [
        ("📂", "Open PDF"),
        ("🔍", "Extract"),
        ("🧠", "Analyze"),
        ("⚡", "AI Solve"),
        ("📄", "Build PDF"),
        ("✅", "Done"),
    ]

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("PDF Question Solver")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self._closed   = False
        self._pct      = 0.0
        self._track_w  = 640
        self._spinning = True
        self._spin_idx = 0
        self._spin_ch  = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        # center window
        self.root.update_idletasks()
        w, h = 700, 530
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()

    # ── build UI ──────────────────────────────────────────────────────────────

    def _build(self):

        # title bar
        bar = tk.Frame(self.root, bg=BG2, height=58)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        # macOS dots
        dot_frame = tk.Frame(bar, bg=BG2)
        dot_frame.place(x=14, rely=0.5, anchor="w")
        for col in ("#FF5F57", "#FFBD2E", "#28C840"):
            cv = tk.Canvas(dot_frame, width=12, height=12, bg=BG2, highlightthickness=0)
            cv.pack(side="left", padx=3)
            cv.create_oval(1, 1, 11, 11, fill=col, outline="")

        tk.Label(bar, text="PDF Question Solver",
                 font=("Segoe UI", 13, "bold"), fg=ACCENT, bg=BG2
                 ).place(relx=0.5, rely=0.35, anchor="center")
        tk.Label(bar, text=f"Groq AI  ·  {GROQ_MODEL}",
                 font=("Segoe UI", 8), fg=TEXT3, bg=BG2
                 ).place(relx=0.5, rely=0.72, anchor="center")

        # ── stage row ─────────────────────────────────────────────────────
        sf = tk.Frame(self.root, bg=BG)
        sf.pack(fill="x", padx=22, pady=14)

        row = tk.Frame(sf, bg=BG)
        row.pack(fill="x")

        self._s_circles = []   # (canvas, oval_id, text_id, icon_str)
        self._s_labels  = []

        for i, (icon, label) in enumerate(self.STAGES):
            cell = tk.Frame(row, bg=BG)
            cell.pack(side="left", expand=True, fill="x")

            # connector left half
            if i > 0:
                lc = tk.Frame(cell, bg=BORDER2, height=2)
                lc.place(relx=0, rely=0.27, relwidth=0.45, anchor="w")

            # connector right half
            if i < len(self.STAGES) - 1:
                rc = tk.Frame(cell, bg=BORDER2, height=2)
                rc.place(relx=1.0, rely=0.27, relwidth=0.45, anchor="e")

            cv = tk.Canvas(cell, width=42, height=42, bg=BG, highlightthickness=0)
            cv.pack(anchor="center")
            oid = cv.create_oval(2, 2, 40, 40, fill=BG3, outline=BORDER, width=2)
            tid = cv.create_text(21, 21, text=icon, font=("Segoe UI", 13), fill=TEXT3)
            self._s_circles.append((cv, oid, tid, icon))

            lbl = tk.Label(cell, text=label, font=("Segoe UI", 8), fg=TEXT3, bg=BG)
            lbl.pack(anchor="center")
            self._s_labels.append(lbl)

        # ── progress bar ──────────────────────────────────────────────────
        pb_outer = tk.Frame(self.root, bg=BG)
        pb_outer.pack(fill="x", padx=22)

        self._track = tk.Canvas(pb_outer, height=10, bg=BG3,
                                highlightthickness=0, relief="flat")
        self._track.pack(fill="x")
        self._fill_id = self._track.create_rectangle(0, 0, 0, 10,
                                                      fill=ACCENT, outline="")
        self._track.bind("<Configure>", lambda e: self._resize_fill(e.width))

        pct_row = tk.Frame(pb_outer, bg=BG)
        pct_row.pack(fill="x")

        self._pct_lbl = tk.Label(pct_row, text="0%",
                                  font=("Segoe UI", 10, "bold"), fg=ACCENT, bg=BG)
        self._pct_lbl.pack(side="left")

        self._eta_lbl = tk.Label(pct_row, text="Initializing...",
                                  font=("Segoe UI", 9), fg=TEXT2, bg=BG)
        self._eta_lbl.pack(side="right")

        # ── status card ───────────────────────────────────────────────────
        card_outer = tk.Frame(self.root, bg=BG)
        card_outer.pack(fill="x", padx=22, pady=10)

        card = tk.Frame(card_outer, bg=BG2, padx=12, pady=10,
                        highlightthickness=1, highlightbackground=BORDER2)
        card.pack(fill="x")

        icon_box = tk.Frame(card, bg="#0D2540", width=46, height=46,
                            highlightthickness=1, highlightbackground="#1D3A5C")
        icon_box.pack(side="left")
        icon_box.pack_propagate(False)
        self._c_icon = tk.Label(icon_box, text="⏳", font=("Segoe UI", 20),
                                 bg="#0D2540", fg=ACCENT)
        self._c_icon.place(relx=0.5, rely=0.5, anchor="center")

        txt_frame = tk.Frame(card, bg=BG2)
        txt_frame.pack(side="left", fill="x", expand=True, padx=12)

        self._c_title = tk.Label(txt_frame, text="Initializing...",
                                  font=("Segoe UI", 12, "bold"),
                                  fg=TEXT, bg=BG2, anchor="w")
        self._c_title.pack(fill="x")

        self._c_sub = tk.Label(txt_frame, text="Please wait...",
                                font=("Segoe UI", 9), fg=TEXT2, bg=BG2, anchor="w")
        self._c_sub.pack(fill="x")

        # ── file chip ─────────────────────────────────────────────────────
        chip_outer = tk.Frame(self.root, bg=BG)
        chip_outer.pack(fill="x", padx=22)

        chip = tk.Frame(chip_outer, bg=BG2,
                        highlightthickness=1, highlightbackground=BORDER)
        chip.pack(side="left")

        tk.Label(chip, text="📄", font=("Segoe UI", 10), bg=BG2, fg=ACCENT
                 ).pack(side="left", padx=8, pady=5)

        self._chip_name = tk.Label(chip, text="No file selected",
                                    font=("Segoe UI", 9), bg=BG2, fg=TEXT)
        self._chip_name.pack(side="left", pady=5)

        self._chip_pages = tk.Label(chip, text="",
                                     font=("Segoe UI", 9), bg=BG2, fg=TEXT2)
        self._chip_pages.pack(side="left", padx=8, pady=5)

        # ── log console ───────────────────────────────────────────────────
        log_outer = tk.Frame(self.root, bg=BG)
        log_outer.pack(fill="both", expand=True, padx=22, pady=10)

        hdr = tk.Frame(log_outer, bg=BG)
        hdr.pack(fill="x")

        tk.Label(hdr, text="Console", font=("Segoe UI", 8, "bold"),
                 fg=TEXT3, bg=BG).pack(side="left")

        self._spin_lbl = tk.Label(hdr, text="", font=("Segoe UI", 8),
                                   fg=ACCENT, bg=BG)
        self._spin_lbl.pack(side="right")

        log_border = tk.Frame(log_outer, bg="#090C10",
                              highlightthickness=1, highlightbackground=BORDER2)
        log_border.pack(fill="both", expand=True, pady=4)

        sb = tk.Scrollbar(log_border, bg=BG3, troughcolor="#090C10",
                          activebackground=BORDER, width=8)
        sb.pack(side="right", fill="y")

        self._log = tk.Text(log_border, bg="#090C10", fg=TEXT3,
                             font=("Courier New", 9), height=7,
                             relief="flat", state="disabled", wrap="word",
                             insertbackground=TEXT, padx=10, pady=8,
                             selectbackground=BG3,
                             yscrollcommand=sb.set)
        self._log.pack(fill="both", expand=True)
        sb.config(command=self._log.yview)

        self._log.tag_config("ok",   foreground=GREEN)
        self._log.tag_config("info", foreground=ACCENT)
        self._log.tag_config("warn", foreground=YELLOW)
        self._log.tag_config("err",  foreground=RED)
        self._log.tag_config("dim",  foreground=TEXT3)

        self._animate()

    # ── internals ─────────────────────────────────────────────────────────────

    def _resize_fill(self, w):
        self._track_w = w
        px = int(w * self._pct / 100)
        col = GREEN if self._pct >= 100 else ACCENT
        self._track.itemconfig(self._fill_id, fill=col)
        self._track.coords(self._fill_id, 0, 0, px, 10)

    def _animate(self):
        if self._closed or not self._spinning:
            return
        self._spin_idx = (self._spin_idx + 1) % len(self._spin_ch)
        try:
            self._spin_lbl.config(text=self._spin_ch[self._spin_idx])
            self.root.after(80, self._animate)
        except Exception:
            pass

    def _on_close(self):
        self._closed   = True
        self._spinning = False
        try:
            self.root.destroy()
        except Exception:
            pass

    def _upd(self):
        if not self._closed:
            try:
                self.root.update()
            except Exception:
                pass

    # ── public ────────────────────────────────────────────────────────────────

    def log(self, msg: str, kind: str = "info"):
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}")
        if self._closed:
            return
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            self._log.configure(state="normal")
            self._log.insert("end", f"[{ts}] {msg}\n", kind)
            self._log.see("end")
            self._log.configure(state="disabled")
            self._upd()
        except Exception:
            pass

    def set_stage(self, idx: int):
        if self._closed:
            return
        try:
            for i, (cv, oid, tid, icon) in enumerate(self._s_circles):
                if i < idx:
                    cv.itemconfig(oid, fill="#122219", outline=GREEN, width=2)
                    cv.itemconfig(tid, text="✓", fill=GREEN)
                    self._s_labels[i].config(fg=GREEN)
                elif i == idx:
                    cv.itemconfig(oid, fill="#0D2540", outline=ACCENT, width=2)
                    cv.itemconfig(tid, text=icon, fill=ACCENT)
                    self._s_labels[i].config(fg=ACCENT)
                else:
                    cv.itemconfig(oid, fill=BG3, outline=BORDER, width=2)
                    cv.itemconfig(tid, text=icon, fill=TEXT3)
                    self._s_labels[i].config(fg=TEXT3)
            self._upd()
        except Exception:
            pass

    def set_progress(self, pct: float, title: str = None, sub: str = None,
                     icon: str = None, eta: str = None):
        if self._closed:
            return
        try:
            self._pct = min(100.0, pct)
            col = GREEN if self._pct >= 100 else ACCENT
            self._pct_lbl.config(text=f"{int(self._pct)}%", fg=col)
            self._resize_fill(self._track_w)
            if eta:   self._eta_lbl.config(text=eta)
            if title: self._c_title.config(text=title)
            if sub:   self._c_sub.config(text=sub)
            if icon:  self._c_icon.config(text=icon)
            self._upd()
        except Exception:
            pass

    def set_file(self, name: str, pages: int = 0):
        if self._closed:
            return
        try:
            self._chip_name.config(text=name)
            if pages:
                self._chip_pages.config(text=f"· {pages} pages")
            self._upd()
        except Exception:
            pass

    def show_done(self, output_path: str):
        if self._closed:
            return
        try:
            self._spinning = False
            self._spin_lbl.config(text="✓", fg=GREEN)
            self.set_progress(100,
                title="All done!",
                sub=f"Saved → {os.path.basename(output_path)}",
                icon="🎉",
                eta="Complete")
            self._c_title.config(fg=GREEN)
            self.log(f"Output: {output_path}", "ok")
            self._upd()
            time.sleep(2.5)
            self.root.destroy()
        except Exception:
            pass

    def show_error(self, msg: str):
        if self._closed:
            return
        try:
            self._spinning = False
            self.set_progress(self._pct, "Error occurred", msg[:80], "❌", "Failed")
            self._c_title.config(fg=RED)
            self.log(f"ERROR: {msg}", "err")
            self._upd()
            messagebox.showerror("Error", msg)
            self.root.destroy()
        except Exception:
            pass

    def ask_file(self) -> str:
        try:
            self.root.withdraw()
            path = filedialog.askopenfilename(
                title="Select PDF to solve",
                filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
            )
            self.root.deiconify()
            return path or ""
        except Exception:
            return ""


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def extract_pdf_text(pdf_path: str, ui) -> tuple:
    print(f"📖 Reading: {pdf_path}")
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        ui.set_file(os.path.basename(pdf_path), total)
        ui.log(f"PDF opened — {total} pages", "ok")
        for i, page in enumerate(pdf.pages):
            txt = page.extract_text() or ""
            full_text += f"\n--- PAGE {i+1} ---\n{txt}\n"
            pct = 10 + (i / total) * 22
            ui.set_progress(pct,
                title=f"Extracting page {i+1} / {total}",
                sub=f"{len(full_text):,} characters extracted",
                icon="🔍",
                eta=f"Page {i+1}/{total}")
            ui.log(f"Page {i+1}/{total} — {len(txt):,} chars", "dim")
    ui.log(f"Extraction complete — {len(full_text):,} chars total", "ok")
    return full_text, total


def call_groq(system_prompt: str, user_prompt: str) -> str:
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}",
               "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 8000,
    }
    resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    result = resp.json()["choices"][0]["message"]["content"].strip()
    print(f"✅ Groq responded — {len(result)} chars")
    return result


def identify_questions(full_text: str, user_query: str, ui) -> str:
    ui.log("Calling Groq — identifying questions...", "info")
    system = (
        "You are an expert academic document analyzer. "
        "Extract EVERY question from the document matching the user's query. "
        "Return them as a numbered list. Include sub-parts. Preserve exact text."
    )
    user = (f"USER QUERY: {user_query}\n\n"
            f"DOCUMENT TEXT:\n{full_text[:12000]}\n\n"
            "List ALL matching questions numbered clearly.")
    result = call_groq(system, user)
    ui.log(f"Questions found — {len([l for l in result.splitlines() if l.strip()])} lines", "ok")
    return result


def solve_questions(questions_list: str, full_text: str, user_query: str, ui) -> str:
    ui.log("Calling Groq — generating solutions...", "info")
    system = (
        "You are an expert teacher. Solve each question with clear step-by-step explanations. "
        "For code questions: provide complete working code with comments. "
        "For theory: provide detailed explanations. Number each answer clearly."
    )
    user = (f"REQUEST: {user_query}\n\n"
            f"CONTEXT:\n{full_text[:5000]}\n\n"
            f"QUESTIONS:\n{questions_list}\n\n"
            "Solve EVERY question with complete detailed answers.")
    result = call_groq(system, user)
    ui.log(f"Solutions generated — {len(result.splitlines())} lines", "ok")
    return result


def build_solution_pdf(solutions_text: str, original_pdf: str,
                       user_query: str, output_path: str, ui):
    ui.log(f"Building PDF → {os.path.basename(output_path)}", "info")

    doc = SimpleDocTemplate(output_path, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    s_title = ParagraphStyle("T", parent=styles["Title"], fontSize=20,
        textColor=colors.HexColor("#1A56DB"), spaceAfter=4,
        alignment=TA_CENTER, fontName="Helvetica-Bold")
    s_sub   = ParagraphStyle("S", parent=styles["Normal"], fontSize=9,
        textColor=colors.HexColor("#6B7280"), spaceAfter=2, alignment=TA_CENTER)
    s_sec   = ParagraphStyle("H", parent=styles["Heading1"], fontSize=13,
        textColor=colors.HexColor("#1A56DB"), spaceBefore=14, spaceAfter=5,
        fontName="Helvetica-Bold")
    s_q     = ParagraphStyle("Q", parent=styles["Normal"], fontSize=11,
        textColor=colors.HexColor("#111827"), spaceBefore=10, spaceAfter=3,
        fontName="Helvetica-Bold")
    s_ans   = ParagraphStyle("A", parent=styles["Normal"], fontSize=10,
        textColor=colors.HexColor("#374151"), spaceBefore=3, spaceAfter=5,
        leading=16, leftIndent=10)
    s_code  = ParagraphStyle("C", parent=styles["Code"], fontSize=8,
        textColor=colors.HexColor("#1F2937"),
        backColor=colors.HexColor("#F3F4F6"),
        fontName="Courier", leading=13, leftIndent=8, spaceAfter=6)

    story = []
    now = datetime.now().strftime("%B %d, %Y  %H:%M")
    pdf_name = os.path.basename(original_pdf)

    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("Solution Document", s_title))
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width="100%", thickness=2,
        color=colors.HexColor("#1A56DB"), spaceAfter=5))
    story.append(Paragraph(f"Source: {pdf_name}", s_sub))
    story.append(Paragraph(f"Query: {user_query}", s_sub))
    story.append(Paragraph(f"Generated: {now}  |  Model: {GROQ_MODEL}", s_sub))
    story.append(HRFlowable(width="100%", thickness=1,
        color=colors.HexColor("#E5E7EB"), spaceBefore=8, spaceAfter=16))

    def safe(t):
        t = t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"\*(.+?)\*",     r"<i>\1</i>", t)
        return t

    q_re    = re.compile(r"^(?:Q\.?\s*\d+|Question\s*\d+|\d+\.\s+[A-Z])", re.IGNORECASE)
    h_re    = re.compile(r"^#+\s+(.+)$")
    in_code = False

    for raw in solutions_text.split("\n"):
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            s = line.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            story.append(Paragraph(
                f'<font name="Courier" size="8">{s or " "}</font>', s_code))
            continue
        if not line.strip():
            story.append(Spacer(1, 3)); continue
        hm = h_re.match(line)
        if hm:
            story.append(Paragraph(safe(hm.group(1)), s_sec)); continue
        if q_re.match(line):
            story.append(Paragraph(safe(line), s_q)); continue
        if line.strip().startswith(("- ", "• ", "* ")):
            story.append(Paragraph(f"  •  {safe(line.strip()[2:])}", s_ans)); continue
        story.append(Paragraph(safe(line), s_ans))

    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width="100%", thickness=1,
        color=colors.HexColor("#E5E7EB"), spaceAfter=4))
    story.append(Paragraph(
        f"Generated by PDF Question Solver  |  Groq AI ({GROQ_MODEL})  |  {now}", s_sub))

    doc.build(story)
    ui.log("PDF written successfully", "ok")


# ══════════════════════════════════════════════════════════════════════════════
#  FUNCTION TOOL
# ══════════════════════════════════════════════════════════════════════════════

@function_tool()
async def solve_pdf_questions(user_query: str) -> str:
    """
    Advanced PDF Question Solver with premium dark UI.

    Opens a file dialog, reads the selected PDF, extracts all matching
    questions, solves them using Groq AI, and saves a formatted solution PDF.

    Arguments:
        user_query: What to solve — e.g. "solve all practical questions",
                    "answer all coding exercises", "solve all MCQs"
    """
    print(f"🚀 solve_pdf_questions | query='{user_query}'")

    # ── fallback for headless / no tkinter ──
    class _HeadlessUI:
        def log(self, m, kind=""):      print(f"  [{kind.upper() or 'INFO'}] {m}")
        def set_stage(self, i):         pass
        def set_progress(self, p, **k): print(f"  [{int(p):3d}%] {k.get('title','')}")
        def set_file(self, n, p=0):     pass
        def show_done(self, p):         print(f"✅ Done → {p}")
        def show_error(self, m):        print(f"❌ {m}")
        def ask_file(self):             return input("PDF path: ").strip()

    ui = SolverUI() if TKINTER_AVAILABLE else _HeadlessUI()

    try:
        # 0 — select file
        ui.set_stage(0)
        ui.set_progress(2, "Select your PDF file", "Opening file dialog...", "📂", "Waiting...")
        ui.log("Opening file selection...", "info")

        pdf_path = ui.ask_file()
        if not pdf_path or not os.path.exists(pdf_path):
            ui.show_error("No PDF file selected.")
            return "❌ Koi PDF select nahi ki gayi."

        pdf_name = os.path.basename(pdf_path)
        ui.log(f"File selected: {pdf_name}", "ok")
        ui.set_progress(8, f"Loaded: {pdf_name}", "Starting...", "📂", "Ready")

        # 1 — extract
        ui.set_stage(1)
        ui.set_progress(10, "Extracting PDF content", "Reading all pages...", "🔍", "Extracting...")
        full_text, page_count = extract_pdf_text(pdf_path, ui)
        ui.set_progress(32, f"Extracted {page_count} pages",
                        f"{len(full_text):,} chars total", "🔍", "Extracted")

        # 2 — identify
        ui.set_stage(2)
        ui.set_progress(34, "Analyzing with AI", "Identifying questions...", "🧠", "Analyzing...")
        questions_list = identify_questions(full_text, user_query, ui)
        q_lines = len([l for l in questions_list.splitlines() if l.strip()])
        ui.set_progress(52, "Questions identified", f"{q_lines} lines found", "🧠", "Done")

        # 3 — solve
        ui.set_stage(3)
        ui.set_progress(54, "Solving with Groq AI", f"Model: {GROQ_MODEL}", "⚡", "Solving...")
        solutions = solve_questions(questions_list, full_text, user_query, ui)
        ui.set_progress(78, "Solutions ready",
                        f"{len(solutions.splitlines())} lines generated", "⚡", "Solved")

        # 4 — build pdf
        ui.set_stage(4)
        base = os.path.splitext(pdf_path)[0]
        output_path = f"{base}_SOLUTIONS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        ui.set_progress(80, "Building solution PDF", "Formatting...", "📄", "Building...")
        build_solution_pdf(solutions, pdf_path, user_query, output_path, ui)
        ui.set_progress(98, "Finalizing...", "Almost done!", "📄", "Finalizing")

        # 5 — done
        ui.set_stage(5)
        ui.show_done(output_path)

        return (
            f"✅ Solution PDF ready!\n"
            f"📄 Source: {pdf_name}\n"
            f"📁 Output: {output_path}\n"
            f"📊 Pages: {page_count} | Query: {user_query}"
        )

    except requests.exceptions.ConnectionError as e:
        msg = f"Network error: {e}"
        ui.show_error(msg)
        return f"❌ {msg}"
    except requests.exceptions.HTTPError as e:
        msg = f"Groq API error: {e}"
        ui.show_error(msg)
        return f"❌ {msg}"
    except Exception as e:
        import traceback
        traceback.print_exc()
        ui.show_error(str(e))
        return f"❌ System error: {e}"