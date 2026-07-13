import asyncio
import subprocess
from typing import Literal
from livekit.agents import function_tool

@function_tool()
async def network_diagnostics(action: Literal["ping", "flush_dns", "active_ports"]) -> str:
    """
    Runs network checks, flushes DNS, and identifies active listening ports.
    
    Args:
        action: "ping" (tests internet speed/latency), "flush_dns" (clears DNS cache), "active_ports" (lists active connections).
        
    Returns:
        str: Success or error report in Hindi/English.
    """
    try:
        if action == "ping":
            proc = await asyncio.create_subprocess_exec(
                "ping", "8.8.8.8", "-n", "3",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            res = stdout.decode('utf-8', errors='ignore').strip()
            if "ms" in res:
                return f"📶 **नेटवर्क लेटेंसी टेस्ट (Ping Test):**\n\n{res}"
            return "❌ पिंग टेस्ट विफल रहा। कृपया इंटरनेट कनेक्शन की जांच करें।"
            
        elif action == "flush_dns":
            proc = await asyncio.create_subprocess_exec(
                "ipconfig", "/flushdns",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            res = stdout.decode('utf-8', errors='ignore').strip()
            return f"✅ **DNS Cache Flushed:** {res}"
            
        elif action == "active_ports":
            proc = await asyncio.create_subprocess_exec(
                "netstat", "-ano",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            res = stdout.decode('utf-8', errors='ignore').strip().split('\n')
            ports_summary = "\n".join(res[:10])
            return f"🔌 **सक्रिय नेटवर्क पोर्ट्स (Active Ports):**\n\n{ports_summary}"
            
    except Exception as e:
        return f"❌ नेटवर्क डायग्नोस्टिक्स त्रुटि: {str(e)}"
