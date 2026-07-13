"""
create_ppt_tool.py
==================
Creates a professional 10-slide PowerPoint using python-pptx.

Dependencies (auto-installed on first run):
    pip install python-pptx

NO Node.js, NO pptxgenjs, NO aiohttp required.
HTTP via stdlib urllib only.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import datetime
import urllib.request
import urllib.parse
from livekit.agents import function_tool


# ─────────────────────────────────────────────
#  AUTO-INSTALL python-pptx if missing
# ─────────────────────────────────────────────

def _ensure_pptx():
    try:
        import pptx  # noqa
    except ImportError:
        print("📦 Installing python-pptx...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "python-pptx", "--quiet"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("✅ python-pptx installed!")


# ─────────────────────────────────────────────
#  HTTP HELPER (stdlib only)
# ─────────────────────────────────────────────

def _http_get_json(url: str, params: dict = None, timeout: int = 10):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AssistantBot/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


# ─────────────────────────────────────────────
#  WIKIPEDIA + DUCKDUCKGO RESEARCH
# ─────────────────────────────────────────────

def _wiki_search_title(topic: str) -> str:
    try:
        data = _http_get_json(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "opensearch", "search": topic,
                    "limit": 5, "namespace": 0, "format": "json"},
            timeout=8,
        )
        titles = data[1] if len(data) > 1 else []
        if titles:
            print(f"   🔎 Wikipedia matched: '{titles[0]}'")
            return titles[0]
    except Exception as e:
        print(f"   ⚠️ Wikipedia opensearch failed: {e}")
    return ""


def _wiki_fetch_content(page_title: str) -> str:
    if not page_title:
        return ""
    try:
        data = _http_get_json(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "titles": page_title,
                "prop": "extracts", "explaintext": "true",
                "exsectionformat": "plain", "exchars": 4000,
                "format": "json",
            },
            timeout=10,
        )
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            extract = page.get("extract", "").strip()
            if extract:
                extract = re.sub(r"={2,}[^=]+={2,}\n?", " ", extract)
                extract = re.sub(r"\s{2,}", " ", extract).strip()
                print(f"   ✅ Wikipedia: {len(extract.split())} words")
                return extract
    except Exception as e:
        print(f"   ⚠️ Wikipedia fetch failed: {e}")
    return ""


def _duckduckgo_abstract(topic: str) -> str:
    try:
        data = _http_get_json(
            "https://api.duckduckgo.com/",
            params={"q": topic, "format": "json",
                    "no_html": "1", "skip_disambig": "1"},
            timeout=6,
        )
        abstract = data.get("Abstract", "").strip()
        if abstract:
            print(f"   ✅ DuckDuckGo: {len(abstract.split())} words")
        return abstract
    except Exception as e:
        print(f"   ⚠️ DuckDuckGo failed: {e}")
    return ""


async def _research_topic(topic: str) -> dict:
    print(f"🔍 Researching: '{topic}'")
    page_title, ddg_text = await asyncio.gather(
        asyncio.to_thread(_wiki_search_title, topic),
        asyncio.to_thread(_duckduckgo_abstract, topic),
    )
    wiki_text = ""
    if page_title:
        wiki_text = await asyncio.to_thread(_wiki_fetch_content, page_title)

    combined = " ".join(filter(None, [wiki_text, ddg_text])).strip()

    if not combined:
        print("   ⚠️ No online content — using rich fallback")
        combined = (
            f"{topic} is a rapidly evolving and highly significant area of modern technology. "
            f"It brings together principles from computer science, engineering, and human-centered design "
            f"to deliver intelligent, adaptive, and user-friendly solutions. "
            f"The development of {topic} has been shaped by key milestones in artificial intelligence, "
            f"machine learning, and natural language processing. "
            f"Today, {topic} is widely adopted across healthcare, education, business, and consumer electronics. "
            f"Despite its promise, {topic} faces challenges such as data privacy, ethical concerns, "
            f"accuracy limitations, and accessibility gaps. "
            f"Researchers anticipate continued breakthroughs that will expand the capabilities of {topic}."
        )
    else:
        print(f"   📄 Total: {len(combined.split())} words")

    return {"raw_text": combined, "topic": topic}


# ─────────────────────────────────────────────
#  PYTHON-PPTX PRESENTATION BUILDER
# ─────────────────────────────────────────────

def _build_pptx(topic: str, raw_text: str, out_path: str):
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN

    # ── Colors ──────────────────────────────────
    NAVY   = RGBColor(0x0F, 0x17, 0x2A)
    BLUE   = RGBColor(0x1E, 0x40, 0xAF)
    GOLD   = RGBColor(0xF5, 0x9E, 0x0B)
    WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
    DARK   = RGBColor(0x1E, 0x29, 0x3B)
    LIGHT  = RGBColor(0xF8, 0xFA, 0xFC)
    CARD   = RGBColor(0xFF, 0xFF, 0xFF)
    MUTED  = RGBColor(0x94, 0xA3, 0xB8)
    LBLUE  = RGBColor(0xEF, 0xF6, 0xFF)
    LBLUE2 = RGBColor(0xBF, 0xDB, 0xFE)
    LGOLD  = RGBColor(0xFE, 0xF3, 0xC7)
    BORDER = RGBColor(0xE2, 0xE8, 0xF0)

    W  = Inches(10)
    H  = Inches(5.625)
    date_str = datetime.datetime.now().strftime("%B %Y")

    prs = Presentation()
    prs.slide_width  = W
    prs.slide_height = H

    # ── Helpers ──────────────────────────────────

    def blank_slide():
        layout = prs.slide_layouts[6]   # completely blank
        return prs.slides.add_slide(layout)

    def rect(slide, x, y, w, h, fill_rgb, line_rgb=None, line_w=Pt(0)):
        from pptx.util import Pt
        shape = slide.shapes.add_shape(1, x, y, w, h)   # MSO_SHAPE_TYPE.RECTANGLE = 1
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill_rgb
        if line_rgb:
            shape.line.color.rgb = line_rgb
            shape.line.width = line_w
        else:
            shape.line.fill.background()
        return shape

    def textbox(slide, text, x, y, w, h,
                font_size=14, bold=False, italic=False,
                color=None, align=PP_ALIGN.LEFT, font_name="Calibri",
                word_wrap=True):
        from pptx.util import Pt
        txBox = slide.shapes.add_textbox(x, y, w, h)
        txBox.word_wrap = word_wrap
        tf = txBox.text_frame
        tf.word_wrap = word_wrap
        p = tf.paragraphs[0]
        p.alignment = align
        run = p.add_run()
        run.text = text
        run.font.size = Pt(font_size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.name = font_name
        if color:
            run.font.color.rgb = color
        return txBox

    def bullet_box(slide, items, x, y, w, h, font_size=13, color=None):
        from pptx.util import Pt
        from pptx.oxml.ns import qn
        from lxml import etree
        color = color or DARK
        txBox = slide.shapes.add_textbox(x, y, w, h)
        txBox.word_wrap = True
        tf = txBox.text_frame
        tf.word_wrap = True
        for i, item in enumerate(items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(5)
            # bullet via XML
            pPr = p._p.get_or_add_pPr()
            buChar = etree.SubElement(pPr, qn('a:buChar'))
            buChar.set('char', '▸')
            buFont = etree.SubElement(pPr, qn('a:buFont'))
            buFont.set('typeface', 'Arial')
            run = p.add_run()
            run.text = item
            run.font.size = Pt(font_size)
            run.font.name = "Calibri"
            run.font.color.rgb = color
        return txBox

    def top_bar(slide, title_text):
        rect(slide, Inches(0), Inches(0), W, Inches(0.75), BLUE)
        textbox(slide, title_text,
                Inches(0.4), Inches(0.05), Inches(9.2), Inches(0.65),
                font_size=20, bold=True, color=WHITE,
                align=PP_ALIGN.LEFT)

    def content_card(slide, x, y, w, h):
        r = rect(slide, x, y, w, h, CARD, BORDER, Pt(0.5))
        return r

    # ── Chunk research text ───────────────────────
    words  = raw_text.split()
    chunks = [" ".join(words[i:i+55]) for i in range(0, len(words), 55)]
    n = len(chunks)
    sec1 = chunks[:max(1, n//3)]
    sec2 = chunks[max(1, n//3): max(2, 2*n//3)] or [f"{topic} has evolved significantly over time."]
    sec3 = chunks[max(2, 2*n//3):] or [f"The future of {topic} looks very promising."]

    # ════════════════════════════════════════════════
    #  SLIDE 1 — TITLE
    # ════════════════════════════════════════════════
    s = blank_slide()
    rect(s, Inches(0), Inches(0), W, H, NAVY)
    rect(s, Inches(0), Inches(0), W, Inches(0.18), GOLD)
    rect(s, Inches(0), Inches(5.4), W, Inches(0.225), GOLD)
    # inner card
    rect(s, Inches(0.5), Inches(0.6), Inches(9), Inches(4.5),
         RGBColor(0x1E, 0x29, 0x3B), RGBColor(0x33, 0x41, 0x55), Pt(1))
    textbox(s, topic,
            Inches(0.7), Inches(1.2), Inches(8.6), Inches(1.8),
            font_size=40, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    textbox(s, "A Comprehensive Presentation",
            Inches(0.7), Inches(3.1), Inches(8.6), Inches(0.55),
            font_size=18, italic=True, color=MUTED, align=PP_ALIGN.CENTER)
    textbox(s, f"{date_str}  ·  AI-Powered Research",
            Inches(0.7), Inches(4.5), Inches(8.6), Inches(0.4),
            font_size=12, color=RGBColor(0x64, 0x74, 0x8B), align=PP_ALIGN.CENTER)

    # ════════════════════════════════════════════════
    #  SLIDE 2 — AGENDA
    # ════════════════════════════════════════════════
    s = blank_slide()
    rect(s, Inches(0), Inches(0), W, H, LIGHT)
    top_bar(s, "Agenda")
    agenda_items = [
        "01  Introduction & Overview",
        "02  Key Concepts",
        "03  Core Details & Insights",
        "04  Applications & Examples",
        "05  Challenges",
        "06  Future Outlook",
        "07  Key Takeaways",
    ]
    cols = [Inches(0.35), Inches(5.15)]
    for i, item in enumerate(agenda_items):
        col = i % 2
        row = i // 2
        x = cols[col]
        y = Inches(0.98 + row * 1.05)
        rect(s, x, y, Inches(4.55), Inches(0.85), LBLUE, LBLUE2, Pt(0.5))
        rect(s, x, y, Inches(0.07), Inches(0.85), GOLD)
        textbox(s, item, x + Inches(0.14), y, Inches(4.38), Inches(0.85),
                font_size=13, color=DARK)

    # ════════════════════════════════════════════════
    #  SLIDE 3 — INTRODUCTION
    # ════════════════════════════════════════════════
    s = blank_slide()
    rect(s, Inches(0), Inches(0), W, H, LIGHT)
    top_bar(s, f"Introduction — What is {topic}?")
    content_card(s, Inches(0.4), Inches(0.95), Inches(9.2), Inches(4.2))
    bullet_box(s, sec1[:5], Inches(0.65), Inches(1.1), Inches(8.7), Inches(3.9))

    # ════════════════════════════════════════════════
    #  SLIDE 4 — KEY CONCEPTS (3 column cards)
    # ════════════════════════════════════════════════
    s = blank_slide()
    rect(s, Inches(0), Inches(0), W, H, LIGHT)
    top_bar(s, "Key Concepts & Background")
    cards = [
        ("🔷", "Definition",
         f"The foundational definition of {topic} centres on core principles and the problems it solves."),
        ("📜", "History",
         f"Development of {topic} spans key milestones across research, engineering, and real-world adoption."),
        ("🌐", "Scope",
         f"Its scope covers multiple disciplines, making {topic} a cross-functional and broadly applicable subject."),
    ]
    for i, (icon, title, body) in enumerate(cards):
        x = Inches(0.35 + i * 3.1)
        rect(s, x, Inches(0.95), Inches(2.95), Inches(4.2), CARD, BORDER, Pt(0.5))
        rect(s, x, Inches(0.95), Inches(2.95), Inches(0.55), BLUE)
        textbox(s, f"{icon}  {title}", x + Inches(0.1), Inches(0.95),
                Inches(2.75), Inches(0.55), font_size=14, bold=True, color=WHITE)
        textbox(s, body, x + Inches(0.12), Inches(1.58),
                Inches(2.71), Inches(3.45), font_size=12, color=DARK, word_wrap=True)

    # ════════════════════════════════════════════════
    #  SLIDE 5 — CORE DETAILS
    # ════════════════════════════════════════════════
    s = blank_slide()
    rect(s, Inches(0), Inches(0), W, H, LIGHT)
    top_bar(s, "Core Details & Insights")
    content_card(s, Inches(0.4), Inches(0.95), Inches(9.2), Inches(4.2))
    bullet_box(s, sec2[:5], Inches(0.65), Inches(1.1), Inches(8.7), Inches(3.9))

    # ════════════════════════════════════════════════
    #  SLIDE 6 — APPLICATIONS (2 column)
    # ════════════════════════════════════════════════
    s = blank_slide()
    rect(s, Inches(0), Inches(0), W, H, LIGHT)
    top_bar(s, "Applications & Real-World Examples")
    # Left card
    content_card(s, Inches(0.4), Inches(0.95), Inches(4.5), Inches(4.2))
    rect(s, Inches(0.4), Inches(0.95), Inches(4.5), Inches(0.45), LBLUE, LBLUE2, Pt(0.5))
    textbox(s, "✅  Industry Use Cases", Inches(0.5), Inches(0.95),
            Inches(4.3), Inches(0.45), font_size=13, bold=True, color=BLUE)
    bullet_box(s, [
        "Widely adopted across healthcare, education, and business.",
        "Supports smarter decision-making through data and automation.",
        "Enables efficiency improvements at enterprise scale.",
    ], Inches(0.55), Inches(1.5), Inches(4.2), Inches(3.5))
    # Right card
    content_card(s, Inches(5.1), Inches(0.95), Inches(4.5), Inches(4.2))
    rect(s, Inches(5.1), Inches(0.95), Inches(4.5), Inches(0.45), LGOLD,
         RGBColor(0xFD, 0xE6, 0x8A), Pt(0.5))
    textbox(s, "💡  Innovation Examples", Inches(5.2), Inches(0.95),
            Inches(4.3), Inches(0.45), font_size=13, bold=True,
            color=RGBColor(0x92, 0x40, 0x0E))
    bullet_box(s, [
        f"Startups leverage {topic} to disrupt traditional markets.",
        "Research institutions explore novel scientific applications.",
        "Governments incorporate insights into strategic planning.",
    ], Inches(5.25), Inches(1.5), Inches(4.2), Inches(3.5))

    # ════════════════════════════════════════════════
    #  SLIDE 7 — CHALLENGES (icon rows)
    # ════════════════════════════════════════════════
    s = blank_slide()
    rect(s, Inches(0), Inches(0), W, H, LIGHT)
    top_bar(s, "Challenges & Considerations")
    challenges = [
        ("⚙️", "Complexity",    "Managing inherent complexity requires domain expertise and structured approaches."),
        ("🔓", "Accessibility", "Ensuring broad access and reducing adoption barriers is an ongoing challenge."),
        ("⚖️", "Ethics",        "Ethical considerations must guide development, deployment, and governance."),
        ("📈", "Scalability",   "Scaling while maintaining performance demands continuous innovation and investment."),
    ]
    for i, (icon, label, desc) in enumerate(challenges):
        y = Inches(0.95 + i * 1.06)
        content_card(s, Inches(0.4), y, Inches(9.2), Inches(0.9))
        rect(s, Inches(0.4), y, Inches(1.5), Inches(0.9), LBLUE, LBLUE2, Pt(0.5))
        textbox(s, f"{icon} {label}", Inches(0.42), y, Inches(1.46), Inches(0.9),
                font_size=12, bold=True, color=BLUE, align=PP_ALIGN.CENTER)
        textbox(s, desc, Inches(2.05), y + Inches(0.1), Inches(7.4), Inches(0.8),
                font_size=13, color=DARK)

    # ════════════════════════════════════════════════
    #  SLIDE 8 — FUTURE OUTLOOK
    # ════════════════════════════════════════════════
    s = blank_slide()
    rect(s, Inches(0), Inches(0), W, H, LIGHT)
    top_bar(s, "Future Outlook & Emerging Trends")
    content_card(s, Inches(0.4), Inches(0.95), Inches(9.2), Inches(4.2))
    bullet_box(s, sec3[:5], Inches(0.65), Inches(1.1), Inches(8.7), Inches(3.9))

    # ════════════════════════════════════════════════
    #  SLIDE 9 — KEY TAKEAWAYS (numbered cards)
    # ════════════════════════════════════════════════
    s = blank_slide()
    rect(s, Inches(0), Inches(0), W, H, LIGHT)
    top_bar(s, "Key Takeaways")
    takeaways = [
        "A multifaceted subject with broad relevance across industries and disciplines.",
        "Understanding core concepts provides a strong foundation for deeper exploration.",
        "Real-world applications demonstrate measurable value across diverse sectors.",
        "Continued evolution signals an exciting and impactful future for this field.",
    ]
    for i, desc in enumerate(takeaways):
        y = Inches(0.95 + i * 1.05)
        content_card(s, Inches(0.4), y, Inches(9.2), Inches(0.9))
        rect(s, Inches(0.4), y, Inches(0.7), Inches(0.9), GOLD)
        textbox(s, f"0{i+1}", Inches(0.4), y, Inches(0.7), Inches(0.9),
                font_size=18, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        textbox(s, desc, Inches(1.25), y + Inches(0.1), Inches(8.2), Inches(0.8),
                font_size=13, color=DARK)

    # ════════════════════════════════════════════════
    #  SLIDE 10 — THANK YOU
    # ════════════════════════════════════════════════
    s = blank_slide()
    rect(s, Inches(0), Inches(0), W, H, NAVY)
    rect(s, Inches(0), Inches(0), W, Inches(0.18), GOLD)
    rect(s, Inches(0), Inches(5.4), W, Inches(0.225), GOLD)
    rect(s, Inches(1.5), Inches(0.8), Inches(7), Inches(4.0),
         RGBColor(0x1E, 0x29, 0x3B), RGBColor(0x33, 0x41, 0x55), Pt(1))
    textbox(s, "Thank You!", Inches(1.7), Inches(1.2), Inches(6.6), Inches(1.0),
            font_size=44, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    rect(s, Inches(3.5), Inches(2.45), Inches(3), Inches(0.05), GOLD)
    textbox(s, topic, Inches(1.7), Inches(2.6), Inches(6.6), Inches(0.7),
            font_size=20, italic=True, color=MUTED, align=PP_ALIGN.CENTER)
    textbox(s, f"Prepared by AI Assistant  ·  {date_str}",
            Inches(1.7), Inches(4.1), Inches(6.6), Inches(0.4),
            font_size=12, color=RGBColor(0x64, 0x74, 0x8B), align=PP_ALIGN.CENTER)

    prs.save(out_path)
    print(f"💾 Saved: {out_path}")


# ─────────────────────────────────────────────
#  MAIN TOOL
# ─────────────────────────────────────────────

@function_tool()
async def create_ppt_from_topic(topic: str, output_folder: str = "") -> str:
    """
    Creates a professional 10-slide PowerPoint on any topic.
    Auto-researches via Wikipedia + DuckDuckGo.
    Uses python-pptx (auto-installed) — NO Node.js needed.

    Args:
        topic: Presentation topic (any language)
        output_folder: Save folder path (default: Desktop)

    Returns:
        str: Success message with file path
    """
    if not topic.strip():
        return "❌ Please provide a topic."

    try:
        # Auto-install python-pptx if missing
        await asyncio.to_thread(_ensure_pptx)

        print(f"🎯 PPT REQUEST: '{topic}'")

        # Output path
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in topic).strip().replace(" ", "_")[:30]
        filename = f"PPT_{safe}_{datetime.datetime.now().strftime('%H%M%S')}.pptx"
        if output_folder and os.path.isdir(output_folder):
            out_path = os.path.join(output_folder, filename)
        else:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            out_path = os.path.join(desktop if os.path.isdir(desktop) else os.path.expanduser("~"), filename)

        print(f"📁 Output: {out_path}")

        # Research
        research = await _research_topic(topic)
        raw_text = research["raw_text"]
        print(f"✅ Research: {len(raw_text.split())} words")

        # Build PPT in thread (python-pptx is sync)
        await asyncio.to_thread(_build_pptx, topic, raw_text, out_path)

        if not os.path.exists(out_path):
            return f"❌ File not created at: {out_path}"

        size_kb = os.path.getsize(out_path) // 1024
        print(f"✅ Done: {size_kb} KB")

        return (
            f"✅ Presentation Ready!\n\n"
            f"📊 Topic   : {topic}\n"
            f"📄 File    : {filename}\n"
            f"📁 Saved at: {out_path}\n"
            f"📦 Size    : {size_kb} KB\n"
            f"🗂️ Slides  : 10 professional slides\n\n"
            f"Open the file in PowerPoint or Google Slides! 🎉"
        )

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"🚨 Error:\n{tb}")
        return f"❌ Error: {str(e)}"