import os
import subprocess
from typing import Literal
from livekit.agents import function_tool

HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
POPULAR_DOMAINS = ["google.com", "facebook.com", "github.com", "bank", "paypal", "microsoft.com", "livekit.io"]

@function_tool()
async def intrusion_detector(action: Literal["audit_hosts", "check_dns", "defender_status"]) -> str:
    """
    Audits the operating system for indicators of compromise (IoC) and network configuration hijacks.

    Args:
        action: "audit_hosts" to perform checks on hosts file for phishing redirections,
                "check_dns" to list configured network DNS servers,
                "defender_status" to audit Windows Defender status.
    """
    try:
        if action == "audit_hosts":
            if not os.path.exists(HOSTS_PATH):
                return "🚨 WARNING: Windows etc/hosts file is missing! This is extremely unusual."
            
            hijacked = []
            with open(HOSTS_PATH, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split()
                        if len(parts) >= 2:
                            ip = parts[0]
                            domain = parts[1].lower()
                            # If a popular domain is redirected to local/weird IPs
                            for pop in POPULAR_DOMAINS:
                                if pop in domain:
                                    hijacked.append(f"{domain} redirected to {ip}")
            
            if hijacked:
                return (
                    "🚨 **SECURITY ALERT: Potential DNS/Hosts Redirect Hijack Detected!**\n"
                    "Following redirections were detected in your hosts file:\n" + 
                    "\n".join([f"- {h}" for h in hijacked]) + 
                    "\n\n*Action needed: Clean up hosts file immediately.*"
                )
            return "🛡️ **Hosts Integrity Audit:** No malicious redirection rules or hijacking detected."
            
        elif action == "check_dns":
            # Run ipconfig /all to get DNS details or use powershell
            cmd = "powershell -Command \"Get-DnsClientServerAddress -AddressFamily IPv4 | Select-Object InterfaceAlias, ServerAddresses\""
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if proc.returncode == 0:
                return f"🛡️ **Active Network DNS Servers:**\n\n{proc.stdout.strip()}"
            return f"❌ Failed to query DNS configuration: {proc.stderr}"
            
        elif action == "defender_status":
            cmd = "powershell -Command \"Get-MpComputerStatus | Select-Object AMServiceEnabled, RealTimeProtectionEnabled, BehaviorMonitorEnabled, AntispywareEnabled\""
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if proc.returncode == 0:
                lines = proc.stdout.strip().split("\n")
                report = "🛡️ **Windows Defender Core Security Status:**\n\n"
                for line in lines:
                    if line.strip():
                        report += f"- {line.strip()}\n"
                return report
            return f"❌ Failed to read Defender configuration: {proc.stderr}"
            
    except Exception as e:
        return f"❌ Intrusion detector error: {str(e)}"
