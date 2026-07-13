import pyautogui
import os
import json
from datetime import datetime
from livekit.agents import function_tool
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from typing import Optional, Dict, List

# Student progress file path
PROGRESS_FILE = os.path.join(os.path.expanduser("~"),"all_students_progress.json")

@function_tool()
def load_all_progress() -> Dict:
    """Load all students' progress from JSON file"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"students": {}, "last_updated": datetime.now().isoformat()}

@function_tool()
def save_all_progress(progress_data: Dict):
    """Save all students' progress to JSON file"""
    progress_data["last_updated"] = datetime.now().isoformat()
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress_data, f, indent=2, ensure_ascii=False)

@function_tool()
def get_student_progress(student_name: str) -> Dict:
    """Get or create progress for a specific student"""
    all_progress = load_all_progress()
    
    # Normalize student name (lowercase for consistency)
    student_key = student_name.lower().strip()
    
    if student_key not in all_progress["students"]:
        # Create new student record
        all_progress["students"][student_key] = {
            "name": student_name,  # Original name with proper capitalization
            "joined_date": datetime.now().isoformat(),
            "topics": [],
            "total_sessions": 0,
            "total_study_time": 0,  # in hours
            "subjects": {},
            "last_active": None
        }
        save_all_progress(all_progress)
    
    return all_progress["students"][student_key], all_progress

def update_student_progress(student_key: str, updated_student_data: Dict, all_progress: Dict):
    """Update a specific student's progress in the main data"""
    all_progress["students"][student_key] = updated_student_data
    save_all_progress(all_progress)



@function_tool()
async def track_topic(student_name: str, topic_name: str, subject: str = "General") -> str:
    """
    🔴 AUTO-EXECUTE FUNCTION - Jab bhi student koi naya topic start kare!
    
    Tracks a new topic that a student starts learning.
    Har student ka alag progress track hoga.
    
    🔍 WHEN TO USE:
    - Student kehta hai "mujhe ye topic samjhao" / "ye topic padhao"
    - Student kehta hai "start karte hain ye chapter"
    - Student poochta hai "kya aap mujhe ye topic sikha sakte ho?"
    - Jab bhi conversation mein clear indication ho ki naya topic shuru ho raha hai
    
    Args:
        student_name: Student ka naam (pehle se puchh kar confirm karein)
        topic_name: Jo topic padhaya ja raha hai
        subject: Kis subject ka topic hai (default: "General")
    
    Returns:
        str: Confirmation message with student name
    """
    try:
        # Get student progress
        student_data, all_progress = get_student_progress(student_name)
        
        # Create new topic entry
        new_topic = {
            "topic": topic_name,
            "subject": subject,
            "start_time": datetime.now().isoformat(),
            "status": "in_progress",
            "sessions": [],
            "notes": []
        }
        
        # Add to student's topics list
        student_data["topics"].append(new_topic)
        student_data["total_sessions"] += 1
        student_data["last_active"] = datetime.now().isoformat()
        
        # Update subject statistics
        if subject not in student_data["subjects"]:
            student_data["subjects"][subject] = {"count": 0, "completed": 0}
        student_data["subjects"][subject]["count"] += 1
        
        # Save updated progress
        student_key = student_name.lower().strip()
        update_student_progress(student_key, student_data, all_progress)
        
        return f"✅ {student_name} ke liye '{topic_name}' topic track karna start kar diya hai! (Subject: {subject})"
        
    except Exception as e:
        return f"❌ Topic track karne mein error: {str(e)}"

@function_tool()
async def mark_topic_complete(student_name: str, topic_name: str) -> str:
    """
    🔴 AUTO-EXECUTE FUNCTION - Jab student ne topic complete kar liya ho!
    
    Marks a topic as completed when a student finishes it.
    
    🔍 WHEN TO USE:
    - Student kehta hai "ye topic samajh aa gaya" / "main samajh gaya"
    - Student kehta hai "ab agla topic chalein?"
    - Student poochta hai "kya ye topic complete ho gaya?"
    - Jab aap khud mahsus karein ki student ne topic achhe se samajh liya
    - Jab topic ka exercise/example complete ho jaye
    
    Args:
        student_name: Student ka naam
        topic_name: Jo topic complete hua hai
    
    Returns:
        str: Confirmation message with completion time
    """
    try:
        student_data, all_progress = get_student_progress(student_name)
        
        # Find the topic
        for topic in student_data["topics"]:
            if topic["topic"].lower() == topic_name.lower() and topic["status"] == "in_progress":
                topic["status"] = "completed"
                topic["completion_time"] = datetime.now().isoformat()
                
                # Calculate duration
                start = datetime.fromisoformat(topic["start_time"])
                end = datetime.fromisoformat(topic["completion_time"])
                duration = (end - start).total_seconds() / 3600
                topic["duration"] = duration
                
                # Update total study time
                student_data["total_study_time"] += duration
                
                # Update subject completed count
                subject = topic.get("subject", "General")
                if subject in student_data["subjects"]:
                    student_data["subjects"][subject]["completed"] += 1
                
                break
        else:
            return f"❌ {student_name} ke liye '{topic_name}' topic nahi mila ya already complete ho chuka hai."
        
        student_data["last_active"] = datetime.now().isoformat()
        
        # Save updated progress
        student_key = student_name.lower().strip()
        update_student_progress(student_key, student_data, all_progress)
        
        return f"✅ {student_name} ne '{topic_name}' complete kar liya! Time: {duration:.1f} hours"
        
    except Exception as e:
        return f"❌ Topic complete karne mein error: {str(e)}"

@function_tool()
async def add_topic_note(student_name: str, topic_name: str, note: str) -> str:
    """
    📝 MANUAL FUNCTION - Jab student koi important point/share kare
    
    Add a note to a specific topic (like doubts, important points, etc.)
    
    🔍 WHEN TO USE:
    - Student koi important formula/point share kare
    - Student koi doubt express kare
    - Aap khud koi important note add karna chahein
    - Jab koi example ya practice question discuss ho
    
    Args:
        student_name: Student ka naam
        topic_name: Kis topic ke liye note hai
        note: Note ka content
    
    Returns:
        str: Confirmation message
    """
    try:
        student_data, all_progress = get_student_progress(student_name)
        
        # Find the topic (either in progress or completed)
        for topic in student_data["topics"]:
            if topic["topic"].lower() == topic_name.lower():
                if "notes" not in topic:
                    topic["notes"] = []
                
                topic["notes"].append({
                    "timestamp": datetime.now().isoformat(),
                    "note": note
                })
                break
        else:
            return f"❌ {student_name} ke liye '{topic_name}' topic nahi mila."
        
        # Save updated progress
        student_key = student_name.lower().strip()
        update_student_progress(student_key, student_data, all_progress)
        
        return f"📝 Note add kar diya hai '{topic_name}' ke liye!"
        
    except Exception as e:
        return f"❌ Note add karne mein error: {str(e)}"

@function_tool()
async def get_all_students() -> str:
    """
    Get list of all students with their progress summary.
    
    Returns:
        str: List of all students and their basic stats
    """
    try:
        all_progress = load_all_progress()
        students = all_progress.get("students", {})
        
        if not students:
            return "📝 Abhi tak koi student register nahi hua hai."
        
        response = "👥 **All Students**\n\n"
        for student_key, student_data in students.items():
            name = student_data["name"]
            total_topics = len(student_data["topics"])
            completed = sum(1 for t in student_data["topics"] if t["status"] == "completed")
            in_progress = total_topics - completed
            
            response += f"**{name}**\n"
            response += f"• Topics: {total_topics} total ({completed} completed, {in_progress} in progress)\n"
            response += f"• Study Time: {student_data['total_study_time']:.1f} hours\n"
            
            # Last active
            if student_data["last_active"]:
                last_active = datetime.fromisoformat(student_data["last_active"]).strftime("%b %d, %Y")
                response += f"• Last Active: {last_active}\n"
            response += "\n"
        
        return response
        
    except Exception as e:
        return f"❌ Students list lene mein error: {str(e)}"

@function_tool()
async def generate_progress_report(student_name: Optional[str] = None) -> str:
    """
    Generates a detailed Word document report of student's learning progress.
    Agar student name nahi diya to sab students ka report banega.
    
    Args:
        student_name: Optional - specific student ka naam
    
    Returns:
        str: Path to the generated Word document
    """
    try:
        all_progress = load_all_progress()
        students_data = all_progress.get("students", {})
        
        if not students_data:
            return "❌ Abhi tak koi progress track nahi kiya gaya hai."
        
        # Create reports folder
        reports_folder = os.path.join(os.path.expanduser("~"), "OneDrive", "Pictures", "nova_screenshots", "reports")
        if not os.path.exists(reports_folder):
            os.makedirs(reports_folder)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        if student_name:
            # Specific student ka report
            student_key = student_name.lower().strip()
            if student_key not in students_data:
                return f"❌ {student_name} naam ka koi student nahi mila."
            
            student_data = students_data[student_key]
            report_path = os.path.join(reports_folder, f"{student_data['name']}_Progress_Report_{timestamp}.docx")
            await _generate_single_student_report(student_data, report_path)
            return f"✅ {student_data['name']} ka progress report generate ho gaya!\n📍 {report_path}"
        
        else:
            # All students ka combined report
            report_path = os.path.join(reports_folder, f"All_Students_Progress_Report_{timestamp}.docx")
            await _generate_all_students_report(students_data, report_path)
            return f"✅ Sab students ka combined progress report generate ho gaya!\n📍 {report_path}"
        
    except Exception as e:
        return f"❌ Report generate karne mein error: {str(e)}"
    
    
@function_tool()
async def _generate_single_student_report(student_data: Dict, report_path: str):
    """Generate report for a single student"""
    doc = Document()
    
    # Title with student name
    title = doc.add_heading(f'📚 {student_data["name"]} - Learning Progress Report', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Report generation date
    date_para = doc.add_paragraph(f"Report Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()
    
    # Student Info
    doc.add_heading('👤 Student Information', level=1)
    joined = datetime.fromisoformat(student_data["joined_date"]).strftime("%B %d, %Y")
    info_table = doc.add_table(rows=3, cols=2)
    info_table.style = 'Light Grid Accent 1'
    
    info_table.cell(0, 0).text = "Joined Date"
    info_table.cell(0, 1).text = joined
    info_table.cell(1, 0).text = "Total Study Time"
    info_table.cell(1, 1).text = f"{student_data['total_study_time']:.1f} hours"
    info_table.cell(2, 0).text = "Total Sessions"
    info_table.cell(2, 1).text = str(student_data["total_sessions"])
    
    doc.add_paragraph()
    
    # Summary statistics
    doc.add_heading('📊 Learning Summary', level=1)
    topics = student_data["topics"]
    total_topics = len(topics)
    completed = sum(1 for t in topics if t["status"] == "completed")
    in_progress = total_topics - completed
    
    stats_table = doc.add_table(rows=4, cols=2)
    stats_table.style = 'Light Grid Accent 1'
    
    stats_table.cell(0, 0).text = "Total Topics"
    stats_table.cell(0, 1).text = str(total_topics)
    stats_table.cell(1, 0).text = "Completed Topics"
    stats_table.cell(1, 1).text = str(completed)
    stats_table.cell(2, 0).text = "In Progress"
    stats_table.cell(2, 1).text = str(in_progress)
    stats_table.cell(3, 0).text = "Completion Rate"
    stats_table.cell(3, 1).text = f"{(completed/total_topics*100):.1f}%" if total_topics > 0 else "0%"
    
    doc.add_paragraph()
    
    # Topics by subject
    doc.add_heading('📝 Detailed Topic History', level=1)
    
    if topics:
        # Create table
        table = doc.add_table(rows=len(topics) + 1, cols=5)
        table.style = 'Light List Accent 1'
        
        # Header
        header_cells = table.rows[0].cells
        header_cells[0].text = "Topic"
        header_cells[1].text = "Subject"
        header_cells[2].text = "Status"
        header_cells[3].text = "Started"
        header_cells[4].text = "Duration"
        
        # Add topics (newest first)
        for i, topic in enumerate(reversed(topics), 1):
            cells = table.rows[i].cells
            cells[0].text = topic["topic"]
            cells[1].text = topic.get("subject", "General")
            
            # Status with emoji
            if topic["status"] == "completed":
                cells[2].text = "✅ Completed"
            else:
                cells[2].text = "🔄 In Progress"
            
            # Start date
            start_date = datetime.fromisoformat(topic["start_time"]).strftime("%b %d, %Y")
            cells[3].text = start_date
            
            # Duration
            if topic["status"] == "completed" and "duration" in topic:
                cells[4].text = f"{topic['duration']:.1f} hours"
            else:
                cells[4].text = "In progress"
    
    # Notes section if any
    has_notes = any(topic.get("notes") for topic in topics)
    if has_notes:
        doc.add_heading('📌 Important Notes', level=1)
        for topic in topics:
            if topic.get("notes"):
                doc.add_heading(f"{topic['topic']}:", level=2)
                for note in topic["notes"]:
                    note_date = datetime.fromisoformat(note["timestamp"]).strftime("%b %d, %Y")
                    doc.add_paragraph(f"• [{note_date}] {note['note']}", style='List Bullet')
    
    doc.save(report_path)
    
    
@function_tool()
async def _generate_all_students_report(students_data: Dict, report_path: str):
    """Generate combined report for all students"""
    doc = Document()
    
    # Title
    title = doc.add_heading('📚 All Students - Learning Progress Report', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Report generation date
    date_para = doc.add_paragraph(f"Report Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()
    
    # Overall statistics
    doc.add_heading('📊 Overall Statistics', level=1)
    
    total_students = len(students_data)
    total_topics_all = 0
    total_completed_all = 0
    total_study_time_all = 0
    
    for student_data in students_data.values():
        topics = student_data["topics"]
        total_topics_all += len(topics)
        total_completed_all += sum(1 for t in topics if t["status"] == "completed")
        total_study_time_all += student_data["total_study_time"]
    
    stats_table = doc.add_table(rows=4, cols=2)
    stats_table.style = 'Light Grid Accent 1'
    
    stats_table.cell(0, 0).text = "Total Students"
    stats_table.cell(0, 1).text = str(total_students)
    stats_table.cell(1, 0).text = "Total Topics"
    stats_table.cell(1, 1).text = str(total_topics_all)
    stats_table.cell(2, 0).text = "Total Completed Topics"
    stats_table.cell(2, 1).text = str(total_completed_all)
    stats_table.cell(3, 0).text = "Total Study Time"
    stats_table.cell(3, 1).text = f"{total_study_time_all:.1f} hours"
    
    doc.add_paragraph()
    
    # Individual student summaries
    doc.add_heading('👥 Individual Student Summaries', level=1)
    
    for student_key, student_data in students_data.items():
        doc.add_heading(f"📌 {student_data['name']}", level=2)
        
        topics = student_data["topics"]
        completed = sum(1 for t in topics if t["status"] == "completed")
        
        summary_table = doc.add_table(rows=3, cols=2)
        summary_table.style = 'Light List Accent 1'
        
        summary_table.cell(0, 0).text = "Total Topics"
        summary_table.cell(0, 1).text = str(len(topics))
        summary_table.cell(1, 0).text = "Completed"
        summary_table.cell(1, 1).text = str(completed)
        summary_table.cell(2, 0).text = "Study Time"
        summary_table.cell(2, 1).text = f"{student_data['total_study_time']:.1f} hours"
        
        doc.add_paragraph()
    
    doc.save(report_path)

@function_tool()
async def get_student_progress_summary(student_name: str) -> str:
    """
    Get a quick summary of a specific student's learning progress.
    
    Args:
        student_name: Student ka naam
    
    Returns:
        str: Quick progress summary for the student
    """
    try:
        student_data, _ = get_student_progress(student_name)
        topics = student_data["topics"]
        
        if not topics:
            return f"📝 {student_data['name']} ne abhi tak koi topic start nahi kiya hai."
        
        total_topics = len(topics)
        completed = sum(1 for t in topics if t["status"] == "completed")
        in_progress = total_topics - completed
        
        # Get current topics
        current_topics = [t for t in topics if t["status"] == "in_progress"]
        
        # Subjects breakdown
        subjects = student_data["subjects"]
        
        response = f"📊 **{student_data['name']} - Progress Summary**\n"
        response += f"• Total Topics: {total_topics}\n"
        response += f"• Completed: {completed}\n"
        response += f"• In Progress: {in_progress}\n"
        response += f"• Total Study Time: {student_data['total_study_time']:.1f} hours\n\n"
        
        if subjects:
            response += "**Subjects Breakdown:**\n"
            for subject, stats in subjects.items():
                response += f"• {subject}: {stats['completed']}/{stats['count']} completed\n"
        
        if current_topics:
            response += "\n**Currently Learning:**\n"
            for topic in current_topics:
                response += f"• {topic['topic']} ({topic.get('subject', 'General')})\n"
        
        return response
        
    except Exception as e:
        return f"❌ Progress check karne mein error: {str(e)}"