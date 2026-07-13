import os
import shutil
from typing import Optional
from livekit.agents import function_tool

@function_tool()
async def desktop_organizer(folder_path: Optional[str] = None) -> str:
    """
    Organizes messy directories (defaulting to user Desktop) by sorting files into subfolders by type.
    
    Args:
        folder_path: Path to clean/organize. If not provided, organizes user's Desktop.
        
    Returns:
        str: Success or error report in Hindi/English.
    """
    try:
        if not folder_path:
            # Default to User Desktop
            folder_path = os.path.join(os.path.expanduser("~"), "Desktop")
            
        if not os.path.exists(folder_path):
            return f"❌ फ़ोल्डर मार्ग '{folder_path}' मौजूद नहीं है।"
            
        extensions_map = {
            "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg"],
            "Documents": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".xls", ".pptx", ".ppt", ".csv"],
            "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
            "Videos": [".mp4", ".mkv", ".avi", ".mov"],
            "Audio": [".mp3", ".wav", ".aac", ".flac"],
            "Executables": [".exe", ".msi"]
        }
        
        moved_count = 0
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            
            if os.path.isdir(file_path):
                continue
                
            _, ext = os.path.splitext(filename)
            ext = ext.lower()
            
            dest_dir = "Others"
            for category, exts in extensions_map.items():
                if ext in exts:
                    dest_dir = category
                    break
                    
            dest_folder = os.path.join(folder_path, dest_dir)
            if not os.path.exists(dest_folder):
                os.makedirs(dest_folder)
                
            shutil.move(file_path, os.path.join(dest_folder, filename))
            moved_count += 1
            
        if moved_count > 0:
            return f"✅ **डेस्कटॉप/फ़ोल्डर व्यवस्थित किया गया:**\n- {moved_count} फाइलों को उनके प्रकार (Images, Documents आदि) के अनुसार फ़ोल्डर्स में वर्गीकृत किया गया है।"
        return "🧹 फ़ोल्डर पहले से ही साफ और व्यवस्थित है।"
        
    except Exception as e:
        return f"❌ व्यवस्थित करने में त्रुटि: {str(e)}"
