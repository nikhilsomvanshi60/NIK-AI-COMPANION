"""
Web Scraper Pro — Tkinter Edition (Thread-safe for LiveKit)

ROOT CAUSE FIX:
  Tkinter MUST run on the main OS thread. LiveKit's agent loop runs on the main
  thread too, so we can't block it. Solution: start a dedicated OS-level thread
  ONCE at import time using a daemon thread that owns the Tk mainloop, and
  communicate with it via thread-safe queues.

  All Tk widget creation and updates happen inside that single thread via
  root.after(0, ...) callbacks — never from any other thread.

Dependencies: pip install aiohttp
Model: openai/gpt-oss-120b via Groq API
"""

import os, re, json, asyncio, threading, urllib.request, queue
from html.parser import HTMLParser
from datetime import datetime
import tkinter as tk
from tkinter import scrolledtext

import aiohttp

try:
    from livekit.agents import function_tool
except ImportError:
    def function_tool():
        def d(fn): return fn
        return d

# ─────────────────────────────────────────────────────────────────────────────
#  Palette & Fonts
# ─────────────────────────────────────────────────────────────────────────────
P = {
    "bg":      "#0D0D14",
    "bg2":     "#111118",
    "panel":   "#13131C",
    "card":    "#1A1A28",
    "card2":   "#1E1E2F",
    "border":  "#252538",
    "border2": "#303050",
    "accent":  "#6C63FF",
    "accentH": "#8B84FF",
    "green":   "#00E5A0",
    "red":     "#FF4757",
    "amber":   "#FFD43B",
    "text":    "#EEEEFF",
    "text2":   "#9090BB",
    "text3":   "#44446A",
}
FUI    = ("Segoe UI", 10)
FUIB   = ("Segoe UI", 10, "bold")
FUIS   = ("Segoe UI",  9)
FUISB  = ("Segoe UI",  9, "bold")
FTITLE = ("Segoe UI", 13, "bold")
FBADGE = ("Segoe UI",  7, "bold")
FMONO  = ("Consolas", 10)
FMONOS = ("Consolas",  9)


# ─────────────────────────────────────────────────────────────────────────────
#  HTML Parser + Scraper
# ─────────────────────────────────────────────────────────────────────────────
class SmartHTMLParser(HTMLParser):
    SKIP = {"script","style","noscript","nav","footer","aside","iframe","svg","button","form"}
    META = {"description","keywords","og:title","og:description","twitter:description","og:site_name"}

    def __init__(self):
        super().__init__()
        self.skip=0; self.texts=[]; self.title=""
        self.meta={}; self.links=0; self.images=0
        self.headings=[]; self._tag=""; self._intitle=False

    def handle_starttag(self, tag, attrs):
        self._tag = tag; a = dict(attrs)
        if tag in self.SKIP: self.skip += 1; return
        if tag == "title": self._intitle = True
        if tag == "meta":
            n = a.get("name", a.get("property","")).lower()
            c = a.get("content","")
            if n in self.META and c: self.meta[n] = c
        if tag == "a" and "href" in a: self.links += 1
        if tag == "img": self.images += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP: self.skip = max(0, self.skip-1)
        if tag == "title": self._intitle = False

    def handle_data(self, data):
        if self.skip > 0: return
        t = data.strip()
        if not t: return
        if self._intitle and not self.title: self.title = t
        if self._tag in ("h1","h2","h3","h4"): self.headings.append((self._tag, t))
        if len(t) > 25: self.texts.append(t)

    def clean(self, n=8000):
        return re.sub(r'\n{3,}', '\n\n', "\n".join(self.texts))[:n]

    def info(self):
        return {"title": self.title, "meta": self.meta,
                "headings": self.headings[:15],
                "links": self.links, "images": self.images}


def scrape_url(url: str):
    if not url.startswith(("http://","https://")): url = "https://" + url
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        enc = r.headers.get_content_charset() or "utf-8"
        html = r.read(1_200_000).decode(enc, errors="replace")
    p = SmartHTMLParser(); p.feed(html)
    return p.clean(), p.info()


async def groq_analyse(query, content, meta, key):
    payload = {
        "model": "openai/gpt-oss-120b",
        "temperature": 0.3,
        "max_tokens": 600,
        "messages": [
            {"role": "system", "content":
                "You are a precise web content analyst. Answer the user's query "
                "based only on the provided webpage content. "
                "Use bullet points where helpful. Max 400 words."},
            {"role": "user", "content":
                f"Metadata:\n{json.dumps(meta, indent=2)}\n\n"
                f"Content:\n{content[:6000]}\n\nQuery: {query}"}
        ]
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json=payload, timeout=60
        ) as r:
            if r.status != 200:
                raise RuntimeError(f"Groq API {r.status}: {(await r.text())[:200]}")
            d = await r.json()
            return d["choices"][0]["message"]["content"].strip()


# ─────────────────────────────────────────────────────────────────────────────
#  Tk Thread Manager — owns the one Tk mainloop forever
# ─────────────────────────────────────────────────────────────────────────────
class _TkManager:
    """
    Starts a single background thread that owns the Tk mainloop.
    All widget creation must happen via .schedule(fn) which posts
    the callable to that thread via root.after(0, fn).
    """
    def __init__(self):
        self._root: tk.Tk | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="TkMainLoop")
        self._thread.start()
        self._ready.wait(timeout=5)

    def _run(self):
        self._root = tk.Tk()
        self._root.withdraw()          # hidden host window — never shown
        self._root.title("_scraper_host")
        self._ready.set()
        self._root.mainloop()

    def schedule(self, fn):
        """Post fn() to the Tk thread. Safe to call from any thread."""
        if self._root:
            self._root.after(0, fn)


# Module-level singleton — created once at import time
_tk_mgr = _TkManager()


# ─────────────────────────────────────────────────────────────────────────────
#  Animated Strip
# ─────────────────────────────────────────────────────────────────────────────
class AnimStrip(tk.Canvas):
    COLORS = ["#6C63FF","#7B73FF","#8B84FF","#9D97FF",
              "#00D9C4","#33E0D4","#FF6B9D","#FF8EB5","#6C63FF"]

    def __init__(self, master):
        super().__init__(master, height=3, bg=P["border"], highlightthickness=0)
        self._pos = 0
        self._running = False

    def start(self):
        self._running = True; self._pos = 0; self._tick()

    def stop(self):
        self._running = False; self.delete("all")

    def _tick(self):
        if not self._running: return
        self.delete("all")
        w = self.winfo_width() or 800
        seg = max(w // len(self.COLORS), 1)
        for i, c in enumerate(self.COLORS):
            x0 = (self._pos + i * seg) % (w + seg)
            self.create_rectangle(x0, 0, x0 + seg + 2, 3, fill=c, outline="")
        self._pos = (self._pos + 5) % (w + seg)
        self.after(25, self._tick)


# ─────────────────────────────────────────────────────────────────────────────
#  Flat Entry with placeholder + focus glow
# ─────────────────────────────────────────────────────────────────────────────
class FlatEntry(tk.Frame):
    def __init__(self, master, placeholder="", mono=False):
        super().__init__(master, bg=P["card"],
                         highlightthickness=1,
                         highlightbackground=P["border2"],
                         highlightcolor=P["accent"])
        self._ph = placeholder
        self._ph_active = False
        self._var = tk.StringVar()
        self._e = tk.Entry(self, textvariable=self._var,
                           font=FMONO if mono else FUI,
                           bg=P["card"], fg=P["text"],
                           insertbackground=P["accent"],
                           relief="flat", bd=8, highlightthickness=0)
        self._e.pack(fill="x")
        if placeholder:
            self._var.set(placeholder)
            self._e.config(fg=P["text3"])
            self._ph_active = True
        self._e.bind("<FocusIn>",  self._on_focus)
        self._e.bind("<FocusOut>", self._on_blur)

    def _on_focus(self, _=None):
        self.config(highlightbackground=P["accent"], bg=P["bg2"])
        self._e.config(bg=P["bg2"])
        if self._ph_active:
            self._var.set(""); self._e.config(fg=P["text"]); self._ph_active = False

    def _on_blur(self, _=None):
        self.config(highlightbackground=P["border2"], bg=P["card"])
        self._e.config(bg=P["card"])
        if not self._var.get():
            self._var.set(self._ph); self._e.config(fg=P["text3"]); self._ph_active = True

    def flash_error(self):
        self.config(highlightbackground=P["red"])
        self.after(1500, lambda: self.config(highlightbackground=P["border2"]))

    def get(self):
        return "" if self._ph_active else self._var.get()

    def set(self, val):
        self._ph_active = False; self._var.set(val); self._e.config(fg=P["text"])

    def clear(self):
        self._var.set(self._ph if self._ph else "")
        self._e.config(fg=P["text3"] if self._ph else P["text"])
        self._ph_active = bool(self._ph)

    def bind_return(self, fn):
        self._e.bind("<Return>", fn)


# ─────────────────────────────────────────────────────────────────────────────
#  Status Pill
# ─────────────────────────────────────────────────────────────────────────────
class StatusPill(tk.Label):
    STATES = {
        "idle":    (P["text3"], "IDLE"),
        "working": (P["amber"], "WORKING"),
        "done":    (P["green"], "DONE"),
        "error":   (P["red"],   "ERROR"),
    }
    def __init__(self, master):
        super().__init__(master, font=FBADGE, bg=P["bg2"], padx=8, pady=3)
        self.set("idle")

    def set(self, state):
        color, label = self.STATES.get(state, self.STATES["idle"])
        self.config(text=f"  ●  {label}  ", fg=color)


# ─────────────────────────────────────────────────────────────────────────────
#  Tab Pane — panes born with correct master, no reparenting
# ─────────────────────────────────────────────────────────────────────────────
class TabPane(tk.Frame):
    def __init__(self, master, tab_names: list):
        super().__init__(master, bg=P["bg"])
        bar = tk.Frame(self, bg=P["bg"])
        bar.pack(fill="x")
        self._content = tk.Frame(self, bg=P["panel"],
                                  highlightthickness=1,
                                  highlightbackground=P["border"])
        self._content.pack(fill="both", expand=True)
        self._panes = {}
        self._btns  = {}

        for name in tab_names:
            pane = scrolledtext.ScrolledText(
                self._content,
                font=FMONOS if name.strip() in ("Page Info", "Raw Text") else FUI,
                bg=P["panel"], fg=P["text2"],
                insertbackground=P["text"],
                selectbackground=P["accent"], selectforeground="#FFFFFF",
                relief="flat", bd=0, wrap="word",
                padx=16, pady=14, state="disabled"
            )
            pane.vbar.config(bg=P["card"], troughcolor=P["bg2"],
                              activebackground=P["border2"],
                              relief="flat", bd=0, width=5,
                              highlightthickness=0)
            self._panes[name] = pane

            btn = tk.Button(bar, text=f"  {name}  ", font=FUISB,
                             bg=P["card"], fg=P["text3"],
                             activebackground=P["panel"], activeforeground=P["text"],
                             relief="flat", bd=0, cursor="hand2", pady=9, padx=2,
                             command=lambda n=name: self.show(n))
            btn.pack(side="left")
            self._btns[name] = btn

        if tab_names:
            self.show(tab_names[0])

    def show(self, name):
        for n, p in self._panes.items(): p.place_forget()
        self._panes[name].place(in_=self._content, relwidth=1, relheight=1)
        for n, b in self._btns.items():
            b.config(bg=P["panel"] if n==name else P["card"],
                     fg=P["text"]  if n==name else P["text3"],
                     font=FUIB     if n==name else FUISB)

    def write(self, name, text):
        p = self._panes[name]
        p.config(state="normal"); p.delete("1.0","end")
        p.insert("end", text);    p.config(state="disabled")

    def clear_all(self):
        for p in self._panes.values():
            p.config(state="normal"); p.delete("1.0","end"); p.config(state="disabled")


# ─────────────────────────────────────────────────────────────────────────────
#  Sidebar History Item
# ─────────────────────────────────────────────────────────────────────────────
class SidebarItem(tk.Frame):
    def __init__(self, master, url, on_click):
        super().__init__(master, bg=P["bg2"], cursor="hand2")
        short = url.replace("https://","").replace("http://","")
        short = (short[:33]+"…") if len(short)>33 else short
        lbl = tk.Label(self, text=short, font=FUIS,
                       bg=P["bg2"], fg=P["text2"], anchor="w", padx=12, pady=7)
        lbl.pack(fill="x")
        for w in (self, lbl):
            w.bind("<Enter>", lambda e: (self.config(bg=P["card"]),
                                          lbl.config(bg=P["card"], fg=P["text"])))
            w.bind("<Leave>", lambda e: (self.config(bg=P["bg2"]),
                                          lbl.config(bg=P["bg2"], fg=P["text2"])))
            w.bind("<Button-1>", lambda e, u=url: on_click(u))


# ─────────────────────────────────────────────────────────────────────────────
#  Scraper Window — ALL creation inside _TkManager thread via schedule()
# ─────────────────────────────────────────────────────────────────────────────
class ScraperWindow:
    TABS = ["AI Analysis", "Page Info", "Raw Text"]

    def __init__(self, initial_query="", api_key=""):
        self.api_key     = api_key
        self.result_text = ""
        self._history    = []
        self._closed_evt = threading.Event()

        # All Tk widget creation must happen on the Tk thread
        _tk_mgr.schedule(lambda: self._create_window(initial_query))

    def _create_window(self, initial_query):
        """Called on the Tk thread."""
        self.win = tk.Toplevel(_tk_mgr._root)
        self.win.title("Web Scraper Pro")
        self.win.geometry("1100x700")
        self.win.minsize(820, 540)
        self.win.configure(bg=P["bg"])
        self.win.resizable(True, True)

        # Center
        self.win.update_idletasks()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"1100x700+{(sw-1100)//2}+{(sh-700)//2}")

        self._build_all(initial_query)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self.win.deiconify()

    def _build_all(self, initial_query):
        # Title bar
        bar = tk.Frame(self.win, bg=P["bg2"], height=50)
        bar.pack(fill="x"); bar.pack_propagate(False)
        left = tk.Frame(bar, bg=P["bg2"])
        left.pack(side="left", padx=20, fill="y")
        tk.Label(left, text="◈", font=("Segoe UI Symbol",16),
                 bg=P["bg2"], fg=P["accent"]).pack(side="left", pady=12)
        tk.Label(left, text="  Web Scraper", font=FTITLE,
                 bg=P["bg2"], fg=P["text"]).pack(side="left")
        tk.Label(left, text="  PRO", font=FBADGE,
                 bg=P["bg2"], fg=P["accent"]).pack(side="left", pady=2)
        self.status_pill = StatusPill(bar)
        self.status_pill.pack(side="right", padx=20, pady=13)

        # Progress strip
        self.strip = AnimStrip(self.win)
        self.strip.pack(fill="x")
        tk.Frame(self.win, bg=P["border"], height=1).pack(fill="x")

        # Body
        body = tk.Frame(self.win, bg=P["bg"])
        body.pack(fill="both", expand=True)

        # Sidebar
        side = tk.Frame(body, bg=P["bg2"], width=210)
        side.pack(side="left", fill="y"); side.pack_propagate(False)

        hdr = tk.Frame(side, bg=P["bg2"], height=36)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="  HISTORY", font=FBADGE,
                 bg=P["bg2"], fg=P["text3"]).pack(side="left", padx=6, pady=10)
        tk.Frame(hdr, bg=P["border"], height=1).pack(side="bottom", fill="x")

        hc = tk.Canvas(side, bg=P["bg2"], highlightthickness=0)
        hc.pack(side="left", fill="both", expand=True)
        vsb = tk.Scrollbar(side, orient="vertical", command=hc.yview,
                            bg=P["card"], troughcolor=P["bg2"],
                            relief="flat", bd=0, width=4, highlightthickness=0)
        vsb.pack(side="right", fill="y")
        hc.configure(yscrollcommand=vsb.set)
        self._hist_inner = tk.Frame(hc, bg=P["bg2"])
        hw = hc.create_window((0,0), window=self._hist_inner, anchor="nw")
        self._hist_inner.bind("<Configure>",
            lambda e: hc.configure(scrollregion=hc.bbox("all")))
        hc.bind("<Configure>", lambda e: hc.itemconfig(hw, width=e.width))

        foot = tk.Frame(side, bg=P["bg2"], height=32)
        foot.pack(fill="x", side="bottom"); foot.pack_propagate(False)
        tk.Frame(foot, bg=P["border"], height=1).pack(side="top", fill="x")
        tk.Label(foot, text="  Groq AI  ·  gpt-oss-120b", font=FBADGE,
                 bg=P["bg2"], fg=P["text3"]).pack(side="left", padx=8, pady=8)

        tk.Frame(body, bg=P["border"], width=1).pack(side="left", fill="y")

        # Main area
        main = tk.Frame(body, bg=P["bg"])
        main.pack(side="left", fill="both", expand=True)

        tk.Label(main, text="SCRAPE  &  ANALYSE", font=FBADGE,
                 bg=P["bg"], fg=P["text3"]).pack(anchor="w", padx=28, pady=(22,14))

        tk.Label(main, text="Target URL", font=FUIS,
                 bg=P["bg"], fg=P["text2"]).pack(anchor="w", padx=28, pady=(0,4))
        self.url_entry = FlatEntry(main, placeholder="https://example.com", mono=True)
        self.url_entry.pack(fill="x", padx=28, ipady=6, pady=(0,12))
        self.url_entry.bind_return(lambda e: self._run())

        tk.Label(main, text="Your Query", font=FUIS,
                 bg=P["bg"], fg=P["text2"]).pack(anchor="w", padx=28, pady=(0,4))
        self.q_entry = FlatEntry(main,
            placeholder="What is this website about? What products does it offer?")
        self.q_entry.pack(fill="x", padx=28, ipady=6, pady=(0,16))
        self.q_entry.set(initial_query)
        self.q_entry.bind_return(lambda e: self._run())

        btn_row = tk.Frame(main, bg=P["bg"])
        btn_row.pack(fill="x", padx=28, pady=(0,12))

        self.go_btn = tk.Button(btn_row, text="  Scrape + Analyse  ",
            command=self._run, font=FUIB, bg=P["accent"], fg="#FFFFFF",
            activebackground=P["accentH"], activeforeground="#FFFFFF",
            relief="flat", bd=0, cursor="hand2", padx=20, pady=9)
        self.go_btn.pack(side="left")

        self.raw_btn = tk.Button(btn_row, text="  Raw Text Only  ",
            command=lambda: self._run(raw_only=True),
            font=FUI, bg=P["card2"], fg=P["text2"],
            activebackground=P["border2"], activeforeground=P["text"],
            relief="flat", bd=0, cursor="hand2", padx=16, pady=9)
        self.raw_btn.pack(side="left", padx=(8,0))

        tk.Button(btn_row, text="  Clear  ", command=self._clear,
                  font=FUIS, bg=P["bg2"], fg=P["text3"],
                  activebackground=P["card"], activeforeground=P["text2"],
                  relief="flat", bd=0, cursor="hand2",
                  padx=12, pady=9).pack(side="right")

        self.msg_lbl = tk.Label(main,
            text="Enter a URL and query, then click  Scrape + Analyse.",
            font=FUIS, bg=P["bg"], fg=P["text3"])
        self.msg_lbl.pack(anchor="w", padx=28, pady=(0,8))

        self.tabs = TabPane(main, self.TABS)
        self.tabs.pack(fill="both", expand=True, padx=28, pady=(0,20))

        self.tabs.write("AI Analysis",
            "Web Scraper Pro  ·  Model: openai/gpt-oss-120b\n"
            "────────────────────────────────────────────────────\n\n"
            "How to use:\n"
            "  1.  Paste any URL in the Target URL field\n"
            "  2.  Type your question in the Query field\n"
            "  3.  Click  Scrape + Analyse\n\n"
            "Result tabs:\n"
            "  AI Analysis  —  GPT-OSS-120b answer to your query\n"
            "  Page Info    —  Title, meta tags, heading structure\n"
            "  Raw Text     —  Full scraped page content\n\n"
            "No browser or Selenium needed.  Pure HTTP scraping.\n"
            "Free AI via Groq  (get key at console.groq.com)"
        )

    # ── Actions (called from Tk thread via after() or directly) ───────────────
    def _run(self, raw_only=False):
        url = self.url_entry.get().strip()
        q   = self.q_entry.get().strip()
        if not url:
            self.url_entry.flash_error(); self._msg("Please enter a URL."); return
        if not raw_only and not q:
            self.q_entry.flash_error(); self._msg("Please enter a query."); return

        self._add_history(url)
        self._busy(True)

        # Scraping/AI runs in a plain thread (no Tkinter calls there)
        threading.Thread(target=self._bg_worker,
                          args=(url, q, raw_only), daemon=True).start()

    def _bg_worker(self, url, query, raw_only):
        """Pure background thread — no Tkinter calls. Posts results via after()."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_work(url, query, raw_only))
        except Exception as e:
            err = str(e)
            _tk_mgr.schedule(lambda: self._on_error(err))
        finally:
            loop.close()

    async def _async_work(self, url, query, raw_only):
        _tk_mgr.schedule(lambda: self._msg("Fetching page content..."))

        content, info = await asyncio.get_event_loop().run_in_executor(
            None, scrape_url, url)

        sep = "─" * 52
        meta_lines = [
            f"URL           {url}",
            f"Title         {info.get('title') or '—'}",
            f"Characters    {len(content):,}",
            f"Links         {info.get('links',0):,}",
            f"Images        {info.get('images',0):,}",
            "", "META TAGS", sep,
            *[f"{k:<22}{v[:80]}" for k,v in info.get("meta",{}).items()],
            "", "HEADINGS", sep,
            *[("  "*(int(h[0][1])-1))+f"[{h[0].upper()}]  {h[1][:80]}"
              for h in info.get("headings",[])],
        ]
        meta_text = "\n".join(meta_lines)

        if raw_only:
            ai = (f"Raw Scrape Complete\n{sep}\n\n"
                  f"Title: {info.get('title') or '—'}\n"
                  f"Characters: {len(content):,}\n\n"
                  "See the  Raw Text  tab for full content.")
            _tk_mgr.schedule(lambda a=ai, m=meta_text, r=content:
                              self._on_done(a, m, r))
            return

        _tk_mgr.schedule(lambda: self._msg("Analysing with GPT-OSS-120b..."))

        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY not set.\n\n"
                "Get a free key at:  console.groq.com\n\n"
                "Set in terminal:\n"
                "  CMD:         set GROQ_API_KEY=gsk_...\n"
                "  PowerShell:  $env:GROQ_API_KEY='gsk_...'\n\n"
                "Or use  Raw Text Only  to scrape without AI."
            )

        result = await groq_analyse(query, content, info, self.api_key)
        ts = datetime.now().strftime("%H:%M:%S")
        ai = (
            f"Query    {query}\n"
            f"URL      {url}\n"
            f"Model    openai/gpt-oss-120b\n"
            f"Time     {ts}\n{sep}\n\n"
            f"{result}\n\n{sep}\n"
            f"Scraped {len(content):,} chars  ·  "
            f"{len(info.get('headings',[]))} headings  ·  "
            f"{info.get('links',0):,} links"
        )
        _tk_mgr.schedule(lambda a=ai, m=meta_text, r=content:
                          self._on_done(a, m, r))

    # ── UI update callbacks (all run on Tk thread) ────────────────────────────
    def _on_done(self, ai, info, raw):
        self.result_text = ai
        self.tabs.write("AI Analysis", ai)
        self.tabs.write("Page Info",   info)
        self.tabs.write("Raw Text",    raw)
        self.tabs.show("AI Analysis")
        self._msg("Analysis complete.")
        self.status_pill.set("done")
        self._busy(False)

    def _on_error(self, err):
        self.tabs.write("AI Analysis", f"Error\n{'─'*50}\n\n{err}")
        self._msg("An error occurred — see AI Analysis tab.")
        self.status_pill.set("error")
        self._busy(False)

    def _busy(self, yes):
        state = "disabled" if yes else "normal"
        self.go_btn.config(state=state)
        self.raw_btn.config(state=state)
        if yes: self.strip.start(); self.status_pill.set("working")
        else:   self.strip.stop()

    def _clear(self):
        self.url_entry.clear(); self.q_entry.clear()
        self.tabs.clear_all()
        self._msg("Cleared."); self.status_pill.set("idle")

    def _msg(self, text):
        self.msg_lbl.config(text=text)

    def _add_history(self, url):
        if url in self._history: return
        self._history.insert(0, url)
        item = SidebarItem(self._hist_inner, url,
                           lambda u: self.url_entry.set(u))
        item.pack(fill="x", pady=1)

    def _on_close(self):
        self._closed_evt.set()
        self.win.destroy()

    def wait_closed(self) -> str:
        """Block the calling thread until the window is closed."""
        self._closed_evt.wait()
        return self.result_text


# ─────────────────────────────────────────────────────────────────────────────
#  LiveKit function_tool
# ─────────────────────────────────────────────────────────────────────────────
@function_tool()
async def web_scraper(query: str) -> str:
    """
    Opens Web Scraper Pro GUI for scraping + AI analysis.
    Thread-safe: works alongside an existing PyQt5 QApplication.
    Args:
        query: What to find out from the webpage.
    Returns:
        AI analysis result string.
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    win = ScraperWindow(initial_query=query, api_key=api_key)

    # Wait for window to be created on Tk thread before returning
    await asyncio.sleep(0.3)

    # Wait for user to close the window (non-blocking poll)
    while not win._closed_evt.is_set():
        await asyncio.sleep(0.3)

    return win.result_text or "Window closed before completing."


# ─────────────────────────────────────────────────────────────────────────────
#  Standalone
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # In standalone mode, just use normal Tk mainloop (no LiveKit conflict)
    import tkinter as tk2
    root = tk2.Tk()
    root.withdraw()

    win = ScraperWindow(
        initial_query="What is this website about?",
        api_key=os.getenv("GROQ_API_KEY", "")
    )
    # Wait until window is built, then show via mainloop on THIS thread
    # Since _TkManager owns the loop, just keep main alive
    try:
        win._closed_evt.wait()
    except KeyboardInterrupt:
        pass