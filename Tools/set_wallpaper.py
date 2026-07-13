import ctypes
import os
from tkinter import Tk, filedialog
from livekit.agents import function_tool


@function_tool()
async def set_wallpaper(confirm: str) -> str:
    """
    Change desktop wallpaper if user confirms.

    Args:
        confirm (str): 'yes' or 'no'

    Returns:
        str: Result message
    """

    try:
        confirm = confirm.lower().strip()

        if confirm in ["no", "n"]:
            return "❌ Thik hai, wallpaper change nahi kiya."

        if confirm not in ["yes", "y"]:
            return "⚠️ Please sirf 'yes' ya 'no' bolo."

        # hide tkinter main window
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        # open file dialog
        file_path = filedialog.askopenfilename(
            title="Wallpaper select karo",
            filetypes=[
                ("Image Files", "*.jpg *.jpeg *.png *.bmp")
            ]
        )

        if not file_path:
            return "❌ Koi image select nahi ki gayi."

        # set wallpaper
        ctypes.windll.user32.SystemParametersInfoW(
            20,
            0,
            file_path,
            3
        )

        return f"🔥 Wallpaper successfully set!\n📸 Image: {os.path.basename(file_path)}"

    except Exception as e:
        return f"❌ Wallpaper set karne mein error: {str(e)}"
