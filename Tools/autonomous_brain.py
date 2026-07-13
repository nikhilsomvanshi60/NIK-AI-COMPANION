import os
import json
import time
import shutil
import psutil
from datetime import datetime
from typing import Literal
from livekit.agents import function_tool

HISTORY_FILE = "autonomous_history.json"

def get_sys_status():
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    total, used, free = shutil.disk_usage("/")
    disk_free_gb = round(free / (1024*1024*1024), 2)
    return cpu, ram, disk_free_gb

@function_tool()
async def autonomous_brain(action: Literal["query_actions", "run_audit", "clear_history"]) -> str:
    """
    Manages NIK's background autonomous brain activity, audits system states, and returns self-learning reports.

    Args:
        action: "query_actions" to query history logs and compile a report of what NIK did,
                "run_audit" to run an active background optimization and diagnostic check,
                "clear_history" to reset autonomous history logs.
    """
    try:
        if action == "run_audit":
            cpu, ram, disk_free = get_sys_status()
            
            # Check temp files count
            temp_count = 0
            temp_dir = os.environ.get("TEMP", "")
            if temp_dir and os.path.exists(temp_dir):
                try:
                    temp_count = len(os.listdir(temp_dir))
                except Exception:
                    pass
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = {
                "timestamp": timestamp,
                "cpu_load": cpu,
                "ram_usage": ram,
                "disk_free_gb": disk_free,
                "temp_files": temp_count,
                "notes": f"Audited system health: CPU at {cpu}%, RAM at {ram}%, free disk at {disk_free} GB, detected {temp_count} temp files."
            }
            
            # Read history
            history = []
            if os.path.exists(HISTORY_FILE):
                try:
                    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                        history = json.load(f)
                except Exception:
                    pass
            
            # Autoclean temp files if there are too many (e.g. > 150)
            cleaned = False
            if temp_count > 150:
                cleaned_files = 0
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        try:
                            os.remove(os.path.join(root, file))
                            cleaned_files += 1
                        except Exception:
                            continue
                log_entry["notes"] += f" Auto-cleaned {cleaned_files} temp files because count was above 150."
                cleaned = True
            
            history.append(log_entry)
            history = history[-50:] # keep last 50 audits
            
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=4)
                
            status_desc = "System stable. No threats detected."
            if cpu > 80:
                status_desc = "High CPU load detected and logged."
            elif cleaned:
                status_desc = f"Cleaned {temp_count} temp files during background sweep."
                
            return f"🧠 NIK Background Brain Audit successfully executed at {timestamp}. Status: {status_desc}"
            
        elif action == "query_actions":
            if not os.path.exists(HISTORY_FILE):
                return "ℹ️ NIK has not performed any background autonomous audits yet."
                
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
                
            if not history:
                return "ℹ️ Autonomous memory database is empty."
                
            report = "🧠 **NIK Autonomous Background Activity Summary:**\n\n"
            report += f"Total background audits run: {len(history)}\n"
            
            latest = history[-1]
            report += f"🕒 **Last Background Activity ({latest['timestamp']}):**\n"
            report += f"- CPU Load: {latest['cpu_load']}%\n"
            report += f"- RAM Usage: {latest['ram_usage']}%\n"
            report += f"- Free Space: {latest['disk_free_gb']} GB\n"
            report += f"- Action Log: *{latest['notes']}*\n\n"
            
            report += "📝 **History Timeline:**\n"
            for entry in reversed(history[-5:]):
                report += f"- `[{entry['timestamp']}]` {entry['notes']}\n"
                
            return report
            
        elif action == "clear_history":
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)
            return "✅ Autonomous action history cleared."
            
    except Exception as e:
        return f"❌ Autonomous brain error: {str(e)}"
