from livekit.agents import function_tool
from typing import Literal
import tools

@function_tool()
async def app_lock(action: Literal["lock", "unlock"]) -> str:
    """
    Locks or unlocks the NIK voice assistant interface.
    
    Args:
        action: Either "lock" to secure the assistant window or "unlock" to restore access.
        
    Returns:
        str: Status message confirmation.
    """
    try:
        is_locked = (action == "lock")
        if tools.bridge_instance:
            tools.bridge_instance.lockSignal.emit(is_locked)
            status_text = "लॉक" if is_locked else "अनलॉक"
            return f"✅ असिस्टेंट को सफलतापूर्वक {status_text} कर दिया गया है।"
        else:
            return "❌ असिस्टेंट का इंटरफ़ेस अभी सक्रिय नहीं है।"
    except Exception as e:
        return f"❌ त्रुटि: {str(e)}"
