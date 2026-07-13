import os
import json
from datetime import datetime
from livekit.agents import function_tool
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from typing import Optional, Dict, List, Any

# User preferences file path
USER_PREFS_FILE = os.path.join(os.path.expanduser("~"), "user_preferences.json")
USER_INSTRUCTIONS_FILE = os.path.join(os.path.expanduser("~"), "user_instructions.json")

# ==================== USER PREFERENCES & INSTRUCTIONS SYSTEM ====================

@function_tool()
def load_user_preferences() -> Dict:
    """Load user preferences from JSON file"""
    if os.path.exists(USER_PREFS_FILE):
        with open(USER_PREFS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "user_name": None,
        "address_term": None,  # e.g., "sir ji", "bhaiya", "ma'am"
        "formality_level": "neutral",  # "formal" (aap), "informal" (tu), "neutral"
        "language": "hindi",  # preferred language
        "response_style": "normal",  # "detailed", "concise", "normal"
        "custom_instructions": {},
        "preferences_history": [],
        "last_updated": datetime.now().isoformat()
    }

@function_tool()
def save_user_preferences(prefs_data: Dict):
    """Save user preferences to JSON file"""
    prefs_data["last_updated"] = datetime.now().isoformat()
    with open(USER_PREFS_FILE, 'w', encoding='utf-8') as f:
        json.dump(prefs_data, f, indent=2, ensure_ascii=False)

@function_tool()
def load_user_instructions() -> Dict:
    """Load all user instructions (behavioral changes) from JSON file"""
    if os.path.exists(USER_INSTRUCTIONS_FILE):
        with open(USER_INSTRUCTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "instructions": [],
        "active_rules": {},
        "categories": {},
        "last_updated": datetime.now().isoformat()
    }

@function_tool()
def save_user_instructions(instructions_data: Dict):
    """Save user instructions to JSON file"""
    instructions_data["last_updated"] = datetime.now().isoformat()
    with open(USER_INSTRUCTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(instructions_data, f, indent=2, ensure_ascii=False)


@function_tool()
async def set_user_preference(
    preference_type: str,
    value: Any,
    context: Optional[str] = None
) -> str:
    """
    ⚙️ AUTO-EXECUTE FUNCTION - Jab user koi preference change kare!
    
    Stores user preferences like how they want to be addressed, formality level, etc.
    
    🔍 WHEN TO USE:
    - User kehta hai "mujhe sir ji bulaya karo"
    - User kehta hai "hamesha aap karke baat karo"
    - User kehta hai "mujhe bhaiya bolo"
    - User kehta hai "detailed answer diya karo" / "short mein batao"
    - User kehta hai "English mein baat karo" / "Hindi mein baat karo"
    
    Args:
        preference_type: Type of preference (address_term, formality_level, language, response_style)
        value: Value for that preference (e.g., "sir ji", "formal", "hindi", "detailed")
        context: Optional context about when/why this preference was set
    
    Returns:
        str: Confirmation message
    """
    try:
        prefs = load_user_preferences()
        
        # Map common phrases to preference types
        pref_mapping = {
            "address": "address_term",
            "bulana": "address_term",
            "bolo": "address_term",
            "formality": "formality_level",
            "aap": "formality_level",
            "tu": "formality_level",
            "language": "language",
            "bhasha": "language",
            "style": "response_style",
            "detail": "response_style",
            "concise": "response_style"
        }
        
        # Normalize preference type
        pref_key = pref_mapping.get(preference_type.lower(), preference_type.lower())
        
        # Validate and store
        valid_prefs = ["address_term", "formality_level", "language", "response_style"]
        if pref_key not in valid_prefs:
            return f"❌ Invalid preference type. Supported: {', '.join(valid_prefs)}"
        
        # Store in history
        if "preferences_history" not in prefs:
            prefs["preferences_history"] = []
        
        prefs["preferences_history"].append({
            "timestamp": datetime.now().isoformat(),
            "type": pref_key,
            "old_value": prefs.get(pref_key),
            "new_value": value,
            "context": context
        })
        
        # Update current preference
        prefs[pref_key] = value
        
        # Save
        save_user_preferences(prefs)
        
        # Create response based on preference type
        responses = {
            "address_term": f"✅ Ab se main aapko '{value}' kehkar bulaaunga!",
            "formality_level": f"✅ Ab se main {value} style mein baat karunga (aap/tu accordingly)",
            "language": f"✅ Ab se main {value} mein baat karunga!",
            "response_style": f"✅ Ab se main {value} responses dunga!"
        }
        
        return responses.get(pref_key, f"✅ Preference set: {pref_key} = {value}")
        
    except Exception as e:
        return f"❌ Preference set karne mein error: {str(e)}"


@function_tool()
async def add_user_instruction(
    instruction: str,
    category: str = "behavior",
    priority: str = "medium"
) -> str:
    """
    📝 AUTO-EXECUTE FUNCTION - Jab user koi specific instruction de!
    
    Stores user instructions about how the agent should behave.
    Yeh specific rules hain jo user ne diye hain.
    
    🔍 WHEN TO USE:
    - User kehta hai "hamesha examples ke saath samjhao"
    - User kehta hai "pehle summary do phir details mein jao"
    - User kehta hai "har baar 'kuch aur poochiye' puchna"
    - User kehta hai "morning mein motivational message bhejna"
    - Koi bhi specific instruction jo user de
    
    Args:
        instruction: User ka instruction
        category: Category (behavior, timing, format, etc.)
        priority: Kitna important hai (high, medium, low)
    
    Returns:
        str: Confirmation with instruction ID
    """
    try:
        instructions_data = load_user_instructions()
        
        # Create instruction entry
        instruction_id = f"inst_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        new_instruction = {
            "id": instruction_id,
            "instruction": instruction,
            "category": category,
            "priority": priority,
            "status": "active",  # active, inactive, completed
            "created_at": datetime.now().isoformat(),
            "last_used": None,
            "times_used": 0,
            "notes": []
        }
        
        # Add to instructions list
        instructions_data["instructions"].append(new_instruction)
        
        # Update category stats
        if category not in instructions_data["categories"]:
            instructions_data["categories"][category] = 0
        instructions_data["categories"][category] += 1
        
        # Update active rules
        instructions_data["active_rules"][instruction_id] = {
            "instruction": instruction,
            "category": category,
            "priority": priority
        }
        
        # Save
        save_user_instructions(instructions_data)
        
        return f"✅ Instruction yaad kar liya! ID: {instruction_id}\n📌 '{instruction}'"
        
    except Exception as e:
        return f"❌ Instruction store karne mein error: {str(e)}"


@function_tool()
async def update_instruction_usage(instruction_id: str) -> str:
    """
    🔄 INTERNAL FUNCTION - Jab instruction use ho jaye tab call karein
    
    Updates usage count for an instruction.
    
    Args:
        instruction_id: Instruction ka ID
    
    Returns:
        str: Confirmation message
    """
    try:
        instructions_data = load_user_instructions()
        
        for instruction in instructions_data["instructions"]:
            if instruction["id"] == instruction_id:
                instruction["last_used"] = datetime.now().isoformat()
                instruction["times_used"] += 1
                break
        
        save_user_instructions(instructions_data)
        return f"✅ Instruction {instruction_id} usage updated"
        
    except Exception as e:
        return f"❌ Update karne mein error: {str(e)}"


@function_tool()
async def get_current_preferences() -> str:
    """
    Get current user preferences and active instructions.
    
    Returns:
        str: Summary of all active preferences and instructions
    """
    try:
        prefs = load_user_preferences()
        instructions_data = load_user_instructions()
        
        response = "⚙️ **Current User Preferences**\n\n"
        
        # Basic preferences
        response += "**📋 Basic Settings:**\n"
        response += f"• Address Term: {prefs.get('address_term', 'Not set')}\n"
        response += f"• Formality Level: {prefs.get('formality_level', 'neutral')}\n"
        response += f"• Language: {prefs.get('language', 'hindi')}\n"
        response += f"• Response Style: {prefs.get('response_style', 'normal')}\n\n"
        
        # Active instructions
        active_instructions = [i for i in instructions_data["instructions"] if i["status"] == "active"]
        
        if active_instructions:
            response += "**📌 Active Instructions:**\n"
            for inst in active_instructions[:5]:  # Show last 5
                priority_emoji = "🔴" if inst["priority"] == "high" else "🟡" if inst["priority"] == "medium" else "🟢"
                response += f"{priority_emoji} {inst['instruction']}\n"
                if inst.get("times_used", 0) > 0:
                    response += f"   (Used {inst['times_used']} times)\n"
            response += "\n"
        
        # Recent changes
        if prefs.get("preferences_history"):
            response += "**📝 Recent Changes:**\n"
            recent = prefs["preferences_history"][-3:]  # Last 3 changes
            for change in recent:
                change_date = datetime.fromisoformat(change["timestamp"]).strftime("%b %d, %H:%M")
                response += f"• [{change_date}] {change['type']}: {change['old_value']} → {change['new_value']}\n"
        
        return response
        
    except Exception as e:
        return f"❌ Preferences check karne mein error: {str(e)}"


@function_tool()
async def generate_instructions_report() -> str:
    """
    Generate a detailed Word document report of all user instructions and preferences.
    
    Returns:
        str: Path to the generated Word document
    """
    try:
        prefs = load_user_preferences()
        instructions_data = load_user_instructions()
        
        # Create reports folder
        reports_folder = os.path.join(os.path.expanduser("~"), "OneDrive", "Pictures", "nova_screenshots", "user_reports")
        if not os.path.exists(reports_folder):
            os.makedirs(reports_folder)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        report_path = os.path.join(reports_folder, f"User_Instructions_Report_{timestamp}.docx")
        
        # Create document
        doc = Document()
        
        # Title
        title = doc.add_heading('📋 User Instructions & Preferences Report', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Report generation date
        date_para = doc.add_paragraph(f"Report Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
        date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph()
        
        # User Preferences Section
        doc.add_heading('⚙️ User Preferences', level=1)
        
        prefs_table = doc.add_table(rows=4, cols=2)
        prefs_table.style = 'Light Grid Accent 1'
        
        prefs_table.cell(0, 0).text = "Address Term"
        prefs_table.cell(0, 1).text = str(prefs.get('address_term', 'Not set'))
        prefs_table.cell(1, 0).text = "Formality Level"
        prefs_table.cell(1, 1).text = prefs.get('formality_level', 'neutral')
        prefs_table.cell(2, 0).text = "Language"
        prefs_table.cell(2, 1).text = prefs.get('language', 'hindi')
        prefs_table.cell(3, 0).text = "Response Style"
        prefs_table.cell(3, 1).text = prefs.get('response_style', 'normal')
        
        doc.add_paragraph()
        
        # Preferences History
        if prefs.get("preferences_history"):
            doc.add_heading('📊 Preference Changes History', level=2)
            
            history_table = doc.add_table(rows=len(prefs["preferences_history"]) + 1, cols=4)
            history_table.style = 'Light List Accent 1'
            
            # Header
            headers = history_table.rows[0].cells
            headers[0].text = "Date"
            headers[1].text = "Type"
            headers[2].text = "Old Value"
            headers[3].text = "New Value"
            
            # Data
            for i, change in enumerate(prefs["preferences_history"], 1):
                cells = history_table.rows[i].cells
                change_date = datetime.fromisoformat(change["timestamp"]).strftime("%Y-%m-%d %H:%M")
                cells[0].text = change_date
                cells[1].text = change["type"]
                cells[2].text = str(change["old_value"])
                cells[3].text = str(change["new_value"])
            
            doc.add_paragraph()
        
        # Active Instructions Section
        doc.add_heading('📌 Active Instructions', level=1)
        
        active_instructions = [i for i in instructions_data["instructions"] if i["status"] == "active"]
        
        if active_instructions:
            # Sort by priority
            priority_order = {"high": 0, "medium": 1, "low": 2}
            active_instructions.sort(key=lambda x: priority_order.get(x["priority"], 3))
            
            inst_table = doc.add_table(rows=len(active_instructions) + 1, cols=6)
            inst_table.style = 'Light List Accent 1'
            
            # Header
            headers = inst_table.rows[0].cells
            headers[0].text = "ID"
            headers[1].text = "Instruction"
            headers[2].text = "Category"
            headers[3].text = "Priority"
            headers[4].text = "Times Used"
            headers[5].text = "Last Used"
            
            # Data
            for i, inst in enumerate(active_instructions, 1):
                cells = inst_table.rows[i].cells
                cells[0].text = inst["id"]
                cells[1].text = inst["instruction"]
                cells[2].text = inst["category"]
                cells[3].text = inst["priority"]
                cells[4].text = str(inst.get("times_used", 0))
                
                if inst.get("last_used"):
                    last_used = datetime.fromisoformat(inst["last_used"]).strftime("%Y-%m-%d")
                    cells[5].text = last_used
                else:
                    cells[5].text = "Never"
        else:
            doc.add_paragraph("No active instructions found.")
        
        doc.add_paragraph()
        
        # Statistics Section
        doc.add_heading('📈 Statistics', level=1)
        
        total_instructions = len(instructions_data["instructions"])
        completed = sum(1 for i in instructions_data["instructions"] if i["status"] == "completed")
        inactive = sum(1 for i in instructions_data["instructions"] if i["status"] == "inactive")
        
        stats_table = doc.add_table(rows=4, cols=2)
        stats_table.style = 'Light Grid Accent 1'
        
        stats_table.cell(0, 0).text = "Total Instructions"
        stats_table.cell(0, 1).text = str(total_instructions)
        stats_table.cell(1, 0).text = "Active"
        stats_table.cell(1, 1).text = str(len(active_instructions))
        stats_table.cell(2, 0).text = "Completed"
        stats_table.cell(2, 1).text = str(completed)
        stats_table.cell(3, 0).text = "Inactive"
        stats_table.cell(3, 1).text = str(inactive)
        
        # Category breakdown
        if instructions_data.get("categories"):
            doc.add_paragraph()
            doc.add_heading('📊 By Category', level=2)
            
            cat_table = doc.add_table(rows=len(instructions_data["categories"]) + 1, cols=2)
            cat_table.style = 'Light List Accent 1'
            
            cat_table.cell(0, 0).text = "Category"
            cat_table.cell(0, 1).text = "Count"
            
            for i, (category, count) in enumerate(instructions_data["categories"].items(), 1):
                cat_table.cell(i, 0).text = category
                cat_table.cell(i, 1).text = str(count)
        
        # Save document
        doc.save(report_path)
        
        return f"✅ Instructions report generate ho gaya!\n📍 {report_path}"
        
    except Exception as e:
        return f"❌ Report generate karne mein error: {str(e)}"


@function_tool()
async def deactivate_instruction(instruction_id: str, reason: Optional[str] = None) -> str:
    """
    Deactivate a specific instruction.
    
    Args:
        instruction_id: Instruction ka ID
        reason: Kyun deactivate kar rahe hain
    
    Returns:
        str: Confirmation message
    """
    try:
        instructions_data = load_user_instructions()
        
        for instruction in instructions_data["instructions"]:
            if instruction["id"] == instruction_id:
                instruction["status"] = "inactive"
                instruction["deactivated_at"] = datetime.now().isoformat()
                instruction["deactivation_reason"] = reason
                
                # Remove from active rules
                if instruction_id in instructions_data["active_rules"]:
                    del instructions_data["active_rules"][instruction_id]
                
                break
        else:
            return f"❌ Instruction ID {instruction_id} nahi mila."
        
        save_user_instructions(instructions_data)
        return f"✅ Instruction {instruction_id} deactivate kar diya gaya."
        
    except Exception as e:
        return f"❌ Deactivate karne mein error: {str(e)}"


@function_tool()
async def clear_all_preferences(confirm: bool = False) -> str:
    """
    Clear all user preferences and instructions.
    
    Args:
        confirm: Confirmation ke liye True karna hoga
    
    Returns:
        str: Confirmation message
    """
    if not confirm:
        return "⚠️ Safety: confirm=True bhej kar confirm karein agar aap saare preferences delete karna chahte hain."
    
    try:
        # Reset preferences
        default_prefs = {
            "user_name": None,
            "address_term": None,
            "formality_level": "neutral",
            "language": "hindi",
            "response_style": "normal",
            "custom_instructions": {},
            "preferences_history": [],
            "last_updated": datetime.now().isoformat()
        }
        save_user_preferences(default_prefs)
        
        # Reset instructions
        default_instructions = {
            "instructions": [],
            "active_rules": {},
            "categories": {},
            "last_updated": datetime.now().isoformat()
        }
        save_user_instructions(default_instructions)
        
        return "✅ Saare preferences aur instructions clear kar diye gaye hain!"
        
    except Exception as e:
        return f"❌ Clear karne mein error: {str(e)}"