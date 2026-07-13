import asyncio
import subprocess
from typing import Literal, Optional
from livekit.agents import function_tool

@function_tool()
async def wifi_manager(action: Literal["scan", "status", "connect"], ssid: Optional[str] = None) -> str:
    """
    Scans wireless networks, displays connection status, or connects to a Wi-Fi profile.
    
    Args:
        action: "scan" (list nearby Wi-Fi networks), "status" (check current connection), "connect" (connects to a profile).
        ssid: Name of wireless network SSID to connect to.
        
    Returns:
        str: Diagnostic or connection status report.
    """
    try:
        if action == "status":
            proc = await asyncio.create_subprocess_exec(
                "netsh", "wlan", "show", "interfaces",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            res = stdout.decode('utf-8', errors='ignore').strip()
            if "State" in res:
                return f"📶 **वाई-फाई कनेक्शन स्थिति (Wi-Fi Status):**\n\n{res}"
            return "❌ वाई-फाई इंटरफ़ेस सक्रिय नहीं है या डिस्कनेक्टेड है।"
            
        elif action == "scan":
            proc = await asyncio.create_subprocess_exec(
                "netsh", "wlan", "show", "networks",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            res = stdout.decode('utf-8', errors='ignore').strip()
            return f"🔍 **आस-पास के उपलब्ध वाई-फाई नेटवर्क:**\n\n{res}"
            
        elif action == "connect":
            if not ssid:
                return "❌ कृपया कनेक्ट करने के लिए वाई-फाई SSID प्रदान करें।"
            proc = await asyncio.create_subprocess_exec(
                "netsh", "wlan", "connect", f"name={ssid}",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            res = stdout.decode('utf-8', errors='ignore').strip()
            return f"✅ **कनेक्शन का प्रयास:** {res}"
            
    except Exception as e:
        return f"❌ वाई-फाई प्रबंधक त्रुटि: {str(e)}"
    return "❌ अज्ञात वाई-फाई एक्शन।"
