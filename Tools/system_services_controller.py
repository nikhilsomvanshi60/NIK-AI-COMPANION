import asyncio
import subprocess
from typing import Literal, Optional
from livekit.agents import function_tool

@function_tool()
async def system_services_controller(action: Literal["list", "start", "stop"], service_name: Optional[str] = None) -> str:
    """
    Monitors, starts, or terminates active Windows background system services.
    
    Args:
        action: "list" (lists critical running services), "start" (starts a service), "stop" (stops a service).
        service_name: Name of target Windows Service (e.g. "Spooler", "wuauserv").
        
    Examples: 
    - `system_services_controller("list")` - Lists all running services
    - `system_services_controller("start", "Spooler")` - Starts the Spooler service
    - `system_services_controller("stop", "Spooler")` - Stops the Spooler service
    - `system_services_controller("list")` - Lists all running services
    - `system_services_controller("start", "Spooler")` - Starts the Spooler service
    - `system_services_controller("stop", "Spooler")` - Stops the Spooler service
    - `system_services_controller("list")` - Lists all running services
    - `system_services_controller("start", "Spooler")` - Starts the Spooler service
    - `system_services_controller("stop", "Spooler")` - Stops the Spooler service

    Returns:
        str: Service execution status report.
    """
    try:
        if action == "list":
            cmd = "Get-Service | Where-Object {$_.Status -eq 'Running'} | Select-Object -First 10 DisplayName, Name, Status | ConvertTo-Json"
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-NonInteractive", "-Command", cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            res = stdout.decode('utf-8', errors='ignore').strip()
            return f"⚙️ **चल रही मुख्य विंडोज सेवाएं (Active Services):**\n\n{res}"
            
        elif action in ("start", "stop"):
            if not service_name:
                return "❌ कृपया सेवा (Service Name) प्रदान करें।"
                
            cmd = f"{'Start' if action == 'start' else 'Stop'}-Service -Name '{service_name}'"
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-NonInteractive", "-Command", cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                action_text = "शुरू" if action == "start" else "बंद"
                return f"✅ सेवा '{service_name}' को सफलतापूर्वक {action_text} कर दिया गया है।"
            else:
                return f"❌ त्रुटि (प्रशासक विशेषाधिकार आवश्यक हो सकते हैं): {stderr.decode('utf-8', errors='ignore').strip()}"
                
    except Exception as e:
        return f"❌ सेवा प्रबंधक त्रुटि: {str(e)}"
    return "❌ अज्ञात सेवा एक्शन।"
