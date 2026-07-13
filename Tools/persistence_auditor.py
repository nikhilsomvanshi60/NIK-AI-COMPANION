import subprocess
import winreg
from typing import Literal
from livekit.agents import function_tool

REG_PATHS = [
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce")
]

@function_tool()
async def persistence_auditor(action: Literal["audit_tasks", "audit_registry_autostart"]) -> str:
    """
    Scans for persistence mechanisms (such as custom startup registry values or scheduled tasks).

    Args:
        action: "audit_tasks" to scan Windows Task Scheduler for suspicious custom actions,
                "audit_registry_autostart" to perform deep inspection on all registry autostart values.
    """
    try:
        if action == "audit_tasks":
            # Run PowerShell command to extract scheduled tasks
            # We filter for tasks that execute binaries/scripts in non-system paths (AppData, Temp, Users, etc.)
            cmd = (
                "powershell -Command \""
                "Get-ScheduledTask | "
                "Where-Object {$_.State -ne 'Disabled' -and $_.TaskPath -notlike '\\Microsoft*'} | "
                "Select-Object TaskName, TaskPath, @{Name='Action';Expression={$_.Actions.Execute + ' ' + $_.Actions.Arguments}} | "
                "ConvertFrom-Json | "
                "ConvertTo-Json\""
            )
            
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if proc.returncode == 0 and proc.stdout.strip():
                import json
                try:
                    tasks = json.loads(proc.stdout)
                    if not isinstance(tasks, list):
                        tasks = [tasks]
                    
                    suspicious = []
                    report = "📋 **Custom/Non-Microsoft Scheduled Tasks:**\n\n"
                    for t in tasks:
                        name = t.get("TaskName", "Unknown")
                        path = t.get("TaskPath", "")
                        act = t.get("Action", "").strip()
                        
                        # Look for suspicious execution paths
                        combined = act.lower()
                        is_suspicious = any(x in combined for x in ["temp", "appdata", "localappdata", "wscript", "cscript", "cmd.exe /c", "powershell -e", "download"])
                        
                        item_str = f"- **{name}** (Path: `{path}`)\n  Action: `{act}`\n"
                        if is_suspicious:
                            suspicious.append(item_str)
                            item_str = f"⚠️ {item_str}"
                        
                        report += item_str
                        
                    if suspicious:
                        report = "🚨 **SUSPICIOUS SCHEDULED TASKS DETECTED:**\n" + "".join(suspicious) + "\n\n" + report
                    return report
                except Exception:
                    # Raw output fallback
                    return f"📋 **Active Custom Scheduled Tasks (Raw):**\n\n{proc.stdout[:800]}"
            return "🛡️ **Task Scheduler Audit:** No custom or non-Microsoft scheduled tasks running."
            
        elif action == "audit_registry_autostart":
            findings = []
            for hive, path in REG_PATHS:
                hive_name = "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM"
                type_name = "RunOnce" if "RunOnce" in path else "Run"
                try:
                    key = winreg.OpenKey(hive, path, 0, winreg.KEY_READ)
                    index = 0
                    while True:
                        try:
                            name, val, _ = winreg.EnumValue(key, index)
                            val_lower = val.lower()
                            
                            # Suspicious script triggers
                            is_sus = any(x in val_lower for x in ["temp", "appdata", "wscript", "cscript", "powershell -e", "cmd.exe", "mshta", "rundll32"])
                            findings.append({
                                "hive": hive_name,
                                "type": type_name,
                                "name": name,
                                "value": val,
                                "suspicious": is_sus
                            })
                            index += 1
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except Exception:
                    continue
                    
            if not findings:
                return "🛡️ **Registry Autostart Audit:** Clean. No persistence items detected."
                
            report = "🚀 **Autostart Registry Audit Details:**\n\n"
            alerts = []
            for f in findings:
                entry = f"- `[{f['hive']}\\{f['type']}]` **{f['name']}** ➔ `{f['value']}`\n"
                if f['suspicious']:
                    alerts.append(entry)
                report += entry
                
            if alerts:
                report = "🚨 **ALERT: Suspicious Registry Autostarts Detected!**\n" + "".join(alerts) + "\n\n" + report
            return report

    except Exception as e:
        return f"❌ Persistence auditor error: {str(e)}"
