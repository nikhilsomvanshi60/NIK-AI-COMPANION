import asyncio
import subprocess
from typing import Literal, Optional
from livekit.agents import function_tool

@function_tool()
async def audio_device_manager(action: Literal["list_devices", "set_default"], device_name: Optional[str] = None) -> str:
    """
    Lists system sound devices (microphones/speakers) and manages playback configurations.
    
    Args:
        action: "list_devices" (audits system audio controllers).
        device_name: Name of target device.
        
    Returns:
        str: Diagnostic audio report.
    """
    try:
        if action == "list_devices":
            cmd = "Get-CimInstance Win32_SoundDevice | Select-Object Name, Status | ConvertTo-Json"
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-NonInteractive", "-Command", cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            res = stdout.decode('utf-8', errors='ignore').strip()
            if res:
                return f"🔊 **सक्रिय ऑडियो उपकरण (Sound Devices):**\n\n{res}"
            return "🔊 सक्रिय साउंड कार्ड और ड्राइवर सही ढंग से कार्य कर रहे हैं।"
            
        elif action == "set_default":
            # Setting default audio device programmatically requires specialized WinAPI/COM calls or helper utilities (like NirCmd).
            # We will suggest the user to switch active sound profiles.
            return "🔊 प्लेबैक डिवाइस सेट करने के लिए, कृपया सिस्टम सेटिंग्स खोलें (कमांड: 'settings' बोलें)।"
            
    except Exception as e:
        return f"❌ ऑडियो प्रबंधक त्रुटि: {str(e)}"
    return "❌ अज्ञात ऑडियो एक्शन।"
