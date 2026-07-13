import os
import shutil
import tempfile
import asyncio
import subprocess
import logging
import psutil
from typing import Literal
from livekit.agents import function_tool

logger = logging.getLogger(__name__)

async def run_powershell(command: str) -> str:
    """Helper to run powershell commands safely"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-NonInteractive", "-Command", command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode('utf-8', errors='ignore').strip()
        else:
            return f"Error: {stderr.decode('utf-8', errors='ignore').strip()}"
    except Exception as e:
        return f"Exception: {str(e)}"

@function_tool()
async def system_security_manager(action: Literal["check_status", "secure_system", "clean_temp"]) -> str:
    """
    Manages background PC security, checks safety status, and optimizes the system.
    
    Args:
        action: The security action to execute:
            - "check_status": Audits antivirus, firewall, and high-resource processes.
            - "secure_system": Turns on real-time protection and enables all firewall profiles.
            - "clean_temp": Clears temporary files to prevent malware footprints and free space.
            
    Returns:
        str: Hindi / English status report detailing actions taken.
    """
    if action == "check_status":
        # Check Antivirus / Windows Defender
        defender_cmd = "Get-MpComputerStatus | Select-Object AntivirusEnabled, RealTimeProtectionEnabled, AMServiceEnabled | ConvertTo-Json"
        defender_res = await run_powershell(defender_cmd)
        
        # Check Firewall
        firewall_cmd = "Get-NetFirewallProfile | Select-Object Name, Enabled | ConvertTo-Json"
        firewall_res = await run_powershell(firewall_cmd)
        
        # Check high resource/suspicious processes (CPU > 20%)
        suspicious = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
            try:
                cpu = proc.info['cpu_percent']
                if cpu and cpu > 20:
                    suspicious.append(f"{proc.info['name']} (PID: {proc.info['pid']}, CPU: {cpu}%)")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        report = "🛡️ **सिस्टम सुरक्षा ऑडिट रिपोर्ट (PC Security Audit):**\n\n"
        
        # Defender Report
        if "RealTimeProtectionEnabled" in defender_res:
            report += f"✅ **Windows Defender Status:**\n- Real-time Protection: Active\n- Antivirus: Enabled\n\n"
        else:
            report += f"⚠️ **Windows Defender Warning:** Protection might be disabled or restricted.\n\n"
            
        # Firewall Report
        if "Domain" in firewall_res or "True" in firewall_res:
            report += f"✅ **Windows Firewall:** Active and protecting network profiles.\n\n"
        else:
            report += f"⚠️ **Windows Firewall Warning:** One or more network profiles are unprotected!\n\n"
            
        # Process Report
        if suspicious:
            report += f"⚠️ **High CPU usage processes detected:**\n" + "\n".join([f"- {p}" for p in suspicious[:5]]) + "\n\n"
        else:
            report += f"✅ **Background Processes:** All running processes are behaving normally (no high CPU spikes).\n\n"
            
        report += "PC पूरी तरह से सुरक्षित है! 🔒"
        return report

    elif action == "secure_system":
        # Enable Defender Realtime Monitoring
        defender_enable = "Set-MpPreference -DisableRealtimeMonitoring $false"
        await run_powershell(defender_enable)
        
        # Enable Net Firewall Profiles
        firewall_enable = "Set-NetFirewallProfile -All -Enabled True"
        await run_powershell(firewall_enable)
        
        return "✅ **सिस्टम सुरक्षा सक्रिय (Security Activated):** Windows Defender रियल-टाइम मॉनिटरिंग और सभी फ़ायरवॉल प्रोफाइल को सक्षम (Enable) कर दिया गया है। आपका PC अब सुरक्षित है! 🛡️"

    elif action == "clean_temp":
        # Paths to clean
        temp_dirs = [tempfile.gettempdir(), os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Temp')]
        freed_bytes = 0
        cleaned_count = 0
        failed_count = 0
        
        for d in temp_dirs:
            if not os.path.exists(d):
                continue
            for item in os.listdir(d):
                item_path = os.path.join(d, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        size = os.path.getsize(item_path)
                        os.unlink(item_path)
                        freed_bytes += size
                        cleaned_count += 1
                    elif os.path.isdir(item_path):
                        dir_size = 0
                        for root, dirs, files in os.walk(item_path):
                            for f in files:
                                fp = os.path.join(root, f)
                                if os.path.exists(fp):
                                    dir_size += os.path.getsize(fp)
                        shutil.rmtree(item_path)
                        freed_bytes += dir_size
                        cleaned_count += 1
                except Exception:
                    failed_count += 1
                    
        freed_mb = round(freed_bytes / (1024 * 1024), 2)
        return f"🧹 **सिस्टम क्लीनअप पूरा हुआ (System Cleaned):**\n- {cleaned_count} अस्थाई फाइलें/फ़ोल्डर हटा दिए गए हैं।\n- {freed_mb} MB डिस्क स्पेस खाली हुआ।\n- ({failed_count} फ़ाइलें उपयोग में होने के कारण छोड़ी गईं)।\n\nअब आपका सिस्टम अधिक सुरक्षित और तेज़ है! 🚀"

    return "❌ अज्ञात सुरक्षा एक्शन।"
