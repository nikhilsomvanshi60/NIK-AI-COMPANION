import psutil
from typing import Literal, Optional
from livekit.agents import function_tool

@function_tool()
async def process_manager(action: Literal["list", "kill"], process_name: Optional[str] = None, pid: Optional[int] = None) -> str:
    """
    Lists running system processes or terminates an unresponsive app by name or PID.
    
    Args:
        action: "list" to list high-resource processes or "kill" to force-terminate an app.
        process_name: Name of process to kill (e.g. "notepad")
        pid: Specific Process ID to kill
        
    Returns:
        str: Success or error report in Hindi/English.
    """
    try:
        if action == "list":
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'memory_percent', 'cpu_percent']):
                try:
                    processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Sort by memory usage
            sorted_proc = sorted(processes, key=lambda x: x['memory_percent'] or 0, reverse=True)
            report = "📊 **शीर्ष संसाधन प्रक्रियाएं (Top Resource Processes):**\n\n"
            for p in sorted_proc[:7]:
                mem_mb = round((p['memory_percent'] * psutil.virtual_memory().total) / 100 / (1024*1024), 1)
                report += f"- **{p['name']}** (PID: {p['pid']}) — Memory: {mem_mb} MB | CPU: {p['cpu_percent'] or 0}%\n"
            return report
            
        elif action == "kill":
            if not process_name and not pid:
                return "❌ कृपया बंद करने के लिए Process Name या PID प्रदान करें।"
            
            killed = []
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if pid and proc.info['pid'] == pid:
                        proc.kill()
                        return f"✅ PID {pid} ({proc.info['name']}) को बलपूर्वक बंद (Terminate) कर दिया गया है।"
                    if process_name and process_name.lower() in proc.info['name'].lower():
                        proc.kill()
                        killed.append(f"{proc.info['name']} (PID: {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if killed:
                return f"✅ इन ऐप्स को बंद कर दिया गया है: {', '.join(killed)}"
            else:
                return f"❌ '{process_name or pid}' नाम की कोई सक्रिय प्रक्रिया नहीं मिली।"
                
    except Exception as e:
        return f"❌ प्रोसेस मैनेजर त्रुटि: {str(e)}"
