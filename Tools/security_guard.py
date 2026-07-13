import os
import psutil
import socket
import winreg
from typing import Literal
from livekit.agents import function_tool

HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"

def get_registry_run_keys(hive, path):
    results = []
    try:
        key = winreg.OpenKey(hive, path, 0, winreg.KEY_READ)
        index = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, index)
                results.append((name, value))
                index += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception:
        pass
    return results

@function_tool()
async def security_guard(action: Literal["check_hosts", "check_startup_registry", "check_connections"]) -> str:
    """
    Audits local system security settings, monitors network sockets, and checks auto-start registry configurations.

    Args:
        action: "check_hosts" to audit the Windows etc/hosts file configuration,
                "check_startup_registry" to list programs starting automatically with Windows,
                "check_connections" to scan established external connections.
    """
    try:
        if action == "check_hosts":
            if not os.path.exists(HOSTS_PATH):
                return "❌ Windows etc/hosts file not found."
            
            with open(HOSTS_PATH, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            
            non_comments = []
            for line in lines:
                line_stripped = line.strip()
                if line_stripped and not line_stripped.startswith("#"):
                    non_comments.append(line_stripped)
            
            report = "🛡️ **Windows etc/hosts Redirect Audit:**\n"
            if not non_comments:
                report += "- No active custom host redirects or overrides detected (clean hosts file).\n"
            else:
                report += f"- Found {len(non_comments)} active line mappings:\n"
                for nc in non_comments:
                    report += f"  - `{nc}`\n"
            return report
            
        elif action == "check_startup_registry":
            hkcu_run = get_registry_run_keys(
                winreg.HKEY_CURRENT_USER, 
                r"Software\Microsoft\Windows\CurrentVersion\Run"
            )
            hklm_run = get_registry_run_keys(
                winreg.HKEY_LOCAL_MACHINE, 
                r"Software\Microsoft\Windows\CurrentVersion\Run"
            )
            
            report = "🚀 **Windows Startup Registry Items:**\n\n"
            
            report += "📁 **User Startup (HKCU):**\n"
            if not hkcu_run:
                report += "- No startup applications configured.\n"
            else:
                for name, val in hkcu_run:
                    report += f"- **{name}**: `{val}`\n"
            
            report += "\n📁 **System Startup (HKLM):**\n"
            if not hklm_run:
                report += "- No startup applications configured.\n"
            else:
                for name, val in hklm_run:
                    report += f"- **{name}**: `{val}`\n"
            return report
            
        elif action == "check_connections":
            connections = psutil.net_connections(kind='tcp')
            established = [c for c in connections if c.status == 'ESTABLISHED']
            
            report = f"🌐 **Active Established TCP Connections ({len(established)} found):**\n\n"
            for c in established[:15]:
                local = f"{c.laddr.ip}:{c.laddr.port}"
                remote = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "N/A"
                try:
                    p = psutil.Process(c.pid)
                    proc_desc = f"{p.name()} (PID: {c.pid})"
                except Exception:
                    proc_desc = f"Unknown (PID: {c.pid})"
                
                report += f"- **{proc_desc}** | Local: `{local}` ➔ Remote: `{remote}`\n"
                
            if len(established) > 15:
                report += f"\n*(Showing top 15 of {len(established)} connections)*"
            return report

    except Exception as e:
        return f"❌ Security Guard audit error: {str(e)}"
