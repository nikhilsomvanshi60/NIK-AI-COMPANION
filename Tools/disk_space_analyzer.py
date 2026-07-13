import os
import shutil
from typing import Literal, Optional
from livekit.agents import function_tool

def format_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

@function_tool()
async def disk_space_analyzer(
    action: Literal["check_drive", "scan_largest_files", "scan_largest_folders"],
    path: str,
    threshold_mb: int = 100
) -> str:
    """
    Analyzes disk storage distribution, checks partition status, and identifies large storage-consuming items.

    Args:
        action: "check_drive" to query disk usage stats of partition,
                "scan_largest_files" to list files in a folder exceeding threshold_mb,
                "scan_largest_folders" to scan and list largest subfolders in path.
        path: Path directory or drive letter to inspect (e.g. "C:\\" or "D:\\sakhi")
        threshold_mb: Size threshold filter in megabytes.
    """
    try:
        if action == "check_drive":
            # Normalize path to drive letter or root path
            drive = os.path.splitdrive(path)[0] or path
            if not drive.endswith("\\"):
                drive += "\\"
            
            total, used, free = shutil.disk_usage(drive)
            used_pct = round((used / total) * 100, 1)
            free_pct = round((free / total) * 100, 1)
            
            return (
                f"💽 **Disk Space Info for {drive}:**\n"
                f"- **Total capacity:** {format_size(total)}\n"
                f"- **Used space:** {format_size(used)} ({used_pct}%)\n"
                f"- **Free space:** {format_size(free)} ({free_pct}%)\n"
            )
            
        elif action == "scan_largest_files":
            if not os.path.exists(path):
                return f"❌ Path '{path}' does not exist."
            
            threshold_bytes = threshold_mb * 1024 * 1024
            large_files = []
            
            for root, _, files in os.walk(path):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        sz = os.path.getsize(fp)
                        if sz >= threshold_bytes:
                            large_files.append((fp, sz))
                    except (OSError, FileNotFoundError):
                        continue
            
            if not large_files:
                return f"ℹ️ No files found exceeding {threshold_mb} MB in '{path}'."
                
            # Sort by size descending
            large_files.sort(key=lambda x: x[1], reverse=True)
            
            report = f"🔍 **Largest Files (> {threshold_mb} MB) in {path}:**\n\n"
            for fp, sz in large_files[:15]:
                report += f"- **{os.path.basename(fp)}** — {format_size(sz)}\n  Path: `{fp}`\n"
            return report
            
        elif action == "scan_largest_folders":
            if not os.path.exists(path):
                return f"❌ Path '{path}' does not exist."
                
            folder_sizes = []
            
            # Scan top-level folders in path
            try:
                items = os.listdir(path)
            except Exception as e:
                return f"❌ Failed to list items in directory: {str(e)}"
                
            for item in items:
                ip = os.path.join(path, item)
                if os.path.isdir(ip):
                    # Compute directory size
                    total_size = 0
                    try:
                        for root, _, files in os.walk(ip):
                            for f in files:
                                fp = os.path.join(root, f)
                                try:
                                    total_size += os.path.getsize(fp)
                                except OSError:
                                    continue
                        folder_sizes.append((ip, total_size))
                    except Exception:
                        continue
            
            if not folder_sizes:
                return f"ℹ️ No subfolders found or computed in '{path}'."
                
            folder_sizes.sort(key=lambda x: x[1], reverse=True)
            
            report = f"📂 **Largest Subfolders in {path}:**\n\n"
            for ip, sz in folder_sizes[:10]:
                report += f"- **{os.path.basename(ip)}** — {format_size(sz)} (`{ip}`)\n"
            return report
            
    except Exception as e:
        return f"❌ Disk space analysis failed: {str(e)}"
