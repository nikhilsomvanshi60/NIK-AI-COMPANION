import os
from typing import Literal, Optional
from livekit.agents import function_tool

SCRIPT_PATH = "reels_script.md"

@function_tool()
async def reels_storyteller(
    action: Literal["save_script", "read_script"],
    script_content: Optional[str] = None,
    topic: Optional[str] = None
) -> str:
    """
    Saves or reads generated Reels scripts (including hook, music, editing guide, hashtags).

    Args:
        action: "save_script" to write the reels content package to a local file,
                "read_script" to read the current reels script.
        script_content: Full text of the generated script package.
        topic: Topic of the reels video.
    """
    try:
        if action == "save_script":
            if not script_content:
                return "❌ कृपया सहेजने के लिए स्क्रिप्ट सामग्री (script_content) प्रदान करें।"
            
            header = f"# 🎬 REELS STORY SCRIPT: {topic or 'Untitled'}\n\n"
            full_data = header + script_content
            
            with open(SCRIPT_PATH, "w", encoding="utf-8") as f:
                f.write(full_data)
                
            return f"✅ Reels script for '{topic or 'Untitled'}' has been successfully saved to '{SCRIPT_PATH}'!"
            
        elif action == "read_script":
            if not os.path.exists(SCRIPT_PATH):
                return "ℹ️ No reels script found on disk. Generate and save one first."
                
            with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
                content = f.read()
            return f"📋 **Current Reels Script:**\n\n{content}"
            
    except Exception as e:
        return f"❌ Reels storyteller tool failed: {str(e)}"
