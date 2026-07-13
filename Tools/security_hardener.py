import winreg
import subprocess
from typing import Literal
from livekit.agents import function_tool

@function_tool()
async def security_hardener(action: Literal["audit_accounts", "harden_system"]) -> str:
    """
    Audits administrative user groups, manages account flags, and disables insecure remote access (RDP).

    Args:
        action: "audit_accounts" to list local accounts and administrator members,
                "harden_system" to disable Remote Desktop and close common backdoor avenues.
    """
    try:
        if action == "audit_accounts":
            # List local users
            proc_users = subprocess.run("net user", shell=True, capture_output=True, text=True)
            # List administrators
            proc_admins = subprocess.run("net localgroup administrators", shell=True, capture_output=True, text=True)
            
            report = "🛡️ **Account Security Audit:**\n\n"
            if proc_users.returncode == 0:
                report += f"👤 **Local User Accounts:**\n{proc_users.stdout.strip()}\n\n"
            else:
                report += "❌ Failed to retrieve local user accounts.\n\n"
                
            if proc_admins.returncode == 0:
                report += f"🔑 **Members of Administrators Group:**\n{proc_admins.stdout.strip()}\n"
            else:
                report += "❌ Failed to retrieve Administrators group members.\n"
            return report
            
        elif action == "harden_system":
            # 1. Disable RDP
            # Registry path: HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server
            # Key: fDenyTSConnections (Set to 1)
            rdp_success = False
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, 
                    r"SYSTEM\CurrentControlSet\Control\Terminal Server", 
                    0, 
                    winreg.KEY_SET_VALUE
                )
                winreg.SetValueEx(key, "fDenyTSConnections", 0, winreg.REG_DWORD, 1)
                winreg.CloseKey(key)
                rdp_success = True
            except Exception as e:
                rdp_err = str(e)
            
            # 2. Disable Remote Registry Service
            srv_success = False
            try:
                subprocess.run("sc config RemoteRegistry start= disabled", shell=True, capture_output=True)
                subprocess.run("net stop RemoteRegistry", shell=True, capture_output=True)
                srv_success = True
            except Exception:
                pass
                
            report = "🛡️ **System Hardening Status:**\n"
            if rdp_success:
                report += "- ✅ **Remote Desktop (RDP):** Disabled successfully (blocked inbound RDP requests).\n"
            else:
                report += f"- ❌ **Remote Desktop (RDP):** Failed to set Registry policy (requires admin rights). Error: {rdp_err}\n"
                
            if srv_success:
                report += "- ✅ **Remote Registry Service:** Stopped and Disabled successfully.\n"
            else:
                report += "- ❌ **Remote Registry Service:** Disable command failed.\n"
                
            return report

    except Exception as e:
        return f"❌ Security hardener failure: {str(e)}"
