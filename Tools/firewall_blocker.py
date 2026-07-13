import asyncio
import subprocess
from typing import Literal, Optional
from livekit.agents import function_tool

@function_tool()
async def firewall_blocker(action: Literal["block", "unblock", "list_rules"], app_path: Optional[str] = None, rule_name: Optional[str] = None) -> str:
    """
    Blocks or unblocks specific applications from internet access using Windows Defender Firewall.
    
    Args:
        action: "block" (creates firewall block rule), "unblock" (removes rule), "list_rules" (lists NIK custom rules).
        app_path: Full path to target application executable (.exe).
        rule_name: Custom rule identification name.
        
    Returns:
        str: Success or error report.
    """
    try:
        r_name = rule_name or "NIK_Custom_Block_Rule"
        if action == "block":
            if not app_path:
                return "❌ कृपया ब्लॉक करने के लिए ऐप का पूर्ण पथ (Full Path to .exe) प्रदान करें।"
            
            cmd = f"New-NetFirewallRule -DisplayName '{r_name}' -Direction Outbound -Program '{app_path}' -Action Block"
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-NonInteractive", "-Command", cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return f"🛡️ **फ़ायरवॉल नियम जोड़ा गया:** '{app_path}' को सफलतापूर्वक इंटरनेट एक्सेस से ब्लॉक कर दिया गया है।"
            else:
                return f"❌ त्रुटि (प्रशासक विशेषाधिकार आवश्यक हो सकते हैं): {stderr.decode('utf-8', errors='ignore').strip()}"
                
        elif action == "unblock":
            cmd = f"Remove-NetFirewallRule -DisplayName '{r_name}'"
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-NonInteractive", "-Command", cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return f"🛡️ **फ़ायरवॉल नियम हटाया गया:** '{r_name}' फ़ायरवॉल नियम सफलतापूर्वक हटा दिया गया है।"
            else:
                return f"❌ नियम हटाने में त्रुटि: {stderr.decode('utf-8', errors='ignore').strip()}"
                
        elif action == "list_rules":
            cmd = "Get-NetFirewallRule -DisplayName 'NIK_Custom_*' | Select-Object DisplayName, Action, Enabled | ConvertTo-Json"
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-NonInteractive", "-Command", cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            res = stdout.decode('utf-8', errors='ignore').strip()
            if res:
                return f"📋 **NIK फ़ायरवॉल कस्टम नियम:**\n\n{res}"
            return "📋 कोई कस्टम NIK फ़ायरवॉल नियम नहीं मिला।"
            
    except Exception as e:
        return f"❌ फ़ायरवॉल प्रबंधक त्रुटि: {str(e)}"
    return "❌ अज्ञात फ़ायरवॉल एक्शन।"
