import psutil
from typing import Literal
from livekit.agents import function_tool

def format_bytes(bytes_num: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_num < 1024.0:
            return f"{bytes_num:.2f} {unit}"
        bytes_num /= 1024.0
    return f"{bytes_num:.2f} PB"

@function_tool()
async def network_sentinel(action: Literal["scan_listeners", "bandwidth_stats"]) -> str:
    """
    Monitors active listener ports and tracks system bandwidth consumption to check for exfiltration.

    Args:
        action: "scan_listeners" to list listening sockets and associate processes,
                "bandwidth_stats" to retrieve bytes sent/received since boot.
    """
    try:
        if action == "scan_listeners":
            connections = psutil.net_connections(kind='inet')
            listeners = [c for c in connections if c.status == 'LISTEN']
            
            if not listeners:
                return "🛡️ **Port Listener Audit:** No open listening sockets detected."
                
            report = f"🌐 **Active Port Listeners ({len(listeners)} open ports):**\n\n"
            for c in listeners:
                local_addr = f"{c.laddr.ip}:{c.laddr.port}"
                try:
                    p = psutil.Process(c.pid)
                    proc_name = f"{p.name()} (PID: {c.pid})"
                except Exception:
                    proc_name = f"System/Unknown (PID: {c.pid})"
                
                # Highlight external or non-loopback listeners (listening on 0.0.0.0 or wildcard)
                wildcard = "[Wildcard Listener]" if c.laddr.ip in ["0.0.0.0", "::", "*"] else ""
                report += f"- **{proc_name}** is listening on `{local_addr}` {wildcard}\n"
            return report
            
        elif action == "bandwidth_stats":
            io_counters = psutil.net_io_counters()
            sent = format_bytes(io_counters.bytes_sent)
            recv = format_bytes(io_counters.bytes_recv)
            packets_sent = io_counters.packets_sent
            packets_recv = io_counters.packets_recv
            
            return (
                f"📊 **System Bandwidth Consumption Stats:**\n"
                f"- **Total Sent:** {sent} ({packets_sent} packets)\n"
                f"- **Total Received:** {recv} ({packets_recv} packets)\n\n"
                f"*Note: A sudden, unexplained spike in Sent bytes during idle time could indicate background data exfiltration.*"
            )

    except Exception as e:
        return f"❌ Network sentinel failure: {str(e)}"
