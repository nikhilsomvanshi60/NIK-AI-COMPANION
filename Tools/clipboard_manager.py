import pyperclip
from typing import Literal, Optional
from livekit.agents import function_tool

# Simple local memory registry for snippets
SNIPPETS = {
    "greeting": "Hello Boss! Hope you are having an amazing day. Let's build something awesome.",
    "python_template": "if __name__ == '__main__':\n    main()",
    "html_template": "<!DOCTYPE html>\n<html>\n<head><title>My App</title></head>\n<body></body>\n</html>"
}

@function_tool()
async def clipboard_manager(action: Literal["get", "set", "list_snippets"], text: Optional[str] = None, snippet_key: Optional[str] = None) -> str:
    """
    Manages system clipboard contents or retrieves predefined text/code snippets.
    
    Args:
        action: "get" to read clipboard, "set" to copy text/snippet to clipboard, "list_snippets" to list saved snippets.
        text: Custom text to copy to clipboard.
        snippet_key: Key of predefined snippet to copy (e.g. "python_template")
        
    Returns:
        str: Success or error report in Hindi/English.
    """
    try:
        if action == "get":
            val = pyperclip.paste()
            if val:
                return f"📋 **क्लिपबोर्ड सामग्री:**\n\n{val[:500]}"
            return "📋 क्लिपबोर्ड खाली है।"
            
        elif action == "set":
            if snippet_key and snippet_key in SNIPPETS:
                pyperclip.copy(SNIPPETS[snippet_key])
                return f"✅ स्निपेट '{snippet_key}' क्लिपबोर्ड पर कॉपी हो गया है।"
            if text:
                pyperclip.copy(text)
                return f"✅ टेक्स्ट क्लिपबोर्ड पर कॉपी हो गया है।"
            return "❌ कृपया कॉपी करने के लिए टेक्स्ट या स्निपेट की (Key) प्रदान करें।"
            
        elif action == "list_snippets":
            keys = ", ".join([f"'{k}'" for k in SNIPPETS.keys()])
            return f"📂 **उपलब्ध स्निपेट्स:**\n\n{keys}\n\nआप किसी भी स्निपेट को कॉपी करने के लिए बोल सकते हैं।"
            
    except Exception as e:
        return f"❌ क्लिपबोर्ड त्रुटि: {str(e)}"
