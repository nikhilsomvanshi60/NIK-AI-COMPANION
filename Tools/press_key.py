
from livekit.agents import function_tool
from livekit.agents import function_tool

@function_tool()
async def press_key(command: str) -> str:
    """
    Advanced keyboard controller.

    Examples:
    - press ctrl+a
    - press control alt delete
    - press enter 5 times
    - press shift tab
    """

    import pyautogui
    import asyncio
    import re

    try:
        command = command.lower().strip()

        key_map = {
            "control": "ctrl",
            "ctl": "ctrl",
            "escape": "esc",
            "return": "enter",
            "windows": "win",
            "command": "win",
            "option": "alt",
            "delete": "delete",
            "spacebar": "space"
        }

        # detect repeat
        repeat = 1
        match = re.search(r"(\d+)\s*(times|time)?", command)
        if match:
            repeat = int(match.group(1))
            command = command.replace(match.group(0), "").strip()

        # split keys
        if "+" in command:
            keys = command.split("+")
        else:
            keys = command.split()

        keys = [key_map.get(k.strip(), k.strip()) for k in keys]

        if len(keys) > 1:
            for _ in range(repeat):
                await asyncio.to_thread(pyautogui.hotkey, *keys)
        else:
            for _ in range(repeat):
                await asyncio.to_thread(pyautogui.press, keys[0])

        return f"✅ Executed key command: {' + '.join(keys)} x{repeat}"

    except Exception as e:
        return f"❌ Key press failed: {str(e)}"
    
import pyautogui
import time


@function_tool()
async def use_smart_clipboard(prompt: str, action: str, item_index: int = None) -> str:
    """
    Manages the Windows clipboard history.

    Args:
        prompt: The user's request, e.g., "open smart clipboard" or "paste the 4th item".
        action: The specific command, like "open_history" or "paste_item".
        item_index: The position of the clipboard item to paste (starting from 1).
                    This is optional and used only with "paste_item" action.

    Returns:
        A message confirming the action.
    """
    try:
        if action == "open_history":
            # Open Clipboard History (Win + V)
            pyautogui.hotkey("win", "v")
            return "📋 Clipboard history opened."

        elif action == "paste_item" and item_index is not None:
            if item_index < 1:
                return "⚠️ Error: Item index must be 1 or greater."

            # Open Clipboard History
            pyautogui.hotkey("win", "v")
            time.sleep(0.5)

            # Navigate with down arrow
            for _ in range(item_index - 1):
                pyautogui.press("down")

            # Select item
            pyautogui.press("enter")

            return f"📋 Pasted item at index {item_index} from clipboard history."

        else:
            return "⚠️ Invalid action or missing/invalid item index."
    except Exception as e:
        return f"❌ Smart clipboard operation failed: {str(e)}"