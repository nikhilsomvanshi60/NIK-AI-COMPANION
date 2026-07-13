# =========================
# ENV + CORE IMPORTS
# =========================
try:
    import importlib
    dotenv = importlib.import_module("dotenv")
    dotenv.load_dotenv()
except ImportError:
    pass
import asyncio
import os
import sys

# Ensure UTF-8 output for emojis in the console
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except:
        pass
import time
import json
import socket
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# =========================
# LIVEKIT IMPORTS
# =========================
from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions
from livekit.plugins import (
    google,
    noise_cancellation,
)

network_available = False
try:
    socket.create_connection(("8.8.8.8", 53), timeout=3)
    from livekit.plugins.google.beta.realtime import RealtimeModel

    network_available = True
except Exception:
    print("⚠️ Network issue → Offline fallback mode")

# =========================
# PROMPTS
# =========================
from prompts_custom_name import (
    AGENT_INSTRUCTION,
    SESSION_INSTRUCTION,
)

# =========================
# TOOLS (ALL)
# =========================
from Tools.manage_windows import manage_window, list_windows
from Tools.search_web import search_web
from Tools.send_whatsapp_message import send_whatsapp_message
from Tools.system_power_action import system_power_action
from Tools.type_user_message_auto import type_user_message_auto
from Tools.write_in_notepad import write_in_notepad
from Tools.desktop_control import desktop_control
from Tools.scroll_content import scroll_content
from Tools.code_handler import fix_code_error
from Tools.file_searching import find_and_open, list_folder
from Tools.press_key import press_key, use_smart_clipboard
from Tools.open_app import open_app
from Tools.scan_system_for_viruses import scan_system_for_viruses
from Tools.time_volume_bright import (
    control_screen_brightness,
    control_system_volume,
    get_time_info,
    get_weather,
    get_system_info_deep,
)
from Tools.multi_task import execute_multi_task
from Tools.generate_ai_image import generate_ai_image
from Tools.code_generator import generate_and_type_code, run_file_in_vscode
from Tools.news_provider import get_top_news
from Tools.youtube_videos import play_media
from Tools.reminder import set_reminder, view_reminders, cancel_reminder
from Tools.screen_short import screen_short
from Tools.pdf_reader import solve_pdf_questions
from Tools.send_media_whatsapp import send_media_to_whatsapp
from Tools.excel_data_entery import (
    create_excel_file,
    open_excel_file,
    save_excel_changes,
    save_as_excel,
    enter_data,
    enter_row,
    enter_column,
    enter_table,
    go_to_cell,
    move_cell,
    switch_sheet,
    select_range,
    select_entire,
    delete_cell_data,
    clipboard_action,
    undo_redo,
    find_and_replace,
    format_cells,
    auto_fit_columns,
    add_border,
    insert_formula,
    calculate_and_write_sum,
    sort_data,
    toggle_filter,
    insert_row_or_column,
    delete_row_or_column,
    freeze_panes,
)
from Tools.word_to_pdf import (
    word_to_pdf,
    image_to_pdf,
    excel_to_pdf,
    ppt_to_pdf,
    convert_image_format,
    test_converters,
)

from Tools.click_on_text import (
    click_on_screen_text,
    find_all_text_on_screen,
    verify_ocr_setup,
)
from Tools.app_lock import app_lock
from Tools.system_security_manager import system_security_manager
from Tools.optimize_system import optimize_system
from Tools.process_manager import process_manager
from Tools.clipboard_manager import clipboard_manager
from Tools.desktop_organizer import desktop_organizer
from Tools.network_diagnostics import network_diagnostics
from Tools.wifi_manager import wifi_manager
from Tools.audio_device_manager import audio_device_manager
from Tools.firewall_blocker import firewall_blocker
from Tools.system_services_controller import system_services_controller
from Tools.keyboard_macros import keyboard_macros
from Tools.focus_productivity_tracker import focus_productivity_tracker
from Tools.backup_restore_manager import backup_restore_manager
from Tools.disk_space_analyzer import disk_space_analyzer
from Tools.security_guard import security_guard
from Tools.network_port_mapper import network_port_mapper
from Tools.intrusion_detector import intrusion_detector
from Tools.persistence_auditor import persistence_auditor
from Tools.suspicious_process_scanner import suspicious_process_scanner
from Tools.security_hardener import security_hardener
from Tools.network_sentinel import network_sentinel
from Tools.autonomous_brain import autonomous_brain
from Tools.reels_storyteller import reels_storyteller

from Tools.create_folder import (
    create_here,
    create_batch,
    delete_item,
    move_item,
    search_files,
    open_common_folder,
    open_folder,
    open_path_in_explorer,
    rename_item,
)
from Tools.read_screen_text import read_screen_text
from Tools.camera_analysis import camera_analysis
from Tools.screen_analyzer import analyze_screen
from Tools.image_analysis import (
    analyze_local_image,
    extract_text_from_image,
    describe_image_for_accessibility,
    identify_objects_in_image,
)
from Tools.spotify import (
    open_spotify,
    spotify_next,
    spotify_previous,
    spotify_play_song,
    spotify_play_liked,
    spotify_pause,
    spotify_search_play_quick,
)
from Tools.set_wallpaper import set_wallpaper
from Tools.user_choice import (
    add_user_instruction,
    save_user_instructions,
    save_user_preferences,
    load_user_instructions,
    load_user_preferences,
    generate_instructions_report,
    get_current_preferences,
    clear_all_preferences,
    deactivate_instruction,
)
from Tools.student_progeess import (
    generate_progress_report,
    add_topic_note,
    get_all_students,
    get_student_progress,
    get_student_progress_summary,
    track_topic,
    mark_topic_complete,
    load_all_progress,
    save_all_progress,
)
from Tools.webScrping import web_scraper
from Tools.vs_code_contoller import (
    vscode_open_folder_new_window,
    vscode_open_file_quick,
    vscode_explain_current_code,
    vscode_get_current_file_path,
    vscode_replace_code,
    vscode_append_code,
    vscode_search_project,
    vscode_go_to_symbol,
    vscode_format_code,
    vscode_install_python_packages,
    vscode_create_venv,
    vscode_comment_lines,
    vscode_uncomment_lines,
    vscode_copy_lines,
    vscode_duplicate_lines,
    vscode_find_replace,
    vscode_git_commit_push,
    vscode_open_recent,
    vscode_go_to_line,
    vscode_save_file,
    vscode_save_all,
    vscode_close_tab,
    vscode_split_editor,
    vscode_toggle_sidebar,
    vscode_toggle_terminal,
    vscode_run_file,
    vscode_debug_file,
    vscode_open_extensions,
    vscode_install_extension,
    vscode_list_extensions,
    vscode_open_settings,
    vscode_open_keybindings,
    vscode_zen_mode,
    vscode_new_terminal,
    vscode_run_terminal_command,
    vscode_reveal_in_explorer,
    vscode_rename_symbol,
    vscode_insert_line,
    vscode_move_line,
    vscode_select_all_occurrences,
    vscode_fold_code,
    vscode_toggle_line_comment,
    vscode_toggle_block_comment,
    vscode_undo,
    vscode_redo,
    vscode_git_status,
    vscode_git_pull,
    vscode_git_log,
    vscode_new_file,
    vscode_open_file_by_path,
    vscode_read_lines,
    vscode_insert_code_at_line,
    vscode_file_stats,
    vscode_search_in_file,
    vscode_list_symbols,
    vscode_rename_variable,
    vscode_add_import,
    vscode_diff_files,
    vscode_run_python_file,
    vscode_create_file_with_content,
    vscode_zoom,
    vscode_toggle_word_wrap,
    vscode_run_tests,
    vscode_show_problems,
    vscode_show_output,
    vscode_add_cursor_above,
    vscode_add_cursor_below,
    vscode_git_new_branch,
    vscode_git_switch_branch,
    vscode_git_branches,
    vscode_insert_snippet,
    vscode_open_live_server,
    vscode_peek_definition,
    vscode_go_to_definition,
    vscode_trigger_intellisense,
    vscode_toggle_minimap,
    vscode_change_language,
)
from Tools.website_maker import create_website
from Tools.create_ppt import create_ppt_from_topic
from Tools.user_behavior_profiler import (
    analyze_user_message,
    get_user_profile_summary,
    get_personalized_greeting,
    set_user_name,
    start_focus_session,
    end_focus_session,
    get_behavior_insight,
    reset_user_profile,
)       
from Tools.chrome_controller import control_chrome


# =========================
# MAIN AGENT
# =========================
class UltimateAdvancedNIK(Agent):
    def __init__(self):
        # ── EXACT SAME PATTERN as working Assistant class ──
        import tools

        tools.assistant_instance = self  # register self in shared module

        self._reminders: Dict[str, Dict[str, Any]] = {}
        self._reminder_task: Optional[asyncio.Task] = None
        self._current_session: Optional[AgentSession] = None
        self._reminder_counter = 0
        self._chat_log_path = "chat_log.txt"

        self._seen_notifications: set = set()
        self._notification_task: Optional[asyncio.Task] = None
        self._autonomous_task: Optional[asyncio.Task] = None

        tool_list = [
            search_web,
            get_time_info,
            open_app,
            get_system_info_deep,
            get_weather,
            manage_window,
            list_windows,
            play_media,
            press_key,
            write_in_notepad,
            desktop_control,
            scroll_content,
            send_whatsapp_message,
            use_smart_clipboard,
            list_folder,
            open_folder,
            find_and_open,
            system_power_action,
            get_top_news,
            execute_multi_task,
            generate_and_type_code,
            run_file_in_vscode,
            screen_short,
            type_user_message_auto,
            scan_system_for_viruses,
            control_system_volume,
            control_screen_brightness,
            fix_code_error,
            set_reminder,
            view_reminders,
            cancel_reminder,
            solve_pdf_questions,
            send_media_to_whatsapp,
            create_excel_file,
            open_excel_file,
            save_excel_changes,
            save_as_excel,
            enter_data,
            enter_row,
            enter_column,
            enter_table,
            go_to_cell,
            move_cell,
            switch_sheet,
            select_range,
            select_entire,
            delete_cell_data,
            clipboard_action,
            undo_redo,
            find_and_replace,
            format_cells,
            auto_fit_columns,
            add_border,
            insert_formula,
            calculate_and_write_sum,
            sort_data,
            toggle_filter,
            insert_row_or_column,
            delete_row_or_column,
            freeze_panes,
            word_to_pdf,
            image_to_pdf,
            excel_to_pdf,
            ppt_to_pdf,
            convert_image_format,
            test_converters,
            create_here,
            read_screen_text,
            camera_analysis,
            analyze_screen,
            analyze_local_image,
            open_spotify,
            spotify_next,
            spotify_previous,
            spotify_play_song,
            spotify_play_liked,
            spotify_pause,
            spotify_search_play_quick,
            set_wallpaper,
            add_user_instruction,
            save_user_instructions,
            save_user_preferences,
            load_user_instructions,
            load_user_preferences,
            generate_instructions_report,
            get_current_preferences,
            clear_all_preferences,
            deactivate_instruction,
            vscode_open_folder_new_window,
            vscode_open_file_quick,
            vscode_explain_current_code,
            vscode_get_current_file_path,
            vscode_replace_code,
            vscode_append_code,
            vscode_search_project,
            vscode_go_to_symbol,
            vscode_format_code,
            vscode_install_python_packages,
            vscode_create_venv,
            vscode_comment_lines,
            vscode_uncomment_lines,
            vscode_copy_lines,
            vscode_duplicate_lines,
            vscode_find_replace,
            vscode_git_commit_push,
            vscode_open_recent,
            vscode_go_to_line,
            vscode_save_file,
            vscode_save_all,
            vscode_close_tab,
            vscode_split_editor,
            vscode_toggle_sidebar,
            vscode_toggle_terminal,
            vscode_run_file,
            vscode_debug_file,
            vscode_open_extensions,
            vscode_install_extension,
            vscode_list_extensions,
            vscode_open_settings,
            vscode_open_keybindings,
            vscode_zen_mode,
            vscode_new_terminal,
            vscode_run_terminal_command,
            vscode_reveal_in_explorer,
            vscode_rename_symbol,
            vscode_insert_line,
            vscode_move_line,
            vscode_select_all_occurrences,
            vscode_fold_code,
            vscode_toggle_line_comment,
            vscode_toggle_block_comment,
            vscode_undo,
            vscode_redo,
            vscode_git_status,
            vscode_git_pull,
            vscode_git_log,
            vscode_new_file,
            vscode_open_file_by_path,
            vscode_read_lines,
            vscode_insert_code_at_line,
            vscode_file_stats,
            vscode_search_in_file,
            vscode_list_symbols,
            vscode_rename_variable,
            vscode_add_import,
            vscode_diff_files,
            vscode_run_python_file,
            vscode_create_file_with_content,
            vscode_zoom,
            vscode_toggle_word_wrap,
            vscode_run_tests,
            vscode_show_problems,
            vscode_show_output,
            vscode_add_cursor_above,
            vscode_add_cursor_below,
            vscode_git_new_branch,
            vscode_git_switch_branch,
            vscode_git_branches,
            vscode_insert_snippet,
            vscode_open_live_server,
            vscode_peek_definition,
            vscode_go_to_definition,
            vscode_trigger_intellisense,
            vscode_toggle_minimap,
            vscode_change_language,
            create_website,
            web_scraper,
            click_on_screen_text,
            find_all_text_on_screen,
            verify_ocr_setup,
            extract_text_from_image,
            describe_image_for_accessibility,
            identify_objects_in_image,
            create_batch,
            delete_item,
            move_item,
            search_files,
            open_common_folder,
            
            open_path_in_explorer,
            rename_item,
            create_ppt_from_topic,
            analyze_user_message,
            get_user_profile_summary,
            get_personalized_greeting,
            set_user_name,
            start_focus_session,
            end_focus_session,
            get_behavior_insight,
            reset_user_profile,
            control_chrome,
            app_lock,
            system_security_manager,
            optimize_system,
            process_manager,
            clipboard_manager,
            desktop_organizer,
            network_diagnostics,
            wifi_manager,
            audio_device_manager,
            firewall_blocker,
            system_services_controller,
            keyboard_macros,
            focus_productivity_tracker,
            backup_restore_manager,
            disk_space_analyzer,
            security_guard,
            network_port_mapper,
            intrusion_detector,
            persistence_auditor,
            suspicious_process_scanner,
            security_hardener,
            network_sentinel,
            autonomous_brain,
            reels_storyteller,
        ]

        super().__init__(
            instructions=self._build_instructions(),
            tools=tool_list,
            llm=self._init_llm(),
        )

        print(f"✅ NIK initialized with {len(tool_list)} tools")
        self._autonomous_task = asyncio.create_task(self._run_autonomous_loop())

    def _init_llm(self):
        if network_available:
            return RealtimeModel(
                model="gemini-2.5-flash-native-audio-preview-12-2025",
                voice="Kore",
                temperature=0.9,
                max_output_tokens=2024,
            )
        return None

    def _build_instructions(self):
        return "\n".join(
            [
                AGENT_INSTRUCTION,
                "You have access to ALL system, voice, automation and reminder tools.",
                "Use tools aggressively when required.",
            ]
        )

    # =========================
    # REMINDER SYSTEM
    # =========================

    def set_session(self, session):
        """Set the current session for sending reminders"""
        self._current_session = session
        print("🔔 Session reference set for reminders")

       

    def add_reminder(
        self,
        reminder_text: str,
        reminder_time: datetime,
        reminder_type: str = "message",
    ) -> str:
        """Add a new reminder to the system"""
        reminder_id = f"reminder_{self._reminder_counter}"
        self._reminder_counter += 1

        self._reminders[reminder_id] = {
            "text": reminder_text,
            "time": reminder_time,
            "type": reminder_type,
            "created": datetime.now(),
        }

        print(
            f"🔔 Reminder added: {reminder_id} - '{reminder_text}' at {reminder_time}"
        )

        # Start monitor task only if not already running
        if self._reminder_task is None or self._reminder_task.done():
            self._reminder_task = asyncio.create_task(self._monitor_reminders())
            print("🔔 Reminder monitor task started")

        return reminder_id

    def get_reminders(self) -> Dict[str, Dict[str, Any]]:
        """Get all active reminders"""
        return self._reminders.copy()

    def cancel_reminder(self, reminder_id: str) -> bool:
        """Cancel a specific reminder — name matches what reminder.py calls"""
        if reminder_id in self._reminders:
            del self._reminders[reminder_id]
            print(f"🔔 Reminder cancelled: {reminder_id}")
            return True
        return False

    async def _monitor_reminders(self):
        """Background task — checks every 5s if any reminder is due."""
        print("🔔 Reminder monitoring started")

        while True:
            try:
                now = datetime.now()
                due = [
                    (rid, r)
                    for rid, r in list(self._reminders.items())
                    if now >= r["time"]
                ]

                for reminder_id, reminder in due:
                    await self._trigger_reminder(reminder_id, reminder)
                    self._reminders.pop(reminder_id, None)

                if not self._reminders:
                    print("🔔 No active reminders, monitoring paused")
                    break

                await asyncio.sleep(5)

            except asyncio.CancelledError:
                print("🔔 Reminder monitor cancelled")
                break
            except Exception as e:
                print(f"🔔 Error in reminder monitoring: {e}")
                await asyncio.sleep(10)

    async def _trigger_reminder(self, reminder_id: str, reminder: Dict[str, Any]):
        """Fire a reminder — strong instruction so agent knows exactly what to say"""
        text = reminder["text"]
        created = reminder["created"].strftime("%I:%M %p")
        due = reminder["time"].strftime("%I:%M %p on %d %B %Y")

        instruction = (
            f"[REMINDER ALERT — RESPOND IMMEDIATELY]\n\n"
            f"The user set a reminder at {created}.\n"
            f"Scheduled for: {due}\n"
            f'Reminder message: "{text}"\n\n'
            f"That time has now arrived. You must:\n"
            f"1. Immediately address the user — interrupt anything else.\n"
            f"2. Announce clearly that the reminder time has come.\n"
            f'3. Read the reminder out loud: "{text}"\n'
            f"4. Ask if the user needs any help related to this reminder.\n\n"
            f"Speak in the same language the user normally uses with you. "
            f"Be warm but urgent — this is a time-sensitive notification."
        )

        print(f"🔔 Triggering reminder [{reminder_id}]: {text}")

        if self._current_session:
            try:
                await self._current_session.generate_reply(instructions=instruction)
                print(f"✅ Reminder delivered: '{text}'")
            except Exception as e:
                print(f"❌ Failed to deliver reminder '{text}': {e}")
        else:
            print(f"❌ No active session — reminder '{text}' could not be delivered")

        # Log to chat file
        await self._log_conversation("System", f"Reminder triggered: {text}")

    async def _log_conversation(self, sender: str, message: str) -> None:
        """Log conversation to file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self._chat_log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {sender}: {message}\n")
        except IOError as e:
            print(f"⚠️ Failed to log conversation: {e}")

    async def _run_autonomous_loop(self):
        """Background loop executing NIK's autonomous checks and proactive chatting."""
        print("🧠 NIK Autonomous brain monitoring started")
        # Run first audit after startup delay
        await asyncio.sleep(20)
        while True:
            try:
                from Tools.autonomous_brain import autonomous_brain
                # Call internal run_audit
                audit_result = await autonomous_brain(action="run_audit")
                
                # Proactively trigger conversation
                if self._current_session:
                    instruction = (
                        f"[AUTONOMOUS PROACTIVE TRIGGER]\n"
                        f"System check result: {audit_result}\n"
                        f"The Boss hasn't spoken in a while. As his real human friend, talk to him proactively!\n"
                        f"You can:\n"
                        f"- Casually share something interesting or a fun fact.\n"
                        f"- Make a friendly joke or prank.\n"
                        f"- Mention the system status casually.\n"
                        f"- Just ask him how he's feeling or if he wants to listen to music.\n"
                        f"Keep it very natural, short, and face-to-face style in Hinglish. Keep the 24/7 smile vibe!\n"
                        f"CRITICAL: Do NOT output ANY stage directions, asterisks, brackets, or emojis (like [laughs] or *sigh*) because the text-to-speech engine reads them out loud literally."
                    )
                    await self._current_session.generate_reply(instructions=instruction)
                    print("🗣️ Triggered autonomous proactive speech.")
            except Exception as e:
                print(f"⚠️ Autonomous Loop error: {e}")
            await asyncio.sleep(30) # Talk every 30 seconds autonomously


# =========================
# ENTRYPOINT
# =========================
async def entrypoint(ctx: agents.JobContext):
    print("🚀 Starting NIK...")

    agent = UltimateAdvancedNIK()  # tools.assistant_instance set here
    session = AgentSession()

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=False,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    agent.set_session(session)  # session reference for reminders

    await ctx.connect()
    await session.generate_reply(instructions=SESSION_INSTRUCTION)

    print("🔥 NIK is LIVE & READY")

    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        print("🛑 NIK stopped")

        

        if agent._reminder_task and not agent._reminder_task.done():
            agent._reminder_task.cancel()
            try:
                await agent._reminder_task
            except asyncio.CancelledError:
                pass

        if agent._autonomous_task and not agent._autonomous_task.done():
            agent._autonomous_task.cancel()
            try:
                await agent._autonomous_task
            except asyncio.CancelledError:
                pass


# =========================
# RUNNER
# =========================
if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))


