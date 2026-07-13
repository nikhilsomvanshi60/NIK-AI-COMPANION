import win32gui
import win32process
import psutil
import time
import json
import os
from typing import Literal, Optional
from livekit.agents import function_tool

LOG_FILE = "focus_productivity_logs.json"

PRODUCTIVE_KEYWORDS = ["code", "visual studio", "python", "excel", "word", "powerpoint", "cmd", "powershell", "git", "github", "stack overflow", "notion"]
DISTRACTED_KEYWORDS = ["youtube", "facebook", "twitter", "instagram", "reddit", "netflix", "game", "steam", "discord", "spotify"]

def get_active_window_details():
    try:
        hwnd = win32gui.GetForegroundWindow()
        window_title = win32gui.GetWindowText(hwnd)
        if not window_title:
            return None, None
        
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        process_name = process.name()
        return window_title, process_name
    except Exception:
        return None, None

def classify_productivity(title: str, process_name: str) -> str:
    combined = (title + " " + process_name).lower()
    for kw in DISTRACTED_KEYWORDS:
        if kw in combined:
            return "Distracting"
    for kw in PRODUCTIVE_KEYWORDS:
        if kw in combined:
            return "Productive"
    return "Neutral"

@function_tool()
async def focus_productivity_tracker(action: Literal["get_active", "log_current", "get_stats"]) -> str:
    """
    Tracks and records the user's active window and logs focus stats (Productive vs Distracting).

    Args:
        action: "get_active" to get the current focus window, 
                "log_current" to write the current active window state to logs,
                "get_stats" to view focus stats report.
    """
    try:
        if action == "get_active":
            title, proc = get_active_window_details()
            if not title:
                return "ℹ️ currently no active window details detected."
            category = classify_productivity(title, proc)
            return f"🎯 **Active Window:** {title}\n⚙️ **Process:** {proc}\n🏷️ **Category:** {category}"
        
        elif action == "log_current":
            title, proc = get_active_window_details()
            if not title:
                return "❌ active window data copy failed or active window is empty."
            category = classify_productivity(title, proc)
            
            logs = []
            if os.path.exists(LOG_FILE):
                try:
                    with open(LOG_FILE, "r", encoding="utf-8") as f:
                        logs = json.load(f)
                except Exception:
                    pass
            
            logs.append({
                "timestamp": time.time(),
                "title": title,
                "process": proc,
                "category": category
            })
            
            # Keep last 100 entries
            logs = logs[-100:]
            
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=4)
                
            return f"✅ logged state: '{title}' ({category}) successfully."
            
        elif action == "get_stats":
            if not os.path.exists(LOG_FILE):
                return "ℹ️ Log database empty. Start logging focus states first."
            
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
                
            total = len(logs)
            if total == 0:
                return "ℹ️ Focus database is empty."
            
            prod_count = sum(1 for x in logs if x["category"] == "Productive")
            dist_count = sum(1 for x in logs if x["category"] == "Distracting")
            neutral_count = sum(1 for x in logs if x["category"] == "Neutral")
            
            prod_pct = round((prod_count / total) * 100, 1)
            dist_pct = round((dist_count / total) * 100, 1)
            neutral_pct = round((neutral_count / total) * 100, 1)
            
            report = f"📊 **Focus & Productivity Report (Last {total} samples):**\n"
            report += f"- 🟢 **Productive Time:** {prod_pct}% ({prod_count} logs)\n"
            report += f"- 🔴 **Distracting Time:** {dist_pct}% ({dist_count} logs)\n"
            report += f"- 🟡 **Neutral Time:** {neutral_pct}% ({neutral_count} logs)\n\n"
            
            recent = logs[-5:]
            report += "📝 **Recent Windows:**\n"
            for r in reversed(recent):
                report += f"- {r['title']} ({r['category']})\n"
                
            return report
            
    except Exception as e:
        return f"❌ Focus tracker failed: {str(e)}"
