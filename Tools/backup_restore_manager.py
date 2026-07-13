import os
import shutil
import subprocess
from datetime import datetime
from typing import Literal, Optional
from livekit.agents import function_tool

@function_tool()
async def backup_restore_manager(
    action: Literal["create_restore_point", "backup_folder"],
    source_dir: Optional[str] = None,
    dest_dir: Optional[str] = None,
    description: Optional[str] = None
) -> str:
    """
    Manages system backups, directories compression, and triggers Windows Restore Points.

    Args:
        action: "create_restore_point" to check or create a system restore checkpoint,
                "backup_folder" to archive/zip a local directory.
        source_dir: Source folder path to back up.
        dest_dir: Destination folder path to save backup archive.
        description: Description tag for the system restore point.
    """
    try:
        if action == "create_restore_point":
            desc = description or f"NIK_Restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Windows Checkpoint-Computer requires admin privileges.
            # We execute it via PowerShell.
            cmd = f'powershell -Command "Checkpoint-Computer -Description \'{desc}\' -RestorePointType \'MODIFY_SETTINGS\' -ErrorAction Stop"'
            
            # Start process
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if proc.returncode == 0:
                return f"✅ Windows System Restore Point '{desc}' successfully created."
            else:
                err = proc.stderr.strip()
                if "Admin" in err or "privilege" in err or "permission" in err or proc.returncode != 0:
                    return (
                        f"❌ System Restore Point creation failed.\n"
                        f"Please run console as Administrator to allow checkpoints.\n"
                        f"Command output: {err or proc.stdout}"
                    )
                return f"❌ Failed to create restore point: {err}"
                
        elif action == "backup_folder":
            if not source_dir or not dest_dir:
                return "❌ Please specify both source_dir and dest_dir for folder backup."
            
            if not os.path.exists(source_dir):
                return f"❌ Source folder '{source_dir}' does not exist."
            
            # Ensure dest_dir exists
            os.makedirs(dest_dir, exist_ok=True)
            
            base_name = os.path.basename(os.path.normpath(source_dir))
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"{base_name}_backup_{timestamp}"
            dest_filepath = os.path.join(dest_dir, backup_filename)
            
            # Perform archive creation (zip format)
            shutil.make_archive(dest_filepath, 'zip', source_dir)
            return f"✅ Directory '{source_dir}' has been successfully backed up to '{dest_filepath}.zip'."

    except Exception as e:
        return f"❌ Backup & Restore manager failed: {str(e)}"
