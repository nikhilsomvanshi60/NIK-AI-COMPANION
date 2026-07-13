import psutil
import os
from typing import Literal
from livekit.agents import function_tool

# Binary spoofing target blacklist (case-insensitive)
COMMON_SPOOF_NAMES = ["svch0st", "lsasss", "svchostt", "winlogont", "winlogonn", "serviceses", "explorerer"]
SUSPICIOUS_PATHS = ["temp", "appdata", "downloads", "programdata", "localappdata"]

@function_tool()
async def suspicious_process_scanner(action: Literal["scan_running"]) -> str:
    """
    Scans currently executing processes for path violations and name spoofing indicators.

    Args:
        action: "scan_running" to audit execution paths and check binary names.
    """
    try:
        if action == "scan_running":
            suspicious = []
            active_list = []
            
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    pinfo = proc.info
                    name = pinfo['name']
                    exe = pinfo['exe']
                    pid = pinfo['pid']
                    
                    if not exe or not name:
                        continue
                    
                    name_lower = name.lower()
                    exe_lower = exe.lower()
                    
                    # 1. Check Spoofed System Names
                    spoofed = False
                    for target in COMMON_SPOOF_NAMES:
                        if target in name_lower:
                            spoofed = True
                            
                    # 2. Check Execution out of Suspicious Folders
                    bad_path = False
                    for path in SUSPICIOUS_PATHS:
                        # Ensure we check directory segments
                        if f"\\{path}\\" in exe_lower or f"/{path}/" in exe_lower:
                            # Verify if it's not a common legitimate app (like Teams, Chrome, Discord which run from AppData)
                            # Web browsers and electron apps run in appdata, we list them but flag temp/downloads with higher risk
                            bad_path = True
                            
                    if spoofed or bad_path:
                        risk = "High" if spoofed or "temp" in exe_lower or "downloads" in exe_lower else "Medium"
                        suspicious.append({
                            "pid": pid,
                            "name": name,
                            "exe": exe,
                            "reason": "Spoofed binary name" if spoofed else f"Runs from restricted path ({exe})",
                            "risk": risk
                        })
                    
                    active_list.append(pinfo)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if not suspicious:
                return f"🛡️ **Suspicious Process Scan:** Clean. Scanned {len(active_list)} processes; no abnormal paths or spoofed binary names detected."
                
            report = "🚨 **SUSPICIOUS PROCESS SCAN ALERTS:**\n\n"
            for s in suspicious:
                report += (
                    f"- **{s['name']}** (PID: {s['pid']}) — [Risk: **{s['risk']}**]\n"
                    f"  Reason: {s['reason']}\n"
                    f"  File Path: `{s['exe']}`\n\n"
                )
            
            report += "*Note: Legitimate applications like Slack, Discord, Chrome, or Teams frequently update/run from LocalAppData. Double-check any high-risk files in Temp/Downloads.*"
            return report

    except Exception as e:
        return f"❌ Suspicious process scanner error: {str(e)}"
