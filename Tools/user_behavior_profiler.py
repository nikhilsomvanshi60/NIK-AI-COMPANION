"""
User Behavior Profiler — Local JSON + LiveKit Agents
=====================================================
Har conversation mein silently user ko samjhta hai aur profile build karta hai.

Tracks:
  1. Mood detection         — khush, stressed, busy, neutral
  2. Communication style    — formal, casual, short, detailed
  3. Daily routine patterns — subah/dopahar/shaam/raat activity
  4. Interests & topics     — frequently poocha gaya kya
  5. Work habits            — focus time, break patterns

Storage: Local JSON file (private, no cloud)

Install:
    pip install livekit-agents
"""

import json
import os
import re
import asyncio
from datetime import datetime, date
from pathlib import Path
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Optional
from zoneinfo import ZoneInfo

from livekit.agents import function_tool


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

PROFILE_PATH = Path(os.getenv("USER_PROFILE_PATH", "user_profile.json"))
TIMEZONE     = os.getenv("USER_TIMEZONE", "Asia/Kolkata")

# ─────────────────────────────────────────────
# MOOD KEYWORDS
# ─────────────────────────────────────────────

MOOD_SIGNALS = {
    "happy": [
        "great", "amazing", "awesome", "love", "fantastic", "wonderful",
        "excellent", "happy", "excited", "perfect", "yay", "thanks",
        "shukriya", "mast", "badhiya", "zabardast", "khushi", "acha laga",
    ],
    "stressed": [
        "stressed", "overwhelmed", "too much", "cant handle", "deadline",
        "pressure", "anxious", "worried", "nervous", "help me fast",
        "jaldi", "urgent", "abhi chahiye", "bahut kaam", "thak gaya",
        "pareshan", "tension", "mushkil",
    ],
    "busy": [
        "busy", "meeting", "call", "in a rush", "quickly", "brief",
        "short", "fast", "no time", "later", "brb", "kam time",
        "thodi der mein", "bta jldi",
    ],
    "neutral": [],  # default fallback
    "tired": [
        "tired", "exhausted", "sleepy", "bored", "not feeling",
        "thaka", "neend", "aaj nahi", "kal karte", "rest",
    ],
}

TOPIC_KEYWORDS = {
    "technology":   ["code", "python", "software", "app", "computer", "laptop", "install", "error", "bug", "api"],
    "productivity": ["task", "reminder", "focus", "deadline", "schedule", "plan", "organize", "goal"],
    "health":       ["exercise", "gym", "diet", "sleep", "health", "walk", "food", "water", "rest"],
    "finance":      ["money", "budget", "expense", "salary", "investment", "save", "spend", "paisa"],
    "learning":     ["study", "learn", "read", "book", "course", "explain", "what is", "how does", "padhai"],
    "entertainment":["movie", "music", "game", "netflix", "youtube", "song", "web series", "cricket"],
    "work":         ["office", "meeting", "email", "report", "project", "client", "boss", "presentation"],
    "personal":     ["family", "friend", "ghar", "mom", "dad", "bhai", "dost", "relationship"],
}


# ─────────────────────────────────────────────
# PROFILE DATA STRUCTURE
# ─────────────────────────────────────────────

def _empty_time_slots():
    return {"morning": 0, "afternoon": 0, "evening": 0, "night": 0}

def _empty_mood():
    return {"happy": 0, "stressed": 0, "busy": 0, "neutral": 0, "tired": 0}

def _empty_style():
    return {"formal": 0, "casual": 0, "short": 0, "detailed": 0}


class UserProfile:
    """
    JSON-backed user profile.
    Profile keys:
      - mood_history        : mood counts over all time
      - daily_mood          : {date: mood} last 30 days
      - time_slots          : activity per time of day
      - topics              : topic frequency counter
      - style               : communication style signals
      - work_sessions       : list of {start, end, duration_min}
      - interactions        : total interaction count
      - first_seen          : ISO date
      - last_seen           : ISO datetime
      - name                : user ka naam agar pata ho
      - language_preference : "hindi", "english", "hinglish"
      - insights            : generated insight strings list
    """

    def __init__(self, path: Path = PROFILE_PATH):
        self.path = path
        self._data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        # Fresh profile
        return {
            "mood_history":        _empty_mood(),
            "daily_mood":          {},
            "time_slots":          _empty_time_slots(),
            "topics":              {},
            "style":               _empty_style(),
            "work_sessions":       [],
            "interactions":        0,
            "first_seen":          date.today().isoformat(),
            "last_seen":           datetime.now().isoformat(),
            "name":                None,
            "language_preference": "hinglish",
            "insights":            [],
        }

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def inc(self, key: str, subkey: str, by: int = 1):
        if key not in self._data:
            self._data[key] = {}
        self._data[key][subkey] = self._data[key].get(subkey, 0) + by

    @property
    def data(self):
        return self._data


# ─────────────────────────────────────────────
# ANALYZER ENGINE
# ─────────────────────────────────────────────

class BehaviorAnalyzer:
    def __init__(self, profile: UserProfile):
        self.profile = profile
        self._work_session_start: Optional[datetime] = None
        self._tz = ZoneInfo(TIMEZONE)

    def _now(self) -> datetime:
        return datetime.now(self._tz)

    def _time_slot(self, dt: datetime) -> str:
        h = dt.hour
        if 5  <= h < 12: return "morning"
        if 12 <= h < 17: return "afternoon"
        if 17 <= h < 21: return "evening"
        return "night"

    # ── 1. Mood Detection ────────────────────────────────────────────────────

    def detect_mood(self, text: str) -> str:
        text_lower = text.lower()
        scores = {mood: 0 for mood in MOOD_SIGNALS}

        for mood, keywords in MOOD_SIGNALS.items():
            for kw in keywords:
                if kw in text_lower:
                    scores[mood] += 1

        # Punctuation signals
        if text.count("!") >= 2:
            scores["happy"] += 1
        if text.count("?") >= 3 or "???" in text:
            scores["stressed"] += 1
        if len(text.split()) <= 4:
            scores["busy"] += 1

        best = max(scores, key=scores.get)
        if scores[best] == 0:
            best = "neutral"

        # Save
        today = date.today().isoformat()
        self.profile.inc("mood_history", best)
        self.profile.data["daily_mood"][today] = best

        return best

    # ── 2. Communication Style ───────────────────────────────────────────────

    def detect_style(self, text: str) -> str:
        words = text.split()
        word_count = len(words)

        # Short vs Detailed
        if word_count <= 6:
            self.profile.inc("style", "short")
            style = "short"
        else:
            self.profile.inc("style", "detailed")
            style = "detailed"

        # Formal vs Casual
        formal_signals   = ["please", "kindly", "could you", "would you", "sir", "madam", "kripya"]
        casual_signals   = ["yaar", "bhai", "dude", "hey", "haan", "nahi", "kya", "bol", "kr", "de"]

        text_lower = text.lower()
        formal_score = sum(1 for s in formal_signals if s in text_lower)
        casual_score = sum(1 for s in casual_signals if s in text_lower)

        if formal_score > casual_score:
            self.profile.inc("style", "formal")
        else:
            self.profile.inc("style", "casual")

        return style

    # ── 3. Topic Detection ───────────────────────────────────────────────────

    def detect_topics(self, text: str) -> list[str]:
        text_lower = text.lower()
        found = []
        for topic, keywords in TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    found.append(topic)
                    self.profile.inc("topics", topic)
                    break
        return found

    # ── 4. Routine Pattern ───────────────────────────────────────────────────

    def record_activity(self):
        slot = self._time_slot(self._now())
        self.profile.inc("time_slots", slot)
        return slot

    # ── 5. Language Detection ────────────────────────────────────────────────

    def detect_language(self, text: str) -> str:
        hindi_chars = sum(1 for c in text if '\u0900' <= c <= '\u097F')
        words = text.split()

        hinglish_words = [
            "kya", "hai", "ho", "kr", "de", "bata", "haan", "nahi",
            "aur", "me", "ka", "ki", "ko", "se", "pe", "ab", "bas",
        ]
        hinglish_score = sum(1 for w in words if w.lower() in hinglish_words)

        if hindi_chars > 5:
            lang = "hindi"
        elif hinglish_score >= 2:
            lang = "hinglish"
        else:
            lang = "english"

        self.profile.set("language_preference", lang)
        return lang

    # ── Work Session Tracking ────────────────────────────────────────────────

    def start_work_session(self):
        self._work_session_start = self._now()

    def end_work_session(self) -> Optional[int]:
        if not self._work_session_start:
            return None
        duration = int((self._now() - self._work_session_start).total_seconds() / 60)
        if duration >= 1:
            sessions = self.profile.get("work_sessions", [])
            sessions.append({
                "date":         date.today().isoformat(),
                "start":        self._work_session_start.strftime("%H:%M"),
                "end":          self._now().strftime("%H:%M"),
                "duration_min": duration,
            })
            # Last 50 sessions hi rakhna
            self.profile.set("work_sessions", sessions[-50:])
        self._work_session_start = None
        return duration

    # ── Insight Generator ────────────────────────────────────────────────────

    def generate_insights(self) -> list[str]:
        insights = []
        d = self.profile.data

        # Most active time
        slots = d.get("time_slots", {})
        if slots:
            peak = max(slots, key=slots.get)
            if slots[peak] > 0:
                insights.append(f"Tum sabse zyada {peak} mein active rehte ho.")

        # Dominant mood
        moods = d.get("mood_history", {})
        if moods:
            top_mood = max(moods, key=moods.get)
            if moods[top_mood] > 0:
                insights.append(f"Tumhara common mood '{top_mood}' rehta hai.")

        # Top topics
        topics = d.get("topics", {})
        if topics:
            top3 = sorted(topics, key=topics.get, reverse=True)[:3]
            insights.append(f"Tum zyada baat karte ho: {', '.join(top3)} ke baare mein.")

        # Style
        style = d.get("style", {})
        if style:
            if style.get("casual", 0) > style.get("formal", 0):
                insights.append("Tum casual style mein baat karte ho — friendly tone prefer karte ho.")
            else:
                insights.append("Tum formal style mein baat karte ho.")

            if style.get("short", 0) > style.get("detailed", 0):
                insights.append("Tum chhote aur seedhe jawab prefer karte ho.")
            else:
                insights.append("Tum detailed jawab prefer karte ho.")

        # Work sessions
        sessions = d.get("work_sessions", [])
        if sessions:
            avg_dur = sum(s["duration_min"] for s in sessions) / len(sessions)
            insights.append(f"Tumhara average focus session {int(avg_dur)} minute ka hota hai.")

        # Language
        lang = d.get("language_preference", "hinglish")
        insights.append(f"Tum zyada '{lang}' mein baat karte ho.")

        self.profile.set("insights", insights)
        return insights

    # ── Main: Process one message ────────────────────────────────────────────

    def process_message(self, text: str) -> dict:
        """Ek user message se sab kuch analyze karo."""
        now = self._now()

        # Update meta
        self.profile.set("last_seen", now.isoformat())
        # Fix: interactions ek int hai
        current = self.profile.get("interactions", 0)
        if isinstance(current, dict):
            current = current.get("count", 0)
        self.profile.set("interactions", current + 1)

        mood   = self.detect_mood(text)
        style  = self.detect_style(text)
        topics = self.detect_topics(text)
        slot   = self.record_activity()
        lang   = self.detect_language(text)

        self.profile.save()

        return {
            "mood":   mood,
            "style":  style,
            "topics": topics,
            "slot":   slot,
            "lang":   lang,
        }


# ─────────────────────────────────────────────
# SINGLETON
# ─────────────────────────────────────────────

_profile  = UserProfile()
_analyzer = BehaviorAnalyzer(_profile)


# ─────────────────────────────────────────────
# LIVEKIT FUNCTION TOOLS
# ─────────────────────────────────────────────

@function_tool()
async def analyze_user_message(message: str) -> str:
    """
    User ke message ko silently analyze karo aur profile update karo.
    Har user message ke baad call karo — mood, style, topic, routine track hoga.

    Args:
        message: User ka latest message (jo unhone abhi bola/likha)

    Returns:
        Quick analysis summary — assistant ke context ke liye.
    """
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _analyzer.process_message, message)

    mood_emoji = {
        "happy": "😊", "stressed": "😰", "busy": "⚡",
        "neutral": "😐", "tired": "😴"
    }.get(result["mood"], "😐")

    topics_str = ", ".join(result["topics"]) if result["topics"] else "general"

    return (
        f"Profile updated.\n"
        f"Mood: {result['mood']} {mood_emoji}\n"
        f"Style: {result['style']}\n"
        f"Topics: {topics_str}\n"
        f"Active time: {result['slot']}\n"
        f"Language: {result['lang']}"
    )


@function_tool()
async def get_user_profile_summary() -> str:
    """
    User ka complete behavior profile dikhao —
    mood trends, habits, interests, routine, aur insights.

    Returns:
        Human-readable profile summary.
    """
    loop = asyncio.get_event_loop()
    insights = await loop.run_in_executor(None, _analyzer.generate_insights)

    d = _profile.data

    # Top topics
    topics = d.get("topics", {})
    top_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:5]
    topics_str = ", ".join(f"{t}({c})" for t, c in top_topics) if top_topics else "abhi tak kuch nahi"

    # Mood summary
    moods = d.get("mood_history", {})
    mood_str = ", ".join(f"{m}:{c}" for m, c in moods.items() if c > 0) or "neutral"

    # Time slots
    slots = d.get("time_slots", {})
    slot_str = ", ".join(f"{s}:{c}" for s, c in slots.items() if c > 0) or "abhi tak kuch nahi"

    # Style
    style = d.get("style", {})
    dominant_style = max(style, key=style.get) if style and any(style.values()) else "unknown"

    # Work sessions
    sessions = d.get("work_sessions", [])
    if sessions:
        avg_dur = int(sum(s["duration_min"] for s in sessions) / len(sessions))
        work_str = f"{len(sessions)} sessions, avg {avg_dur} min"
    else:
        work_str = "abhi tak koi session track nahi hua"

    name = d.get("name") or "User"
    interactions = d.get("interactions", 0)
    first_seen   = d.get("first_seen", "?")
    lang         = d.get("language_preference", "hinglish")

    summary = f"""
👤 USER PROFILE — {name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 First seen:     {first_seen}
💬 Interactions:   {interactions}
🌐 Language:       {lang}
🎭 Dominant style: {dominant_style}

😊 MOOD HISTORY
{mood_str}

⏰ ACTIVE TIME SLOTS
{slot_str}

🔖 TOP INTERESTS
{topics_str}

💼 WORK SESSIONS
{work_str}

💡 INSIGHTS
""".strip()

    for i, insight in enumerate(insights, 1):
        summary += f"\n  {i}. {insight}"

    return summary


@function_tool()
async def get_personalized_greeting() -> str:
    """
    User ke profile ke hisaab se personalized greeting banao.
    Din ke time, mood history, aur style ke hisaab se adjust hoti hai.

    Returns:
        Personalized greeting string jo assistant use kar sakta hai.
    """
    d    = _profile.data
    now  = datetime.now(ZoneInfo(TIMEZONE))
    hour = now.hour
    name = d.get("name", "")

    # Time-based greeting
    if 5  <= hour < 12: time_greet = "Good morning"
    elif 12 <= hour < 17: time_greet = "Good afternoon"
    elif 17 <= hour < 21: time_greet = "Good evening"
    else:                  time_greet = "Hey"

    # Style adjust
    style = d.get("style", {})
    casual_count = style.get("casual", 0)
    formal_count = style.get("formal", 0)

    if casual_count > formal_count:
        if hour >= 22 or hour < 5:
            time_greet = "Arre yaar, itni raat ko?"
        elif 5 <= hour < 12:
            time_greet = "Subah subah aa gaye!"

    # Mood-based addition
    moods      = d.get("mood_history", {})
    top_mood   = max(moods, key=moods.get) if moods and any(moods.values()) else "neutral"
    mood_extra = {
        "stressed": " Lagta hai kafi busy rehte ho — koi cheez mein help chahiye?",
        "tired":    " Thoda rest bhi lena chahiye kabhi kabhi 😊",
        "happy":    " Tumse baat karke hamesha achha lagta hai!",
        "busy":     " Seedha kaam ki baat karte hain —",
        "neutral":  "",
    }.get(top_mood, "")

    name_part = f", {name}" if name else ""
    return f"{time_greet}{name_part}!{mood_extra}"


@function_tool()
async def set_user_name(name: str) -> str:
    """
    User ka naam profile mein save karo.

    Args:
        name: User ka naam

    Returns:
        Confirmation message.
    """
    _profile.set("name", name.strip())
    _profile.save()
    return f"Naam save ho gaya: {name}. Ab main tumhe {name} bulaunga!"


@function_tool()
async def start_focus_session() -> str:
    """
    Focus/work session start karo — track hoga ki kitna kaam kiya.

    Returns:
        Session start confirmation.
    """
    _analyzer.start_work_session()
    now = datetime.now(ZoneInfo(TIMEZONE))
    return f"Focus session shuru! Time: {now.strftime('%H:%M')} — jab kaam khatam ho to mujhe batana."


@function_tool()
async def end_focus_session() -> str:
    """
    Focus/work session khatam karo aur duration track karo.

    Returns:
        Session summary — kitni der kaam kiya.
    """
    loop = asyncio.get_event_loop()
    duration = await loop.run_in_executor(None, _analyzer.end_work_session)
    _profile.save()

    if duration is None:
        return "Koi active focus session nahi mila. Pehle 'start focus session' bolo."

    if duration < 25:
        tip = "Thoda aur karo — 25 min ka Pomodoro best hota hai! 🍅"
    elif duration < 60:
        tip = "Achha session tha! Thoda break lo. ☕"
    else:
        tip = "Kaafi lamba session tha — zaroor break lo aur paani piyo! 💧"

    return f"Session khatam! Tumne {duration} minute focus kiya.\n{tip}"


@function_tool()
async def get_behavior_insight() -> str:
    """
    User ke behavior se ek actionable insight do —
    kab productive hain, kya improve kar sakte hain.

    Returns:
        Personalized behavior insight.
    """
    loop    = asyncio.get_event_loop()
    insights = await loop.run_in_executor(None, _analyzer.generate_insights)
    _profile.save()

    d = _profile.data

    # Peak productivity slot
    slots    = d.get("time_slots", {})
    peak     = max(slots, key=slots.get) if slots and any(slots.values()) else None

    # Recent mood trend (last 7 days)
    daily_mood  = d.get("daily_mood", {})
    recent_moods = list(daily_mood.values())[-7:] if daily_mood else []
    mood_counter = Counter(recent_moods)
    dominant_recent = mood_counter.most_common(1)[0][0] if mood_counter else "neutral"

    # Work session avg
    sessions = d.get("work_sessions", [])
    avg_dur  = int(sum(s["duration_min"] for s in sessions) / len(sessions)) if sessions else 0

    # Build insight
    lines = ["🧠 BEHAVIOR INSIGHT\n"]

    if peak:
        lines.append(f"⏰ Tumhara peak time '{peak}' hai — important kaam tab karo.")

    if dominant_recent == "stressed":
        lines.append("😰 Pichle 7 din mein tumhara mood zyada stressed raha — kaam ka load check karo.")
    elif dominant_recent == "happy":
        lines.append("😊 Pichle hafte ka mood achha raha — aise hi chalte raho!")
    elif dominant_recent == "tired":
        lines.append("😴 Lately thakawat zyada lag rahi hai — neend aur rest prioritize karo.")

    if avg_dur > 0:
        if avg_dur < 20:
            lines.append(f"💼 Tumhare focus sessions ({avg_dur} min avg) bahut chhote hain — longer blocks try karo.")
        elif avg_dur > 90:
            lines.append(f"💼 Tumhare focus sessions ({avg_dur} min avg) bahut lambe hain — beech mein breaks lo.")
        else:
            lines.append(f"💼 Focus sessions ({avg_dur} min avg) — bilkul sahi range mein hain!")

    topics = d.get("topics", {})
    if topics:
        top = sorted(topics, key=topics.get, reverse=True)[0]
        lines.append(f"🔖 Tumhara main interest area: '{top}' — isme aur gehraai se kaam kar sakte ho.")

    lines.append("\n💡 Top insight:")
    lines.append(insights[0] if insights else "Abhi aur data chahiye better insight ke liye.")

    return "\n".join(lines)


@function_tool()
async def reset_user_profile() -> str:
    """
    User profile ko completely reset karo — sab data clear ho jaayega.
    Sirf tab use karo jab user explicitly bole.

    Returns:
        Reset confirmation.
    """
    if PROFILE_PATH.exists():
        PROFILE_PATH.unlink()

    # Reload fresh
    global _profile, _analyzer
    _profile  = UserProfile()
    _analyzer = BehaviorAnalyzer(_profile)

    return "Profile reset ho gayi. Fresh start — ab naya profile build hoga conversations se."