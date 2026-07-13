import socket
import urllib.request
import json
from typing import Literal, Optional
from livekit.agents import function_tool

COMMON_PORTS = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    135: "RPC",
    139: "NetBIOS",
    143: "IMAP",
    443: "HTTPS",
    445: "SMB",
    1433: "MSSQL",
    3306: "MySQL",
    3389: "RDP",
    8080: "HTTP-Alt"
}

@function_tool()
async def network_port_mapper(
    action: Literal["get_public_ip", "scan_local_ports"],
    host: Optional[str] = None
) -> str:
    """
    Retrieves public IP details, geolocation details, or scans specific ports of a host address.

    Args:
        action: "get_public_ip" to resolve local machine public IP address and geo details,
                "scan_local_ports" to scan open ports on target host.
        host: Target host IP/domain to scan (defaults to "127.0.0.1" for local port mapping).
    """
    try:
        if action == "get_public_ip":
            try:
                # Use robust ip-api.com service first
                req = urllib.request.Request(
                    "http://ip-api.com/json/",
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode())
                
                if data.get('status') == 'success':
                    return (
                        f"🌐 **Public IP & Geolocation Details:**\n"
                        f"- **IP Address:** {data.get('query')}\n"
                        f"- **City:** {data.get('city')}\n"
                        f"- **Region:** {data.get('regionName')} ({data.get('region')})\n"
                        f"- **Country:** {data.get('country')} ({data.get('countryCode')})\n"
                        f"- **ISP:** {data.get('isp')}\n"
                        f"- **Latitude / Longitude:** {data.get('lat')}, {data.get('lon')}"
                    )
                raise Exception("Service response status not success")
            except Exception as ex:
                # Fallback to ipapi.co
                try:
                    req = urllib.request.Request(
                        "https://ipapi.co/json/",
                        headers={'User-Agent': 'Mozilla/5.0'}
                    )
                    with urllib.request.urlopen(req, timeout=5) as response:
                        data = json.loads(response.read().decode())
                    return (
                        f"🌐 **Public IP & Geolocation Details (Backup):**\n"
                        f"- **IP Address:** {data.get('ip')}\n"
                        f"- **City:** {data.get('city')}\n"
                        f"- **Region:** {data.get('region')}\n"
                        f"- **Country:** {data.get('country_name')} ({data.get('country_code')})\n"
                        f"- **ISP:** {data.get('org')}\n"
                        f"- **Latitude / Longitude:** {data.get('latitude')}, {data.get('longitude')}"
                    )
                except Exception as ex2:
                    # Fallback to simple ipify
                    try:
                        with urllib.request.urlopen("https://api.ipify.org?format=json", timeout=3) as resp:
                            data = json.loads(resp.read().decode())
                        return f"🌐 **Public IP:** {data.get('ip')} (Detailed geo data fetch failed: {str(ex2)})"
                    except Exception as ex3:
                        return f"❌ Failed to reach IP lookup services: {str(ex3)}"
                    
        elif action == "scan_local_ports":
            target = host or "127.0.0.1"
            open_ports = []
            
            # Resolve host IP
            try:
                ip_addr = socket.gethostbyname(target)
            except socket.gaierror:
                return f"❌ Target host '{target}' could not be resolved."
            
            # Scan common ports
            for port, service in COMMON_PORTS.items():
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.4) # Fast timeout for local/nearby host
                result = s.connect_ex((ip_addr, port))
                if result == 0:
                    open_ports.append((port, service))
                s.close()
            
            report = f"🔌 **Port Map Scan Report for {target} ({ip_addr}):**\n\n"
            if not open_ports:
                report += "- All standard monitored ports are closed/filtered.\n"
            else:
                report += "🟢 **Open Ports:**\n"
                for port, service in open_ports:
                    report += f"  - Port **{port}** ({service})\n"
            return report

    except Exception as e:
        return f"❌ Port mapper failed: {str(e)}"
