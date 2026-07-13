"""
NIK — Voice Assistant ✦ 4-MODE THEME SYSTEM
Colors from original doc5, bright themes from doc6, circle bigger
"""
import sys, threading, time, subprocess, traceback, os, json, socket
sys.stdout.reconfigure(encoding='utf-8')
os.system("chcp 65001 >nul 2>&1")
from datetime import datetime
import psutil
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QMessageBox, QInputDialog, QDialog, QDialogButtonBox, QProgressBar, QLabel, QPushButton
from PyQt5.QtCore import Qt, QTimer, QUrl, pyqtSlot
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtCore import QObject, pyqtSignal
import firebase_admin
from firebase_admin import credentials, db; BASE_SECRET = "R7d9cQvPZ5mK2tYxW3nB8aJ4uH6sL1eT0gV9rC2pN7qD5fM8hK3zX1yU6jA4bS0iG7lE2oV9wQ5tR3nD8mC1kH6pJ4xZ0aY7"

PREMIUM_SECRET = "N4kM8qS1vH6cL2xT9eR5jU3pA7zY0wD8fG2bC6nV4mK1tQ9rJ5hX3lS7oE0iP8aZ2Y6uW3dR9"

ELITE_SECRET = "Z8xC1vB5nM2kL7jH3gF9dS4aA0pQ6wE2rT8yU1iO7lK3mN9cV5bX2zJ6hD4eR0tY8W3qP6uI1"

VARIANT_SECRET_MAP = {"base": BASE_SECRET, "premium": PREMIUM_SECRET, "elite": ELITE_SECRET}; VARIANT_NAMES = {"base": "Base", "premium": "Premium", "elite": "Elite"}; UPGRADE_PATHS = {"base": "elite", "premium": "elite", "elite": None}; MIC_ACTIVE = True
class SysInfo:
    cpu = 0.0; ram = 0.0; disk = 0.0; bat_pct = 100.0; bat_charging = True; bat_secs = 0; net_up = 0.0; net_dn = 0.0; gpu_load = 0.0; gpu_temp = 42.0; gpu_mhz = 300.0; cpu_temp = 0.0; _prev_net = None; _prev_net_t = None
    @classmethod
    def _poll(cls):
        try:
            cls.cpu = psutil.cpu_percent(interval=1.0)
            vm = psutil.virtual_memory()
            cls.ram = vm.percent
            cls.disk = psutil.disk_usage("/").percent
            b = psutil.sensors_battery()
            if b:
                cls.bat_pct = b.percent
                cls.bat_charging = b.power_plugged
                cls.bat_secs = 0
            net = psutil.net_io_counters()
            now = time.time()
            if cls._prev_net and cls._prev_net_t:
                dt = max(now - (cls._prev_net_t), 0.001)
                cls.net_up = ((net.bytes_sent) - (cls._prev_net.bytes_sent)) / dt / 1024
                cls.net_dn = ((net.bytes_recv) - (cls._prev_net.bytes_recv)) / dt / 1024
            cls._prev_net = net
            cls._prev_net_t = now
            r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,clocks.current.graphics", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=1)
            parts = r.stdout.strip().split(",")
            if len(parts) == 3:
                cls.gpu_load = float(parts[0])
                cls.gpu_temp = float(parts[1])
                cls.gpu_mhz = float(parts[2])
            
        except:
            pass
        time.sleep(2)
    
    @classmethod
    def start(cls):
        t = threading.Thread(target=cls._poll, daemon=True); t.start()
    
    @classmethod
    def bat_str(cls):
        if cls.bat_secs > 0:
            h = (cls.bat_secs) // 3600
            m = (cls.bat_secs) % 3600 // 60
            return f"{cls.bat_pct:.0f}% · {h}h {m:02d}m"
        
        return f"{cls.bat_pct:.0f}% · on battery"
    
    @classmethod
    def as_dict(cls):
        def fmtk(v):
            return f"{v:.0f} KB/s"
        
        mem_used = (psutil.virtual_memory().used) / 1_073_741_824
        return {"cpu": round(cls.cpu, 1), "ram": round(cls.ram, 1), "disk": round(cls.disk, 1), "gpu_load": round(cls.gpu_load, 1), "gpu_temp": round(cls.gpu_temp, 1), "gpu_mhz": round(cls.gpu_mhz, 0), "cpu_temp": round(cls.cpu_temp, 1), "bat": cls.bat_str(), "net_up": fmtk(cls.net_up), "net_dn": fmtk(cls.net_dn), "mem_used": f"{mem_used:.1f} GB ({cls.ram:.0f}%)"}

class Bridge(QObject):
    sysUpdate = pyqtSignal(str); chatUpdate = pyqtSignal(str); micChanged = pyqtSignal(bool); lockSignal = pyqtSignal(bool)
    def __init__(self):
        super().__init__(); self._mic_on = True; self._seen_count = 0; self._start_time = datetime.now(); self._last_mtime = None; self.MEMORY_FILE = "memory.json"
        import tools
        tools.bridge_instance = self
    
    @pyqtSlot(bool)
    def toggleMic(self, state):
        global MIC_ACTIVE
        self._mic_on = state; MIC_ACTIVE = state
        try:
            from ctypes import cast, POINTER
            import importlib
            comtypes = importlib.import_module("comtypes")
            CLSCTX_ALL = comtypes.CLSCTX_ALL
            pycaw_mod = importlib.import_module("pycaw.pycaw")
            AudioUtilities = pycaw_mod.AudioUtilities
            IAudioEndpointVolume = pycaw_mod.IAudioEndpointVolume
            
            devices = AudioUtilities.GetMicrophone()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMute(1, None)
        except Exception as e:
            print(f"Mic: {e}")
        
        self.micChanged.emit(state)
    
    @pyqtSlot(str)
    def setMode(self, mode):
        print(f"Mode: {mode}")
    
    def push_sys(self):
        self.sysUpdate.emit(json.dumps(SysInfo.as_dict()))
    
    def poll_memory(self):
        try:
            if not os.path.exists(self.MEMORY_FILE):
                if self._seen_count > 0:
                    self._seen_count = 0
                    self._last_mtime = None
                    self.chatUpdate.emit(json.dumps({"type": "clear"}))
                return
            mtime = os.path.getmtime(self.MEMORY_FILE)
            if mtime == self._last_mtime:
                return
            with open(self.MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            pass
        if not isinstance(data, list):
            return
        
        try:
            if self._last_mtime and len(data) < self._seen_count:
                self._seen_count = 0
                self.chatUpdate.emit(json.dumps({"type": "clear"}))
            self._last_mtime = mtime
            new_entries = data[self._seen_count:]
            emitted = 0
            for entry in new_entries:
                role = entry.get("role", "")
                content = entry.get("content", "")
                ts_raw = entry.get("timestamp", "")
                try:
                    msg_time = datetime.fromisoformat(ts_raw)
                    ts = msg_time.strftime("%H:%M")
                except:
                    msg_time = datetime.now()
                    ts = ""
                if msg_time < self._start_time:
                    emitted += 1
                    continue
                self.chatUpdate.emit(json.dumps({"type": "message", "role": role, "content": content, "ts": ts}))
                emitted += 1
            self._seen_count += emitted
        except Exception as e:
            print(f"Error emitting chat: {e}")

def get_service_json_path():
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, "voice.json")

def init_firebase_from_embedded(database_url=None):
    path = get_service_json_path()
    assert os.path.exists(path), f"Firebase service file not found: {path}"
    cred = credentials.Certificate(path)
    db_url = database_url or "https://nik-ai-new-default-rtdb.firebaseio.com/"
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(cred, {"databaseURL": db_url})
    check_license_and_bind_cloud()

def check_license_and_bind_cloud():
    import uuid, sys, subprocess, random, string
    from firebase_admin import db
    
    try:
        hwid = subprocess.check_output(
            'powershell -Command "(Get-CimInstance -Class Win32_ComputerSystemProduct).UUID"', 
            shell=True, 
            stderr=subprocess.DEVNULL
        ).decode().strip()
        if not hwid:
            raise Exception()
    except Exception:
        hwid = str(uuid.getnode())
        
    ref = db.reference("nik_licenses")
    licenses = ref.get()
    
    if not licenses:
        # Generate 5 fresh keys if node is completely empty
        licenses = {}
        for i in range(5):
            key_code = "NIK-" + "-".join(''.join(random.choices(string.ascii_uppercase + string.digits, k=4)) for _ in range(3))
            licenses[f"key_{i}"] = {"key": key_code, "hwid": None, "used": False}
        ref.set(licenses)
        
    # Check if already bound
    for k, lic in licenses.items():
        if lic.get('hwid') == hwid:
            return # Valid and bound
            
    # Try to bind a new key
    bound = False
    for k, lic in licenses.items():
        if not lic.get('used') and not lic.get('hwid'):
            lic['hwid'] = hwid
            lic['used'] = True
            ref.child(k).update({"hwid": hwid, "used": True})
            bound = True
            print(f"Cloud License {lic['key']} activated for HWID: {hwid}")
            break
            
    if not bound:
        from PyQt5.QtWidgets import QMessageBox, QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "License Error", "All 5 cloud access keys have been used! Cannot activate on this hardware.")
        sys.exit(1)

def set_env_variable(key, value):
    try:
        subprocess.run(["setx", key, value], shell=True, check=True)
    except:
        pass

def get_bool(value):
    if isinstance(value, bool):
        return value
    elif isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    
    return False

def detect_variant_and_ref(access_key):
    for variant in ("base", "premium", "elite"):
        ref = db.reference(f"NIK{variant}/{access_key}")
        record = ref.get()
        if record is None:
            return (variant, ref, record)
    
    return (None, None, None)

def prompt_access_key():
    key, ok = QInputDialog.getText(None, "Activation Required", "Enter your Access Key:")
    if ok and key.strip():
        return key.strip()

def prompt_user_name():
    name, ok = QInputDialog.getText(None, "User Setup - NIK", "Enter your name:")
    if not ok:
        if QMessageBox.question(None, "Confirm", "Use default 'User'?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            return "User"
    elif name.strip():
        return name.strip()
    QMessageBox.warning(None, "Invalid", "Name cannot be empty.")

def prompt_agent_name():
    name, ok = QInputDialog.getText(None, "User Setup - NIK", "Enter Assistant Name:")
    if not ok:
        if QMessageBox.question(None, "Confirm", "Use default 'NIK'?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            return "NIK"
    elif name.strip():
        return name.strip()

def prompt_lan():
    name, ok = QInputDialog.getText(None, "Language Setup", "Enter language (e.g. Hindi, English):")
    if not ok:
        if QMessageBox.question(None, "Confirm", "Use default 'Hindi'?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            return "Hindi"
    elif name.strip():
        return name.strip()

def ensure_user_name():
    current = os.getenv("USER_NAME", "").strip()
    if current:
        return current
    user_name = prompt_user_name(); mother_tongue = prompt_lan(); agent_name = prompt_agent_name(); set_env_variable("USER_NAME", user_name); set_env_variable("LAN", mother_tongue); set_env_variable("AGENT_NAME", agent_name)
    os.environ["USER_NAME"] = user_name; os.environ["LAN"] = mother_tongue; os.environ["AGENT_NAME"] = agent_name; return user_name

def activation_gate():
    access_key = os.getenv("ACCESS_KEY"); is_activated = os.getenv("IS_ACTIVATED", "").strip().lower() == "true"; current_variant = os.getenv("NIK_VARIANT", "")
    try:
        if not os.getenv("ACTIVATION_COUNT", "0").strip():
            activation_count = int("0")
        
    except Exception as e:
        QMessageBox.critical(None, "Error", f"Failed: {e}")
    return False
    
    set_env_variable("ACCESS_KEY", access_key)
    
    set_env_variable("IS_ACTIVATED", "true"); set_env_variable("ACTIVATION_COUNT", "1"); set_env_variable("NIK_VARIANT", variant)
    
    set_env_variable("SYSTEM_CONST_32", VARIANT_SECRET_MAP[variant])
    
    os.environ.update({"ACCESS_KEY": access_key, "IS_ACTIVATED": "true", "ACTIVATION_COUNT": "1", "NIK_VARIANT": variant, "SYSTEM_CONST_32": VARIANT_SECRET_MAP[variant]})
    return True

def safe_activation_gate():
    try:
        if activation_gate():
            return (True, "activated")
        return (False, "failed")
        return (False, "fallback")
    except:
        pass

class WaitForInternetDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("NIK - Waiting for Internet"); self.setFixedSize(400, 150)
        
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(); self.message_label = QLabel("🔍 Checking internet connection..."); self.message_label.setAlignment(Qt.AlignCenter)
        
        self.message_label.setWordWrap(True); layout.addWidget(self.message_label)
        
        self.progress_bar = QProgressBar(); self.progress_bar.setRange(0, 0); layout.addWidget(self.progress_bar); self.timer_label = QLabel("Next check in: 10 seconds")
        
        self.timer_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(self.timer_label); bb = QDialogButtonBox(); self.cancel_button = bb.addButton("Cancel", QDialogButtonBox.RejectRole)
        
        layout.addWidget(bb); self.setLayout(layout); self.cancel_button.clicked.connect(self.reject); self.seconds_remaining = 10; QTimer.singleShot(500, self.check_internet)
    
    def check_internet(self):
        if self._is_internet_available():
            self.message_label.setText("✅ Connected!")
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)
            QTimer.singleShot(800, self.accept)
            return
        self.seconds_remaining = 10; self.message_label.setText("❌ No internet. Retrying...")
        
        self._start_countdown()
    
    def _start_countdown(self):
        self.countdown_timer = QTimer(); self.countdown_timer.timeout.connect(self._update_countdown); self.countdown_timer.start(1000)
    
    def _update_countdown(self):
        self.seconds_remaining -= 1; self.timer_label.setText(f"Next check in: {self.seconds_remaining} seconds")
        match self:
            case 0:
                pass
    
    def _is_internet_available(self):
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            return True
            socket.create_connection(("google.com", 80), timeout=5)
        except:
            pass
        
        return True; return False

def wait_for_internet():
    d = WaitForInternetDialog()
    return d.exec_() == QDialog.Accepted

NIK_HTML = "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\"/>\n<meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\"/>\n<title>NIK - ELYSIAN Assistant</title>\n<link href='https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&family=Rajdhani:wght@300;400;500;600;700&family=Share+Tech+Mono&display=swap' rel='stylesheet' />\n<style>\n\n/* ══════════════════════════════════════════════\n   4 THEMES — Doc1 PyQt5 colors ported to CSS\n══════════════════════════════════════════════ */\n:root{\n  --bg:#00060f;--c1:#00d4ff;--c2:#00a8d4;--c3:#0077b6;--c4:#00f5ff;\n  --c-glow:rgba(0,212,255,0.25);--green:#00ff88;\n  --text:#d0f0ff;--text2:#6a9fb8;--text3:#2a5570;\n  --border:rgba(0,180,230,0.14);--border2:rgba(0,200,255,0.28);--border3:rgba(0,220,255,0.45);\n  --font-display:'Orbitron',sans-serif;--font-ui:'Rajdhani',sans-serif;--font-mono:'Share Tech Mono',monospace;\n  --r:10px;--r2:6px;--theme-trans:all 0.55s cubic-bezier(0.4,0,0.2,1);\n}\n\n/* ── SILENT — Soft indigo-violet (doc1 Silent palette) ── */\nbody.theme-silent{\n  --bg:#050209;--bg2:#0a0414;\n  --c1:#a78bfa;--c2:#7c5de8;--c3:#4c1d95;--c4:#c4b5fd;\n  --c-glow:rgba(167,139,250,0.45);\n  --green:#e879f9;--green2:#a78bfa;\n  --text:#ede9fe;--text2:#8b72c8;--text3:#3d2870;\n  --border:rgba(124,93,232,0.20);--border2:rgba(167,139,250,0.50);--border3:rgba(196,181,253,0.72);\n}\n\n/* ── BALANCED — Beautiful Cyan/Teal (modern & balanced) ── */\nbody.theme-balanced{\n  --bg:#000f16;--bg2:#001a26;\n  --c1:#00bcd4;--c2:#0088a8;--c3:#004d7a;--c4:#26dfc7;\n  --c-glow:rgba(0,188,212,0.40);\n  --green:#00bcd4;--green2:#26dfc7;\n  --text:#d0f0ff;--text2:#5fb8d4;--text3:#1a5070;\n  --border:rgba(0,188,212,0.20);--border2:rgba(0,188,212,0.46);--border3:rgba(38,223,199,0.68);\n}\n\n/* ── PERFORMANCE — Fiery orange-red (doc1 Turbo pink → orange) ── */\nbody.theme-performance{\n  --bg:#080300;--bg2:#120500;\n  --c1:#ff6b1a;--c2:#ff8c00;--c3:#8b0000;--c4:#ffd700;\n  --c-glow:rgba(255,107,26,0.44);\n  --green:#ff8c00;--green2:#ffd700;\n  --text:#fff4e0;--text2:#e08040;--text3:#6a2800;\n  --border:rgba(255,107,26,0.20);--border2:rgba(255,107,26,0.48);--border3:rgba(255,200,0,0.68);\n}\n\n/* ── TURBO — Blood Red + Ultraviolet + Deep Magenta ── */\nbody.theme-turbo{\n  --bg:#06000a;--bg2:#0e0012;\n  --c1:#ff0050;--c2:#aa00ff;--c3:#ff00aa;--c4:#6600ff;\n  --c-glow:rgba(255,0,80,0.52);\n  --green:#ff0050;--green2:#aa00ff;\n  --text:#ffe0ee;--text2:#cc70a0;--text3:#5a1030;\n  --border:rgba(255,0,80,0.22);--border2:rgba(170,0,255,0.52);--border3:rgba(255,0,170,0.72);\n}\n\nbody.theme-turbo #navbar::after{\n  background:linear-gradient(90deg,transparent,#ff0050,#aa00ff,#ff00aa,#6600ff,#ff0050,transparent);\n  animation:nav-shimmer 1.8s linear infinite;\n}\nbody.theme-turbo #bottom-bar::before{\n  background:linear-gradient(90deg,transparent,#ff0050,#aa00ff,#ff00aa,transparent);\n  opacity:0.8;\n}\n\n*{margin:0;padding:0;box-sizing:border-box;}\nhtml,body{width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text);transition:background 0.55s ease,color 0.55s ease;}\n::selection{background:rgba(255,255,255,0.2);color:#fff;}\n::-webkit-scrollbar{width:3px;}\n::-webkit-scrollbar-track{background:transparent;}\n::-webkit-scrollbar-thumb{background:linear-gradient(180deg,var(--c1),var(--c3));border-radius:2px;}\n\n#theme-overlay{position:fixed;inset:0;z-index:9999;pointer-events:none;opacity:0;transition:opacity 0.15s ease;}\n#theme-overlay.flash{opacity:0.06;}\n\n#app{display:grid;grid-template-rows:52px 1fr 58px;height:100vh;width:100vw;position:relative;}\n#bg-canvas{position:fixed;inset:0;z-index:0;pointer-events:none;}\n\n/* ── NAVBAR ── */\n#navbar{\n  display:flex;align-items:center;padding:0 20px;\n  background:linear-gradient(180deg,rgba(0,0,0,0.97) 0%,rgba(0,0,0,0.93) 100%);\n  border-bottom:1px solid var(--border2);\n  position:relative;z-index:200;\n  box-shadow:0 1px 50px var(--c-glow);\n  transition:border-color 0.55s,box-shadow 0.55s;\n}\n#navbar::after{content:'';position:absolute;bottom:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--c1),var(--c4),var(--c1),transparent);animation:nav-shimmer 3s linear infinite;}\n@keyframes nav-shimmer{0%{opacity:0.4}50%{opacity:1}100%{opacity:0.4}}\n.logo-wrap{display:flex;align-items:center;gap:10px;margin-right:24px;}\n.logo-text{font-family:var(--font-display);font-size:18px;font-weight:900;letter-spacing:6px;background:linear-gradient(135deg,#ffffff 0%,var(--c1) 40%,var(--c4) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;transition:var(--theme-trans);}\n.logo-sub{font-family:var(--font-mono);font-size:8px;color:var(--text3);letter-spacing:2px;margin-top:-2px;}\n.nav-sep{width:1px;height:28px;background:var(--border2);margin:0 16px;transition:background 0.55s;}\n.nav-btn{height:52px;padding:0 18px;background:transparent;border:none;color:var(--text2);font-family:var(--font-mono);font-size:10px;cursor:pointer;letter-spacing:2px;transition:all 0.25s;position:relative;}\n.nav-btn::before{content:'';position:absolute;bottom:0;left:50%;right:50%;height:2px;background:linear-gradient(90deg,transparent,var(--c1),transparent);transition:all 0.3s;}\n.nav-btn:hover{color:var(--c1);}\n.nav-btn:hover::before,.nav-btn.active::before{left:10%;right:10%;}\n.nav-btn.active{color:var(--c1);}\n.nav-status{display:flex;align-items:center;gap:6px;padding:4px 12px;margin-left:8px;background:rgba(0,0,0,0.5);border:1px solid var(--border2);border-radius:20px;transition:var(--theme-trans);}\n.status-dot{width:5px;height:5px;background:var(--c1);border-radius:50%;box-shadow:0 0 10px var(--c1),0 0 20px var(--c-glow);animation:blink 1.8s ease-in-out infinite;transition:background 0.55s,box-shadow 0.55s;}\n@keyframes blink{0%,100%{opacity:1}50%{opacity:0.35}}\n.status-txt{font-family:var(--font-mono);font-size:9px;color:var(--c1);letter-spacing:2px;transition:color 0.55s;}\n.nav-right{margin-left:auto;display:flex;align-items:center;gap:4px;}\n.sys-time{font-family:var(--font-mono);font-size:11px;color:var(--text3);margin-right:12px;letter-spacing:1px;}\n.win-btn{width:28px;height:28px;background:transparent;border:1px solid transparent;color:var(--text3);font-size:11px;cursor:pointer;border-radius:6px;transition:all 0.2s;display:flex;align-items:center;justify-content:center;}\n.win-btn:hover{color:var(--c1);border-color:var(--border2);background:rgba(0,0,0,0.4);}\n.win-btn.close:hover{color:#ff4466;border-color:rgba(255,51,85,0.4);background:rgba(255,51,85,0.1);}\n\n/* ── LAYOUT ── */\n#body{display:grid;grid-template-columns:272px 1fr 320px;gap:8px;padding:8px 8px 0 8px;overflow:hidden;position:relative;z-index:1;grid-row:2;height:100%;}\n#left,#center,#right{display:flex;flex-direction:column;gap:8px;overflow:hidden;height:100%;min-height:0;}\n\n/* ── GLASS CARD ── */\n.card{background:linear-gradient(145deg,rgba(0,0,0,0.86) 0%,rgba(0,0,0,0.91) 100%);border:1px solid var(--border);border-radius:var(--r);position:relative;overflow:hidden;box-shadow:0 0 0 1px rgba(0,0,0,0.6) inset,0 8px 40px rgba(0,0,0,0.6),0 0 60px var(--c-glow);transition:border-color 0.55s,box-shadow 0.55s;}\n.card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--c1),var(--c4),var(--c1),transparent);opacity:0.6;transition:var(--theme-trans);}\n.card-scan::after{content:'';position:absolute;left:0;right:0;height:100px;pointer-events:none;background:linear-gradient(180deg,transparent,rgba(255,255,255,0.016),transparent);animation:scan-anim 7s linear infinite;}\n@keyframes scan-anim{0%{top:-100px}100%{top:100%}}\n.card-corners .cc{position:absolute;width:11px;height:11px;border-color:var(--c1);border-style:solid;opacity:0.65;transition:border-color 0.55s;box-shadow:0 0 5px var(--c-glow);}\n.cc.tl{top:6px;left:6px;border-width:1px 0 0 1px;}.cc.tr{top:6px;right:6px;border-width:1px 1px 0 0;}\n.cc.bl{bottom:6px;left:6px;border-width:0 0 1px 1px;}.cc.br{bottom:6px;right:6px;border-width:0 1px 1px 0;}\n\n/* ── SECTION HEADER ── */\n.sh{display:flex;align-items:center;gap:8px;margin-bottom:12px;}\n.sh-diamond{width:8px;height:8px;background:var(--c1);transform:rotate(45deg);box-shadow:0 0 12px var(--c1),0 0 24px var(--c-glow);animation:diamond-pulse 2s ease-in-out infinite;flex-shrink:0;transition:background 0.55s,box-shadow 0.55s;}\n@keyframes diamond-pulse{0%,100%{box-shadow:0 0 8px var(--c1),0 0 16px var(--c-glow)}50%{box-shadow:0 0 20px var(--c1),0 0 40px var(--c-glow)}}\n.sh-text{font-family:var(--font-mono);font-size:9px;letter-spacing:3px;color:var(--text2);transition:color 0.55s;}\n.sh-line{flex:1;height:1px;background:linear-gradient(90deg,var(--border2),transparent);transition:background 0.55s;}\n.sh-tag{font-family:var(--font-mono);font-size:8px;color:var(--c1);padding:2px 7px;border:1px solid var(--border2);border-radius:3px;background:rgba(0,0,0,0.4);transition:var(--theme-trans);}\n\n/* ── STAT BARS ── */\n.stat-row{margin-bottom:10px;}\n.stat-top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:5px;}\n.stat-lbl{font-family:var(--font-mono);font-size:8px;letter-spacing:2px;color:var(--text3);}\n.stat-num{font-family:var(--font-display);font-size:13px;font-weight:700;color:var(--c1);transition:color 0.55s;text-shadow:0 0 10px var(--c-glow);}\n.stat-unit{font-family:var(--font-mono);font-size:8px;color:var(--text3);margin-left:1px;}\n.stat-track{height:4px;background:rgba(255,255,255,0.05);border-radius:2px;overflow:visible;position:relative;}\n.stat-bg-grid{position:absolute;inset:0;background:repeating-linear-gradient(90deg,rgba(255,255,255,0.04) 0px,rgba(255,255,255,0.04) 1px,transparent 1px,transparent 10%);}\n.stat-fill{height:100%;border-radius:2px;transition:width 1.2s cubic-bezier(0.23,1,0.32,1),background 0.55s;position:relative;background:linear-gradient(90deg,var(--c3),var(--c1),var(--c4));}\n.stat-fill::after{content:'';position:absolute;right:-1px;top:-4px;bottom:-4px;width:4px;background:var(--c4);border-radius:2px;box-shadow:0 0 12px var(--c4),0 0 24px var(--c-glow);transition:var(--theme-trans);}\n.stat-fill.warn{background:linear-gradient(90deg,#7a3a00,#ff8c00);}\n.stat-fill.hot{background:linear-gradient(90deg,#7a0020,#ff2244);}\n\n/* ── GPU BADGE ── */\n.gpu-badge{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;margin-bottom:10px;background:rgba(0,0,0,0.4);border:1px solid var(--border2);border-radius:var(--r2);box-shadow:0 0 18px var(--c-glow);transition:var(--theme-trans);}\n.gpu-freq{font-family:var(--font-display);font-size:24px;font-weight:800;color:var(--c1);text-shadow:0 0 22px var(--c-glow);transition:color 0.55s,text-shadow 0.55s;}\n.gpu-meta-row{font-family:var(--font-mono);font-size:9px;color:var(--text2);display:block;}\n.gpu-meta-val{color:var(--c1);text-shadow:0 0 8px var(--c-glow);transition:color 0.55s;}\n\n/* ── VOICE ── */\n.voice-wrap{display:flex;flex-direction:column;align-items:center;gap:8px;}\n#orb-canvas{width:150px;height:150px;flex-shrink:0;}\n#waveform{width:100%;height:46px;}\n#mic-btn{width:100%;height:36px;border-radius:var(--r2);font-family:var(--font-mono);font-size:10px;letter-spacing:2px;cursor:pointer;transition:all 0.35s;border:1px solid;}\n#mic-btn.on{color:var(--c1);border-color:var(--border2);background:rgba(0,0,0,0.5);box-shadow:0 0 22px var(--c-glow) inset,0 0 12px var(--c-glow);}\n#mic-btn.off{color:var(--text2);border-color:var(--border);background:rgba(0,0,0,0.4);}\n#mic-btn:hover{filter:brightness(1.2);transform:translateY(-1px);}\n\n/* ── TILES ── */\n.tile{display:flex;align-items:center;gap:10px;padding:8px 10px;border:1px solid var(--border);border-radius:var(--r2);margin-bottom:6px;background:rgba(0,0,0,0.38);transition:all 0.35s;}\n.tile:hover{border-color:var(--border2);box-shadow:0 0 12px var(--c-glow);}\n.tile-orb{width:32px;height:32px;border-radius:50%;flex-shrink:0;border:1px solid var(--border2);background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;font-size:14px;box-shadow:0 0 8px var(--c-glow);transition:border-color 0.55s,box-shadow 0.55s;}\n.tile-lbl{font-family:var(--font-mono);font-size:7.5px;letter-spacing:2px;color:var(--text3);display:block;}\n.tile-val{font-family:var(--font-mono);font-size:11px;font-weight:500;color:var(--text);display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}\n.tile-bar{height:2px;background:var(--border);border-radius:1px;margin-top:4px;overflow:hidden;}\n.tile-bar-fill{height:100%;border-radius:1px;background:linear-gradient(90deg,var(--c3),var(--c1));transition:width 1s ease,background 0.55s;}\n\n/* ── CENTER ── */\n#center{flex:1;min-height:0;display:flex;flex-direction:column;}\n#center .card{flex:1;display:flex;flex-direction:column;overflow:hidden;}\n#core-inner{flex:1;padding:14px 16px 12px 16px;display:flex;flex-direction:column;overflow:hidden;min-height:0;}\n#NIK-hero{text-align:center;padding-bottom:8px;position:relative;flex-shrink:0;}\n#NIK-letters{\n  font-family:var(--font-display);font-size:60px;font-weight:900;letter-spacing:16px;line-height:1;display:inline-block;\n  background:linear-gradient(135deg,var(--c3) 0%,var(--c1) 45%,var(--c4) 100%);\n  -webkit-background-clip:text;-webkit-text-fill-color:transparent;\n  filter:drop-shadow(0 0 28px var(--c-glow));\n  animation:hero-breathe 4s ease-in-out infinite;transition:filter 0.55s;\n}\n@keyframes hero-breathe{0%,100%{filter:drop-shadow(0 0 18px var(--c-glow)) drop-shadow(0 0 36px var(--c-glow))}50%{filter:drop-shadow(0 0 48px var(--c-glow)) drop-shadow(0 0 90px var(--c-glow))}}\n.hero-tagline{font-family:var(--font-mono);font-size:9px;letter-spacing:5px;color:var(--text3);margin-top:4px;text-align:center;}\n.hero-underline{width:200px;height:1px;margin:8px auto 0;background:linear-gradient(90deg,transparent,var(--c1),var(--c4),var(--c1),transparent);animation:underline-flow 3s ease-in-out infinite;}\n@keyframes underline-flow{0%,100%{opacity:0.5;width:140px}50%{opacity:1;width:220px}}\n.ai-status-bar{display:flex;align-items:center;gap:10px;padding:7px 14px;margin-bottom:8px;background:rgba(0,0,0,0.45);border:1px solid var(--border2);border-radius:var(--r2);box-shadow:0 0 18px var(--c-glow);flex-shrink:0;transition:var(--theme-trans);}\n.ai-dot{width:6px;height:6px;background:var(--c1);border-radius:50%;box-shadow:0 0 10px var(--c1),0 0 20px var(--c-glow);animation:blink 1.8s ease-in-out infinite;transition:background 0.55s,box-shadow 0.55s;}\n.ai-status-txt{font-family:var(--font-mono);font-size:9px;color:var(--c1);letter-spacing:2px;text-shadow:0 0 8px var(--c-glow);transition:color 0.55s,text-shadow 0.55s;}\n.ai-mode-lbl{margin-left:auto;font-family:var(--font-display);font-size:11px;font-weight:700;color:var(--c1);letter-spacing:3px;text-shadow:0 0 12px var(--c-glow);transition:color 0.55s,text-shadow 0.55s;}\n#plasma-wrap{flex:1;position:relative;min-height:0;border-radius:var(--r2);overflow:hidden;background:rgba(0,0,0,0.28);box-shadow:0 0 50px var(--c-glow) inset;transition:box-shadow 0.55s;}\n#plasma{width:100%;height:100%;display:block;}\n\n/* ── BOTTOM MODE BAR ── */\n#bottom-bar{grid-row:3;display:flex;align-items:center;justify-content:center;gap:10px;padding:8px 16px;background:linear-gradient(180deg,rgba(0,0,0,0) 0%,rgba(0,0,0,0.95) 100%);border-top:1px solid var(--border2);position:relative;z-index:10;transition:border-color 0.55s;}\n#bottom-bar::before{content:'';position:absolute;top:0;left:5%;right:5%;height:1px;background:linear-gradient(90deg,transparent,var(--c1),var(--c4),var(--c1),transparent);opacity:0.5;transition:var(--theme-trans);}\n.mode-btn{width:180px;height:40px;background:rgba(0,0,0,0.55);border:1px solid var(--border);border-radius:var(--r2);color:var(--text3);font-family:var(--font-mono);font-size:9px;cursor:pointer;letter-spacing:2px;transition:all 0.3s;position:relative;overflow:hidden;}\n.mode-btn:hover{color:var(--text2);border-color:var(--border2);box-shadow:0 0 10px var(--c-glow);}\n.mode-btn.active{color:var(--c1);border-color:var(--c1);box-shadow:0 0 22px var(--c-glow),0 0 0 1px var(--border2) inset;text-shadow:0 0 8px var(--c-glow);}\n.mode-btn.active::before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(255,255,255,0.10),rgba(255,255,255,0.02));}\n.mode-btn.active::after{content:'';position:absolute;bottom:0;left:10%;right:10%;height:2px;background:linear-gradient(90deg,transparent,var(--c1),var(--c4),var(--c1),transparent);}\n.mode-btn .pip{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:6px;vertical-align:middle;}\n/* Doc5 pip colors */\n.mode-btn[data-mode=\"Silent\"] .pip{background:#a78bfa;box-shadow:0 0 8px #a78bfa;}\n.mode-btn[data-mode=\"Balanced\"] .pip{background:#10e89a;box-shadow:0 0 8px #10e89a;}\n.mode-btn[data-mode=\"Performance\"] .pip{background:#ff6b1a;box-shadow:0 0 8px #ff6b1a;}\n.mode-btn[data-mode=\"Turbo\"] .pip{\n  background:#ff0050;\n  box-shadow:0 0 8px #ff0050, 0 0 16px rgba(170,0,255,0.6);\n}\n.mode-btn.active .pip{animation:pip-pulse 1.2s ease-in-out infinite;}\n@keyframes pip-pulse{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.6);opacity:0.7}}\n\n/* ── CHAT ── */\n#chat-card{flex:1;display:flex;flex-direction:column;overflow:hidden;min-height:0;}\n#chat-inner{flex:1;padding:14px;display:flex;flex-direction:column;overflow:hidden;gap:10px;min-height:0;}\n#chat-top{display:flex;align-items:center;gap:8px;padding-bottom:10px;border-bottom:1px solid var(--border2);transition:border-color 0.55s;}\n.chat-title{font-family:var(--font-mono);font-size:9px;letter-spacing:3px;color:var(--text2);}\n.live-badge{display:flex;align-items:center;gap:5px;padding:3px 10px;background:rgba(0,0,0,0.5);border:1px solid var(--border2);border-radius:20px;margin-left:auto;box-shadow:0 0 10px var(--c-glow);transition:var(--theme-trans);}\n.live-dot{width:5px;height:5px;background:var(--c1);border-radius:50%;box-shadow:0 0 8px var(--c1),0 0 16px var(--c-glow);animation:blink 1.4s ease-in-out infinite;transition:background 0.55s,box-shadow 0.55s;}\n.live-txt{font-family:var(--font-mono);font-size:8px;letter-spacing:2px;color:var(--c1);text-shadow:0 0 6px var(--c-glow);transition:color 0.55s,text-shadow 0.55s;}\n#chat-scroll{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:8px;padding:2px 0;}\n#chat-empty{margin:auto;text-align:center;color:var(--text3);font-family:var(--font-ui);font-size:13px;line-height:1.9;}\n#chat-empty .empty-icon{font-size:28px;display:block;margin-bottom:8px;opacity:0.45;}\n.bw{display:flex;gap:8px;align-items:flex-end;animation:fade-up 0.3s ease;}\n@keyframes fade-up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}\n.bw.user{flex-direction:row-reverse;}\n.av{width:28px;height:28px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-family:var(--font-mono);font-size:9px;font-weight:600;}\n.av.NIK{background:rgba(0,0,0,0.85);border:1px solid var(--border2);color:var(--c1);box-shadow:0 0 14px var(--c-glow);transition:var(--theme-trans);}\n.av.user{background:rgba(0,0,0,0.65);border:1px solid var(--border2);color:var(--text);transition:var(--theme-trans);}\n.bbl-wrap{display:flex;flex-direction:column;max-width:195px;}\n.bbl{padding:9px 13px;font-family:var(--font-ui);font-size:12px;line-height:1.6;}\n.bbl.NIK{background:rgba(0,0,0,0.78);border:1px solid var(--border2);border-radius:3px 14px 14px 14px;color:var(--text);box-shadow:0 4px 20px rgba(0,0,0,0.5),0 0 8px var(--c-glow);transition:var(--theme-trans);}\n.bbl.user{background:rgba(0,0,0,0.60);border:1px solid var(--border3);border-radius:14px 3px 14px 14px;color:var(--text);transition:var(--theme-trans);}\n.bbl-ts{font-family:var(--font-mono);font-size:8px;color:var(--text3);margin-top:3px;padding:0 2px;}\n.bw.user .bbl-ts{text-align:right;}\n#typing-row{display:none;gap:8px;align-items:flex-end;}\n.typing-bbl{padding:10px 16px;background:rgba(0,0,0,0.75);border:1px solid var(--border2);border-radius:3px 14px 14px 14px;display:flex;gap:5px;align-items:center;transition:var(--theme-trans);}\n.typing-bbl span{width:5px;height:5px;background:var(--c1);border-radius:50%;animation:tdot 1.5s ease-in-out infinite;transition:background 0.55s;box-shadow:0 0 5px var(--c-glow);}\n.typing-bbl span:nth-child(2){animation-delay:.18s;}\n.typing-bbl span:nth-child(3){animation-delay:.36s;}\n@keyframes tdot{0%,60%,100%{transform:translateY(0);opacity:0.3}30%{transform:translateY(-6px);opacity:1}}\n#quick-row{display:flex;gap:6px;flex-wrap:wrap;}\n.qb{padding:5px 12px;background:rgba(0,0,0,0.55);border:1px solid var(--border);border-radius:20px;color:var(--text2);font-family:var(--font-mono);font-size:9px;cursor:pointer;letter-spacing:1px;transition:all 0.2s;}\n.qb:hover{border-color:var(--border3);color:var(--c1);background:rgba(0,0,0,0.75);box-shadow:0 0 10px var(--c-glow);}\n#inp-row{display:flex;align-items:center;gap:8px;padding:8px 12px;background:rgba(0,0,0,0.72);border:1px solid var(--border2);border-radius:var(--r);transition:var(--theme-trans);}\n#inp-row:focus-within{border-color:var(--c1);box-shadow:0 0 22px var(--c-glow);}\n.inp-mic{font-size:15px;cursor:pointer;opacity:0.7;transition:opacity 0.2s;flex-shrink:0;}\n.inp-mic:hover{opacity:1;}\n#chat-inp{flex:1;background:transparent;border:none;outline:none;color:var(--text);font-family:var(--font-ui);font-size:13px;}\n#chat-inp::placeholder{color:var(--text3);}\n#send-btn{width:32px;height:32px;flex-shrink:0;background:linear-gradient(135deg,var(--c3),var(--c1));border:1px solid var(--border2);border-radius:var(--r2);color:#000;font-size:13px;font-weight:bold;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.3s;box-shadow:0 0 12px var(--c-glow);}\n#send-btn:hover{filter:brightness(1.25);box-shadow:0 0 22px var(--c-glow);transform:scale(1.05);}\n</style>\n</head>\n<body class=\"theme-turbo\">\n<div id=\"theme-overlay\"></div>\n<canvas id=\"bg-canvas\"></canvas>\n<div id=\"app\">\n<nav id=\"navbar\">\n  <div class=\"logo-wrap\">\n    <canvas id=\"logo-icon\" width=\"32\" height=\"32\" style=\"width:32px;height:32px;flex-shrink:0;\"></canvas>\n    <div><div class=\"logo-text\">NIK</div><div class=\"logo-sub\">VOICE ASSISTANT</div></div>\n  </div>\n  <div class=\"nav-sep\"></div>\n  <button class=\"nav-btn active\" onclick=\"setNav(this)\">HOME</button>\n  <button class=\"nav-btn\" onclick=\"setNav(this)\">VOICE AI</button>\n  <button class=\"nav-btn\" onclick=\"setNav(this)\">MONITORING</button>\n  <button class=\"nav-btn\" onclick=\"setNav(this)\">SETTINGS</button>\n  <div class=\"nav-sep\"></div>\n  <div class=\"nav-status\"><div class=\"status-dot\"></div><span class=\"status-txt\" id=\"ai-status-txt\">AI CORE ONLINE</span></div>\n  <div class=\"nav-right\">\n    <div class=\"sys-time\" id=\"clock\">00:00:00</div>\n    <button class=\"win-btn\" onclick=\"winMin()\">—</button>\n    <button class=\"win-btn\" onclick=\"winMax()\">⬜</button>\n    <button class=\"win-btn close\" onclick=\"winClose()\">✕</button>\n  </div>\n</nav>\n<div id=\"body\">\n  <!-- LEFT -->\n  <div id=\"left\">\n    <div class=\"card card-scan card-corners\" style=\"padding:14px;\">\n      <div class=\"cc tl\"></div><div class=\"cc tr\"></div><div class=\"cc bl\"></div><div class=\"cc br\"></div>\n      <div class=\"sh\"><div class=\"sh-diamond\"></div><span class=\"sh-text\">SYSTEM MONITOR</span><div class=\"sh-line\"></div><span class=\"sh-tag\">LIVE</span></div>\n      <div class=\"gpu-badge\">\n        <div><div style=\"font-family:var(--font-mono);font-size:8px;letter-spacing:2px;color:var(--text3);margin-bottom:2px;\">GPU CLOCK</div><div class=\"gpu-freq\" id=\"gpu-freq\">300</div><div style=\"font-family:var(--font-mono);font-size:8px;color:var(--text3);\">MHz</div></div>\n        <div><span class=\"gpu-meta-row\">TEMP &nbsp;<span class=\"gpu-meta-val\" id=\"gpu-temp\">42°C</span></span><span class=\"gpu-meta-row\" style=\"margin-top:4px;\">LOAD &nbsp;<span class=\"gpu-meta-val\" id=\"gpu-load\">0%</span></span></div>\n      </div>\n      <div class=\"stat-row\"><div class=\"stat-top\"><span class=\"stat-lbl\">GPU USAGE</span><span><span class=\"stat-num\" id=\"sn-gpu\">0</span><span class=\"stat-unit\">%</span></span></div><div class=\"stat-track\"><div class=\"stat-bg-grid\"></div><div class=\"stat-fill\" id=\"sf-gpu\" style=\"width:0%\"></div></div></div>\n      <div class=\"stat-row\"><div class=\"stat-top\"><span class=\"stat-lbl\">CPU USAGE</span><span><span class=\"stat-num\" id=\"sn-cpu\">0</span><span class=\"stat-unit\">%</span></span></div><div class=\"stat-track\"><div class=\"stat-bg-grid\"></div><div class=\"stat-fill\" id=\"sf-cpu\" style=\"width:0%\"></div></div></div>\n      <div class=\"stat-row\"><div class=\"stat-top\"><span class=\"stat-lbl\">RAM USAGE</span><span><span class=\"stat-num\" id=\"sn-ram\">0</span><span class=\"stat-unit\">%</span></span></div><div class=\"stat-track\"><div class=\"stat-bg-grid\"></div><div class=\"stat-fill\" id=\"sf-ram\" style=\"width:0%\"></div></div></div>\n      <div class=\"stat-row\" style=\"margin-bottom:0\"><div class=\"stat-top\"><span class=\"stat-lbl\">DISK USAGE</span><span><span class=\"stat-num\" id=\"sn-disk\">0</span><span class=\"stat-unit\">%</span></span></div><div class=\"stat-track\"><div class=\"stat-bg-grid\"></div><div class=\"stat-fill\" id=\"sf-disk\" style=\"width:0%\"></div></div></div>\n    </div>\n    <div class=\"card card-corners\" style=\"padding:14px;\">\n      <div class=\"cc tl\"></div><div class=\"cc tr\"></div><div class=\"cc bl\"></div><div class=\"cc br\"></div>\n      <div class=\"sh\"><div class=\"sh-diamond\"></div><span class=\"sh-text\">VOICE ENGINE</span><div class=\"sh-line\"></div></div>\n      <div class=\"voice-wrap\">\n        <canvas id=\"orb-canvas\" width=\"150\" height=\"150\"></canvas>\n        <canvas id=\"waveform\" width=\"244\" height=\"46\"></canvas>\n        <button id=\"mic-btn\" class=\"on\" onclick=\"toggleMic()\">⏹ &nbsp;&nbsp; LISTENING — ACTIVE</button>\n      </div>\n    </div>\n    <div class=\"card card-scan\" style=\"padding:14px;flex:1;overflow:hidden;\">\n      <div class=\"sh\"><div class=\"sh-diamond\"></div><span class=\"sh-text\">SYSTEM STATUS</span><div class=\"sh-line\"></div></div>\n      <div class=\"tile\"><div class=\"tile-orb\">🧠</div><div class=\"tile-body\"><span class=\"tile-lbl\">MEMORY</span><span class=\"tile-val\" id=\"tv-mem\">—</span><div class=\"tile-bar\"><div class=\"tile-bar-fill\" id=\"tbf-mem\" style=\"width:0%\"></div></div></div></div>\n      <div class=\"tile\"><div class=\"tile-orb\">🔋</div><div class=\"tile-body\"><span class=\"tile-lbl\">BATTERY</span><span class=\"tile-val\" id=\"tv-bat\">—</span><div class=\"tile-bar\"><div class=\"tile-bar-fill\" id=\"tbf-bat\" style=\"width:0%\"></div></div></div></div>\n      <div class=\"tile\"><div class=\"tile-orb\">💾</div><div class=\"tile-body\"><span class=\"tile-lbl\">DISK</span><span class=\"tile-val\" id=\"tv-disk\">—</span><div class=\"tile-bar\"><div class=\"tile-bar-fill\" id=\"tbf-disk\" style=\"width:0%\"></div></div></div></div>\n      <div class=\"tile\"><div class=\"tile-orb\">🌐</div><div class=\"tile-body\"><span class=\"tile-lbl\">NETWORK</span><span class=\"tile-val\" id=\"tv-net\">—</span></div></div>\n      <div class=\"tile\" style=\"margin-bottom:0\"><div class=\"tile-orb\">🌡️</div><div class=\"tile-body\"><span class=\"tile-lbl\">GPU INFO</span><span class=\"tile-val\" id=\"tv-gpu2\">—</span></div></div>\n    </div>\n  </div>\n  <!-- CENTER -->\n  <div id=\"center\">\n    <div class=\"card card-corners\" style=\"flex:1;\">\n      <div class=\"cc tl\"></div><div class=\"cc tr\"></div><div class=\"cc bl\"></div><div class=\"cc br\"></div>\n      <div id=\"core-inner\">\n        <div id=\"NIK-hero\">\n          <div id=\"NIK-letters\">ELYSIAN</div>\n          <div class=\"hero-tagline\">VOICE ASSISTANT &nbsp;·&nbsp; AI CORE ACTIVE</div>\n          <div class=\"hero-underline\"></div>\n        </div>\n        <div class=\"ai-status-bar\">\n          <div class=\"ai-dot\"></div>\n          <span class=\"ai-status-txt\" id=\"ai-bar-txt\">NEURAL ENGINE RUNNING</span>\n          <span class=\"ai-mode-lbl\" id=\"mode-label\">TURBO</span>\n        </div>\n        <div id=\"plasma-wrap\"><canvas id=\"plasma\"></canvas></div>\n      </div>\n    </div>\n  </div>\n  <!-- RIGHT -->\n  <div id=\"right\">\n    <div class=\"card card-corners\" id=\"chat-card\" style=\"flex:1;display:flex;flex-direction:column;\">\n      <div class=\"cc tl\"></div><div class=\"cc tr\"></div><div class=\"cc bl\"></div><div class=\"cc br\"></div>\n      <div id=\"chat-inner\">\n        <div id=\"chat-top\">\n          <div class=\"sh-diamond\" style=\"margin-right:4px;width:7px;height:7px;background:var(--c1);transform:rotate(45deg);box-shadow:0 0 10px var(--c1);flex-shrink:0;\"></div>\n          <span class=\"chat-title\">NIK - ELYSIAN</span>\n          <div class=\"live-badge\"><div class=\"live-dot\"></div><span class=\"live-txt\">LIVE</span></div>\n        </div>\n        <div id=\"chat-scroll\"><div id=\"chat-empty\"><span class=\"empty-icon\">◈</span>No conversation yet.<br>Agent se baat karo —<br>messages yahan dikhenge.</div></div>\n        <div id=\"typing-row\"><div class=\"av NIK\">NIK</div><div class=\"typing-bbl\"><span></span><span></span><span></span></div></div>\n        <div id=\"quick-row\">\n          <button class=\"qb\" onclick=\"quickSend('Temps')\">TEMPS</button>\n          <button class=\"qb\" onclick=\"quickSend('Battery')\">BATTERY</button>\n          <button class=\"qb\" onclick=\"quickSend('Turbo Mode')\">TURBO</button>\n          <button class=\"qb\" onclick=\"quickSend('System Status')\">STATUS</button>\n        </div>\n        <div id=\"inp-row\">\n          <span class=\"inp-mic\" onclick=\"toggleMic()\">🎙</span>\n          <input id=\"chat-inp\" type=\"text\" placeholder=\"Message NIK…\" onkeydown=\"if(event.key==='Enter')sendMsg()\"/>\n          <button id=\"send-btn\" onclick=\"sendMsg()\">➤</button>\n        </div>\n      </div>\n    </div>\n  </div>\n</div>\n<!-- BOTTOM MODE BAR -->\n<div id=\"bottom-bar\">\n  <button class=\"mode-btn\" data-mode=\"Silent\"      onclick=\"setMode('Silent',this)\"><span class=\"pip\"></span>SILENT</button>\n  <button class=\"mode-btn\" data-mode=\"Balanced\"    onclick=\"setMode('Balanced',this)\"><span class=\"pip\"></span>BALANCED</button>\n  <button class=\"mode-btn\" data-mode=\"Performance\" onclick=\"setMode('Performance',this)\"><span class=\"pip\"></span>PERFORMANCE</button>\n  <button class=\"mode-btn active\" data-mode=\"Turbo\" onclick=\"setMode('Turbo',this)\"><span class=\"pip\"></span>TURBO</button>\n</div>\n</div>\n<script>\nfunction rrect(ctx,x,y,w,h,r){if(w<2*r)r=w/2;if(h<2*r)r=h/2;ctx.beginPath();ctx.moveTo(x+r,y);ctx.lineTo(x+w-r,y);ctx.quadraticCurveTo(x+w,y,x+w,y+r);ctx.lineTo(x+w,y+h-r);ctx.quadraticCurveTo(x+w,y+h,x+w-r,y+h);ctx.lineTo(x+r,y+h);ctx.quadraticCurveTo(x,y+h,x,y+h-r);ctx.lineTo(x,y+r);ctx.quadraticCurveTo(x,y,x+r,y);ctx.closePath();}\nfunction tickClock(){var d=new Date();document.getElementById('clock').textContent=('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2)+':'+('0'+d.getSeconds()).slice(-2);}\nsetInterval(tickClock,1000);tickClock();\nvar pyBridge=null;\nif(typeof QWebChannel!=='undefined'){\n  new QWebChannel(qt.webChannelTransport,function(ch){\n    pyBridge=ch.objects.bridge;\n    if(pyBridge.sysUpdate)  pyBridge.sysUpdate.connect(onSysUpdate);\n    if(pyBridge.chatUpdate) pyBridge.chatUpdate.connect(onChatUpdate);\n    if(pyBridge.micChanged) pyBridge.micChanged.connect(function(s){micOn=s;updateMicUI();});\n  });\n}\nfunction callPy(fn,a){try{if(pyBridge&&pyBridge[fn])pyBridge[fn](a);}catch(e){}}\nfunction winMin(){callPy('minimizeWindow');}function winMax(){callPy('maximizeWindow');}function winClose(){callPy('closeWindow');}\nfunction setNav(btn){document.querySelectorAll('.nav-btn').forEach(function(b){b.classList.remove('active');});btn.classList.add('active');}\n\n/* ════ THEMES — Doc5 CSS colors + Doc6 canvas RGB values ════ */\nvar THEMES={\n  Silent:{\n    statusTxt:'SILENT MODE — RESTING',\n    barTxt:'PROCESSING QUIETLY',\n    bgOrbs:[[100,60,200],[140,100,255],[80,40,180],[167,139,250]],\n    plasmaColor:[[167,139,250],[124,93,232],[196,181,253]],\n    orbColor:[[167,139,250],[196,181,253],[109,40,217]],\n    waveColor:[167,139,250]\n  },\n  Balanced:{\n    statusTxt:'BALANCED — OPTIMAL',\n    barTxt:'NEURAL ENGINE BALANCED',\n    bgOrbs:[[0,188,212],[0,136,168],[0,77,122],[38,223,199]],\n    plasmaColor:[[0,188,212],[0,136,168],[38,223,199]],\n    orbColor:[[0,188,212],[38,223,199],[0,136,168]],\n    waveColor:[0,188,212]\n  },\n  Performance:{\n    statusTxt:'PERFORMANCE — FULL THRUST',\n    barTxt:'ENGINES AT MAXIMUM THRUST',\n    bgOrbs:[[255,107,26],[255,140,0],[200,40,10],[255,215,0]],\n    plasmaColor:[[255,107,26],[255,140,0],[255,215,0]],\n    orbColor:[[255,107,26],[255,200,0],[200,40,10]],\n    waveColor:[255,107,26]\n  },\n  Turbo:{\n    statusTxt:'TURBO — MAXIMUM OVERDRIVE',\n    barTxt:'ALL SYSTEMS MAXIMUM — TURBO ENGAGED',\n    bgOrbs:[[255,0,80],[170,0,255],[255,0,170],[102,0,255]],\n    plasmaColor:[[255,0,80],[170,0,255],[255,0,170],[102,0,255]],\n    orbColor:[[255,0,80],[170,0,255],[255,0,170]],\n    waveColor:[255,0,80]\n },\n};\n\nvar currentMode='Turbo';\nvar currentTheme=THEMES['Turbo'];\n\nfunction flashOverlay(){\n  var o=document.getElementById('theme-overlay');\n  var wc=currentTheme.waveColor;\n  o.style.background='rgba('+wc[0]+','+wc[1]+','+wc[2]+',1)';\n  o.classList.add('flash');\n  setTimeout(function(){o.classList.remove('flash');},250);\n}\nfunction setMode(name,btn){\n  if(name===currentMode)return;\n  flashOverlay();currentMode=name;currentTheme=THEMES[name]||THEMES['Turbo'];\n  setTimeout(function(){\n    document.body.className='theme-'+name.toLowerCase();\n    document.getElementById('mode-label').textContent=name.toUpperCase();\n    document.getElementById('ai-status-txt').textContent=currentTheme.statusTxt;\n    document.getElementById('ai-bar-txt').textContent=currentTheme.barTxt;\n  },120);\n  document.querySelectorAll('#bottom-bar .mode-btn').forEach(function(b){b.classList.remove('active');});\n  btn.classList.add('active');callPy('setMode',name);\n}\n\nvar micOn=true;\nfunction toggleMic(){micOn=!micOn;callPy('toggleMic',micOn);_orbActive=micOn;_waveActive=micOn;updateMicUI();}\nfunction updateMicUI(){\n  var btn=document.getElementById('mic-btn');\n  if(micOn){btn.textContent='⏹   LISTENING — ACTIVE';btn.className='on';}\n  else{btn.textContent='🎙   ACTIVATE VOICE';btn.className='off';}\n}\nfunction onSysUpdate(js){\n  try{\n    var d=JSON.parse(js);\n    setBar('gpu',d.gpu_load);setBar('cpu',d.cpu);setBar('ram',d.ram);setBar('disk',d.disk);\n    document.getElementById('gpu-freq').textContent=Math.round(d.gpu_mhz)||300;\n    document.getElementById('gpu-temp').textContent=(d.gpu_temp||42)+'°C';\n    document.getElementById('gpu-load').textContent=(d.gpu_load||0)+'%';\n    document.getElementById('tv-mem').textContent=d.mem_used||'—';document.getElementById('tv-bat').textContent=d.bat||'—';\n    document.getElementById('tv-disk').textContent=d.disk+'%';document.getElementById('tv-net').textContent='↑ '+d.net_up+' · ↓ '+d.net_dn;\n    document.getElementById('tv-gpu2').textContent=(d.gpu_mhz||300)+' MHz · '+(d.gpu_temp||42)+'°C';\n    document.getElementById('tbf-bat').style.width=Math.min(100,parseFloat(d.bat)||100)+'%';\n    document.getElementById('tbf-mem').style.width=Math.min(100,d.ram||0)+'%';\n    document.getElementById('tbf-disk').style.width=Math.min(100,d.disk||0)+'%';\n  }catch(e){}\n}\nfunction setBar(id,val){\n  val=parseFloat(val)||0;document.getElementById('sn-'+id).textContent=val.toFixed(1);\n  var el=document.getElementById('sf-'+id);el.style.width=Math.min(100,val)+'%';\n  el.className='stat-fill'+(val>85?' hot':val>65?' warn':'');\n}\nvar replies=['Understood. Processing now.','Settings updated.','All thermal sensors nominal.','Mode engaged. Performance maximized.','Battery saver activated.','All subsystems clear.','Frequency optimised.','Neural engine running at peak capacity.'];\nvar rIdx=0;\nfunction ts(){var d=new Date();return('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2);}\nfunction addBubble(text,isUser,timestamp){\n  var empty=document.getElementById('chat-empty');if(empty)empty.remove();\n  var scroll=document.getElementById('chat-scroll');\n  var bw=document.createElement('div');bw.className='bw'+(isUser?' user':'');\n  var av=document.createElement('div');av.className='av '+(isUser?'user':'NIK');av.textContent=isUser?'U':'NIK';\n  var wrap=document.createElement('div');wrap.className='bbl-wrap';\n  var b=document.createElement('div');b.className='bbl '+(isUser?'user':'NIK');b.textContent=text;\n  var t2=document.createElement('div');t2.className='bbl-ts';t2.textContent=timestamp||ts();\n  wrap.appendChild(b);wrap.appendChild(t2);\n  if(isUser){bw.appendChild(wrap);bw.appendChild(av);}else{bw.appendChild(av);bw.appendChild(wrap);}\n  scroll.appendChild(bw);scroll.scrollTop=scroll.scrollHeight;\n}\nfunction showTyping(v){document.getElementById('typing-row').style.display=v?'flex':'none';if(v){var s=document.getElementById('chat-scroll');s.scrollTop=s.scrollHeight;}}\nfunction sendMsg(){\n  var inp=document.getElementById('chat-inp');var tx=inp.value.trim();if(!tx)return;\n  inp.value='';showTyping(true);\n  setTimeout(function(){showTyping(false);},1500);\n}\nfunction quickSend(q){document.getElementById('chat-inp').value=q;sendMsg();}\nvar _shownMessages = new Set();\n\nfunction onChatUpdate(js) {\n  try {\n    var d = JSON.parse(js);\n    if (d.type === 'clear') {\n      _shownMessages.clear();\n      document.getElementById('chat-scroll').innerHTML = '<div id=\"chat-empty\" style=\"margin:auto;text-align:center;color:var(--text3);font-family:var(--font-ui);font-size:13px;line-height:1.9\"><span style=\"font-size:28px;display:block;margin-bottom:8px;opacity:0.45\">◈</span>No conversation yet.<br>Agent se baat karo —<br>messages yahan dikhenge.</div>';\n    } else if (d.type === 'message') {\n      // Unique key — role + content + timestamp\n      var key = d.role + '|' + d.ts + '|' + d.content;\n      if (_shownMessages.has(key)) return;  // duplicate ignore\n      _shownMessages.add(key);\n      addBubble(d.content, d.role === 'user', d.ts);\n    }\n  } catch(e) {}\n}\n\n/* ═══ BACKGROUND ═══ */\n(function(){\n  var c=document.getElementById('bg-canvas'),ctx=c.getContext('2d');\n  var W,H,stars=[];\n  function resize(){W=c.width=window.innerWidth;H=c.height=window.innerHeight;}\n  window.addEventListener('resize',resize);resize();\n  var rng=(function(){var s=99;return function(){s=(s*1664525+1013904223)&0xffffffff;return(s>>>0)/4294967296;};})();\n  for(var i=0;i<140;i++)stars.push({x:rng(),y:rng(),z:rng()*1.6+0.3,ph:rng()*6.28,spd:rng()*1.3+0.3});\n  var orbs=[{x:0.10,y:0.22,r:460,ph:0,sp:0.0011},{x:0.90,y:0.78,r:400,ph:2.1,sp:0.0015},{x:0.50,y:0.04,r:300,ph:4.2,sp:0.0021},{x:0.18,y:0.90,r:260,ph:1.8,sp:0.0013}];\n  var t=0;\n  function frame(){\n    requestAnimationFrame(frame);t+=0.011;ctx.clearRect(0,0,W,H);\n    ctx.fillStyle='#000000';ctx.fillRect(0,0,W,H);\n    var oc=currentTheme.bgOrbs;\n    orbs.forEach(function(o,i){\n      var ph=o.ph+t*o.sp*80;var ox=(o.x+0.04*Math.sin(ph))*W,oy=(o.y+0.03*Math.cos(ph*1.4))*H;\n      var col=oc[i%oc.length];var g=ctx.createRadialGradient(ox,oy,0,ox,oy,o.r);\n      g.addColorStop(0,'rgba('+col[0]+','+col[1]+','+col[2]+',0.052)');\n      g.addColorStop(0.45,'rgba('+col[0]+','+col[1]+','+col[2]+',0.016)');\n      g.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=g;ctx.fillRect(0,0,W,H);\n    });\n    var wc=currentTheme.waveColor;\n    stars.forEach(function(s){\n      var tw=0.35+0.65*Math.abs(Math.sin(s.ph+t*s.spd));var al=tw*0.72*(s.z/1.6);\n      ctx.fillStyle='rgba('+wc[0]+','+wc[1]+','+wc[2]+','+al+')';\n      ctx.beginPath();ctx.arc(s.x*W,s.y*H,s.z*0.5,0,Math.PI*2);ctx.fill();\n    });\n    var vig=ctx.createRadialGradient(W/2,H/2,H*0.2,W/2,H/2,Math.max(W,H)*0.80);\n    vig.addColorStop(0,'rgba(0,0,0,0)');vig.addColorStop(0.55,'rgba(0,0,0,0.22)');vig.addColorStop(1,'rgba(0,0,0,0.84)');\n    ctx.fillStyle=vig;ctx.fillRect(0,0,W,H);\n  }\n  frame();\n})();\n\n/* ═══ LOGO ═══ */\n(function(){\n  var c=document.getElementById('logo-icon'),ctx=c.getContext('2d');var t=0,cx=16,cy=16;\n  function frame(){\n    requestAnimationFrame(frame);t+=0.04;ctx.clearRect(0,0,32,32);\n    var wc=currentTheme.orbColor[0];\n    var g=ctx.createRadialGradient(cx,cy,0,cx,cy,13);\n    g.addColorStop(0,'rgba('+wc[0]+','+wc[1]+','+wc[2]+',0.6)');g.addColorStop(1,'rgba(0,0,0,0)');\n    ctx.fillStyle=g;ctx.beginPath();ctx.arc(cx,cy,13,0,Math.PI*2);ctx.fill();\n    ctx.strokeStyle='rgba('+wc[0]+','+wc[1]+','+wc[2]+',0.9)';ctx.lineWidth=1.3;ctx.beginPath();ctx.arc(cx,cy,10,0,Math.PI*2);ctx.stroke();\n    for(var i=0;i<6;i++){var a=t+i*Math.PI/3;var p=0.5+0.5*Math.abs(Math.sin(t*2+i));ctx.strokeStyle='rgba('+wc[0]+','+wc[1]+','+wc[2]+','+(0.25+0.65*p)+')';ctx.lineWidth=0.9;ctx.beginPath();ctx.moveTo(cx+7*Math.cos(a),cy+7*Math.sin(a));ctx.lineTo(cx+10*Math.cos(a),cy+10*Math.sin(a));ctx.stroke();}\n    var cg=ctx.createRadialGradient(cx,cy,0,cx,cy,4);cg.addColorStop(0,'rgba(255,255,255,0.95)');cg.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=cg;ctx.beginPath();ctx.arc(cx,cy,4,0,Math.PI*2);ctx.fill();\n  }\n  frame();\n})();\n\n/* ═══ PLASMA — circle bada, S=0.96 ═══ */\n(function(){\n  var c=document.getElementById('plasma'),ctx=c.getContext('2d');\n  var t=0,W,H,cx,cy;\n  var arcs=[];for(var i=0;i<12;i++)arcs.push([Math.random()*Math.PI*2,Math.random()*Math.PI*2]);\n\n  function resize(){var wrap=document.getElementById('plasma-wrap');W=c.width=wrap.clientWidth||600;H=c.height=wrap.clientHeight||360;cx=W/2;cy=H/2;}\n  window.addEventListener('resize',function(){setTimeout(resize,50);});setTimeout(resize,150);resize();\n\n  function rgba(col,a){return'rgba('+col[0]+','+col[1]+','+col[2]+','+a+')';}\n\n  function drawFrame(){\n    requestAnimationFrame(drawFrame);t+=0.018;ctx.clearRect(0,0,W,H);\n    /* S = 0.96 — thoda bada pehle wale 0.88 se */\n    var S=Math.min(W,H)*0.96;\n    var pal=currentTheme.plasmaColor;\n\n    /* halos */\n    [[0.68,0.40],[0.48,0.72],[0.30,1.0]].forEach(function(rf){\n      var r=rf[0]*S;var g=ctx.createRadialGradient(cx,cy,0,cx,cy,r);\n      g.addColorStop(0,rgba(pal[0],0.22*rf[1]));g.addColorStop(0.5,rgba(pal[1],0.09*rf[1]));g.addColorStop(1,'rgba(0,0,0,0)');\n      ctx.fillStyle=g;ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.fill();\n    });\n    /* rings */\n    [0.12,0.18,0.25,0.32,0.41].forEach(function(rf,ri){\n      var R=rf*S;var dir=(ri%2===0)?1:-1;var aoff=t*(0.28+ri*0.09)*dir;\n      var segs=6+ri*2,sa=265/segs,gap=10;var pw=Math.max(0.6,3.0-ri*0.40);\n      var pulse=0.5+0.5*Math.sin(t*(0.65+ri*0.16)+ri);var al=(55+130*pulse)/255;\n      ctx.strokeStyle=rgba(pal[ri%3],al);ctx.lineWidth=pw;ctx.lineCap='round';\n      for(var s=0;s<segs;s++){var sd=aoff*57.3+s*(sa+gap);var span=sa*(0.55+0.45*Math.abs(Math.sin(t*0.38+s*0.85+ri)));ctx.beginPath();ctx.arc(cx,cy,R,sd*Math.PI/180,(sd+span)*Math.PI/180);ctx.stroke();}\n    });\n    /* bezier web */\n    var arcR=0.30*S;\n    arcs.forEach(function(ap,i){\n      var rot=t*0.11*(i%2===0?1:-1);var pulse=0.35+0.65*Math.abs(Math.sin(t*0.22+i*0.52));var al=pulse*0.28;\n      var x1=cx+arcR*Math.cos(ap[0]+rot),y1=cy+arcR*Math.sin(ap[0]+rot);var x2=cx+arcR*Math.cos(ap[1]+rot),y2=cy+arcR*Math.sin(ap[1]+rot);\n      var mx=cx+arcR*0.38*Math.cos((ap[0]+ap[1])*0.5+rot+0.9);var my=cy+arcR*0.38*Math.sin((ap[0]+ap[1])*0.5+rot+0.9);\n      ctx.strokeStyle=rgba(pal[i%3],al);ctx.lineWidth=0.9;ctx.beginPath();ctx.moveTo(x1,y1);ctx.quadraticCurveTo(mx,my,x2,y2);ctx.stroke();\n    });\n    /* spokes */\n    var is=0.125*S;\n    for(var i=0;i<28;i++){\n      var ang=(i*(360/28)+t*14)*Math.PI/180;var pulse=Math.abs(Math.sin(t*1.4+i*0.38));\n      var outer=is+pulse*0.13*S;var al=(80+175*pulse)/255;\n      ctx.strokeStyle=rgba(pal[i%3],al);ctx.lineWidth=0.8;ctx.lineCap='round';\n      ctx.beginPath();ctx.moveTo(cx+is*Math.cos(ang),cy+is*Math.sin(ang));ctx.lineTo(cx+outer*Math.cos(ang),cy+outer*Math.sin(ang));ctx.stroke();\n    }\n    /* triangles */\n    var tr=0.085*S,trot=t*22;\n    [[1.0,1.0,false],[0.72,0.70,true],[0.50,0.48,false]].forEach(function(ts2){\n      var sc=ts2[0],am=ts2[1],rev=ts2[2];var pts=[];\n      for(var vi=0;vi<3;vi++){var va=((vi*120+trot*(rev?-1:1))-90)*Math.PI/180;pts.push([cx+tr*sc*Math.cos(va),cy+tr*sc*Math.sin(va)]);}\n      var pulse=0.5+0.5*Math.sin(t*1.8+sc*3);var al=pulse*190*am/255;\n      ctx.strokeStyle=rgba(pal[0],al);ctx.lineWidth=1.5*sc;ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);pts.forEach(function(pt){ctx.lineTo(pt[0],pt[1]);});ctx.closePath();ctx.stroke();\n    });\n    /* core */\n    var cr=0.125*S;\n    var cg=ctx.createRadialGradient(cx,cy,0,cx,cy,cr*1.5);\n    cg.addColorStop(0,rgba(pal[0],0.65));cg.addColorStop(0.6,rgba(pal[1],0.30));cg.addColorStop(1,'rgba(0,0,0,0)');\n    ctx.fillStyle=cg;ctx.beginPath();ctx.arc(cx,cy,cr*1.5,0,Math.PI*2);ctx.fill();\n    ctx.beginPath();ctx.arc(cx,cy,cr,0,Math.PI*2);ctx.strokeStyle=rgba(pal[0],1.0);ctx.lineWidth=2.5;ctx.stroke();\n    ctx.beginPath();ctx.arc(cx,cy,cr,0,Math.PI*2);ctx.strokeStyle=rgba(pal[2],0.6);ctx.lineWidth=1.1;ctx.stroke();\n    var ir=0.026*S;ctx.beginPath();ctx.arc(cx,cy,ir,0,Math.PI*2);ctx.strokeStyle=rgba(pal[2],0.95);ctx.lineWidth=2.0;ctx.stroke();\n    /* center */\n    var cp=0.5+0.5*Math.sin(t*2.6);\n    [0.052*S,0.030*S,0.014*S,4].forEach(function(r,ri){\n      var a=[0.22,0.45,0.78,1.0][ri]*(0.8+0.2*cp);var cg2=ctx.createRadialGradient(cx,cy,0,cx,cy,r);\n      cg2.addColorStop(0,'rgba(255,255,255,'+(a*(ri===3?1:0.9))+')');cg2.addColorStop(0.4,rgba(pal[0],a*0.65));cg2.addColorStop(1,'rgba(0,0,0,0)');\n      ctx.fillStyle=cg2;ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.fill();\n    });\n    /* crosshairs */\n    var cl=0.40*S;ctx.strokeStyle=rgba(pal[0],0.09);ctx.lineWidth=0.5;\n    ctx.beginPath();ctx.moveTo(cx-cl,cy);ctx.lineTo(cx-cr-6,cy);ctx.stroke();ctx.beginPath();ctx.moveTo(cx+cr+6,cy);ctx.lineTo(cx+cl,cy);ctx.stroke();\n    ctx.beginPath();ctx.moveTo(cx,cy-cl);ctx.lineTo(cx,cy-cr-6);ctx.stroke();ctx.beginPath();ctx.moveTo(cx,cy+cr+6);ctx.lineTo(cx,cy+cl);ctx.stroke();\n  }\n  drawFrame();\n})();\n\n/* ═══ VOICE ORB ═══ */\nvar _orbActive=true;\n(function(){\n  var c=document.getElementById('orb-canvas'),ctx=c.getContext('2d');\n  var W=150,H=150,cx=75,cy=75,t=0;var n=32,hh=new Array(n).fill(0),tg=new Array(n).fill(0),rot=0;\n  function rgba(r,g,b,a){return'rgba('+r+','+g+','+b+','+a+')';}\n  function frame(){\n    requestAnimationFrame(frame);t+=0.022;ctx.clearRect(0,0,W,H);\n    var E=_orbActive?1.0:0.20;var oc=currentTheme.orbColor;var c1=oc[0],c2=oc[1];\n    [[46,0.42],[34,0.72],[22,1.0]].forEach(function(rf){var r=rf[0]*E;var g=ctx.createRadialGradient(cx,cy,0,cx,cy,r);g.addColorStop(0,rgba(c1[0],c1[1],c1[2],0.22*rf[1]*E));g.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=g;ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.fill();});\n    var rp=0.5+0.5*Math.sin(t*1.1);ctx.beginPath();ctx.arc(cx,cy,46,0,Math.PI*2);ctx.strokeStyle=rgba(c1[0],c1[1],c1[2],0.75*E*rp);ctx.lineWidth=1.8;ctx.stroke();\n    rot=(rot+(_orbActive?0.6:0.05))%360;\n    for(var i=0;i<n;i++){\n      if(_orbActive){tg[i]=Math.min(1,0.08+0.74*Math.abs(Math.sin(t*(0.17+0.14*i/n)+i*0.42))+0.06*(Math.random()-0.5));hh[i]+=(tg[i]-hh[i])*0.20;}else{hh[i]*=0.88;}\n      var ang=(rot+i*360/n)*Math.PI/180;var bl=Math.max(1.5,hh[i]*18);var x1=cx+48*Math.cos(ang),y1=cy+48*Math.sin(ang);var x2=cx+(48+bl)*Math.cos(ang),y2=cy+(48+bl)*Math.sin(ang);\n      var al=_orbActive?(70+185*hh[i]):(8+20*hh[i]);var cc=i/n<0.5?c1:c2;\n      ctx.strokeStyle=rgba(cc[0],cc[1],cc[2],al/255);ctx.lineWidth=1.4+hh[i]*1.6;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();\n    }\n    [11,6,3].forEach(function(r,ri){var cp=0.5+0.5*Math.sin(t*2.2+ri);ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.strokeStyle=rgba(c2[0],c2[1],c2[2],[0.55,0.75,0.92][ri]*E*cp);ctx.lineWidth=[1.6,1.2,0.9][ri];ctx.stroke();});\n    var cp2=0.5+0.5*Math.sin(t*2.9);\n    [18,10,4.5,2].forEach(function(r,ri){var a=[0.20,0.44,0.76,1.0][ri]*E*(0.8+0.2*cp2);var cg2=ctx.createRadialGradient(cx,cy,0,cx,cy,r);cg2.addColorStop(0,'rgba(255,255,255,'+a+')');cg2.addColorStop(0.4,rgba(c1[0],c1[1],c1[2],a*0.65));cg2.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=cg2;ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.fill();});\n    ctx.font=_orbActive?'bold 7px Share Tech Mono,monospace':'7px Share Tech Mono,monospace';ctx.textAlign='center';\n    if(_orbActive){var lp=0.6+0.4*Math.sin(t*3.2);ctx.fillStyle=rgba(c1[0],c1[1],c1[2],0.70+0.30*lp);ctx.fillText('● LIVE',cx,cy+64);}\n    else{ctx.fillStyle=rgba(c1[0],c1[1],c1[2],0.4);ctx.fillText('○ MUTED',cx,cy+64);}\n  }\n  frame();\n})();\n\n/* ═══ WAVEFORM ═══ */\nvar _waveActive=true;\n(function(){\n  var c=document.getElementById('waveform'),ctx=c.getContext('2d');var t=0,n=28,hh=new Array(n).fill(0),tg=new Array(n).fill(0),rot=0;\n  function frame(){\n    requestAnimationFrame(frame);t+=0.022;rot=(rot+(_waveActive?0.85:0.04))%360;\n    var W=c.width=c.offsetWidth||244,H=46,mid=H/2;ctx.clearRect(0,0,W,H);\n    var wc=currentTheme.waveColor;var gap=2,bw=Math.max(3,Math.floor((W-20-(n-1)*gap)/n));var total=n*bw+(n-1)*gap,sx=10+Math.floor((W-20-total)/2);\n    for(var i=0;i<n;i++){\n      if(_waveActive){tg[i]=Math.min(1,0.08+0.74*Math.abs(Math.sin(t*(0.18+0.11*i/n)+i*0.36))+0.05*(Math.random()-0.5));hh[i]+=(tg[i]-hh[i])*0.20;}else{hh[i]*=0.88;}\n      var half=Math.max(2,hh[i]*(mid-3));var bx=sx+i*(bw+gap);var al=_waveActive?(75+175*hh[i]):(12+30*hh[i]);\n      var gt=ctx.createLinearGradient(0,mid-half,0,mid);gt.addColorStop(0,'rgba('+wc[0]+','+wc[1]+','+wc[2]+','+al/255+')');gt.addColorStop(1,'rgba('+wc[0]+','+wc[1]+','+wc[2]+',0.04)');ctx.fillStyle=gt;rrect(ctx,bx,mid-half,bw,half,2);ctx.fill();\n      var gb=ctx.createLinearGradient(0,mid,0,mid+half);gb.addColorStop(0,'rgba('+wc[0]+','+wc[1]+','+wc[2]+',0.04)');gb.addColorStop(1,'rgba('+wc[0]+','+wc[1]+','+wc[2]+','+al/255+')');ctx.fillStyle=gb;rrect(ctx,bx,mid,bw,half,2);ctx.fill();\n    }\n    var gx=ctx.createLinearGradient(10,mid,W-10,mid);gx.addColorStop(0,'rgba('+wc[0]+','+wc[1]+','+wc[2]+',0)');gx.addColorStop(0.2,'rgba('+wc[0]+','+wc[1]+','+wc[2]+',0.28)');gx.addColorStop(0.5,'rgba('+wc[0]+','+wc[1]+','+wc[2]+',0.48)');gx.addColorStop(0.8,'rgba('+wc[0]+','+wc[1]+','+wc[2]+',0.28)');gx.addColorStop(1,'rgba('+wc[0]+','+wc[1]+','+wc[2]+',0)');ctx.fillStyle=gx;ctx.fillRect(10,mid-0.8,W-20,1.6);\n  }\n  frame();\n})();\n</script>\n</body>\n</html>\n"
class NIKWindow(QMainWindow):
    def __init__(self, bridge: Bridge):
        super().__init__(); self._bridge = bridge; self.setWindowTitle("NIK — ELYSIAN Assistant ✦ 4-Mode Theme Edition"); self.resize(1200, 800); self.setMinimumSize(800, 600); self._view = QWebEngineView()
        
        settings = self._view.settings(); settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True); settings.setAttribute(QWebEngineSettings.ScrollAnimatorEnabled, True); self._channel = QWebChannel()
        
        self._channel.registerObject("bridge", bridge); self._view.page().setWebChannel(self._channel); self.setCentralWidget(self._view)
        
        self._load_html()
        
        bridge.sysUpdate.connect(self._on_sys_update); bridge.chatUpdate.connect(self._on_chat_update); bridge.lockSignal.connect(self.handle_lock_signal); self._sys_timer = QTimer()
        
        self._sys_timer.timeout.connect(bridge.push_sys)
        
        self._sys_timer.start(2000); self._mem_timer = QTimer(); self._mem_timer.timeout.connect(bridge.poll_memory); self._mem_timer.start(1500)
        
        bridge.minimizeWindow = self._minimize
        
        bridge.maximizeWindow = self._maximize
        
        bridge.closeWindow = self._close_app
        
        self.setWindowOpacity(0.0); self._fade_val = 0.0
        
        self._ft = QTimer()
        
        self._ft.timeout.connect(self._fade_in); self._ft.start(30)
    
    def _load_html(self):
        from PyQt5.QtCore import QFile, QIODevice; f = QFile(":/qtwebchannel/qwebchannel.js"); js_src = ""
        if f.open(QIODevice.ReadOnly):
            js_src = bytes(f.readAll()).decode()
            f.close()
        lock_css = """
#lock-screen {
  display: none;
  position: fixed;
  inset: 0;
  z-index: 99999;
  background: rgba(0, 3, 10, 0.97);
  backdrop-filter: blur(15px);
  -webkit-backdrop-filter: blur(15px);
  align-items: center;
  justify-content: center;
  font-family: 'Orbitron', sans-serif;
  transition: opacity 0.4s ease;
  opacity: 0;
}
@keyframes lock-pulse {
  0%, 100% { transform: scale(1); filter: drop-shadow(0 0 10px var(--c-glow)); }
  50% { transform: scale(1.08); filter: drop-shadow(0 0 30px var(--c1)); }
}
@keyframes lock-appear {
  to { transform: scale(1); opacity: 1; }
}
"""
        lock_html = """
<div id="lock-screen">
  <div style="text-align: center; transform: scale(0.9); animation: lock-appear 0.5s cubic-bezier(0.18, 0.89, 0.32, 1.28) forwards;">
    <div style="font-size: 72px; margin-bottom: 20px; text-shadow: 0 0 30px var(--c-glow); animation: lock-pulse 2s infinite ease-in-out;">🔒</div>
    <div style="font-size: 24px; font-weight: 900; letter-spacing: 8px; color: var(--c1); margin-bottom: 10px;">SYSTEM SECURED</div>
    <div style="font-family: 'Share Tech Mono', monospace; font-size: 10px; color: var(--text2); letter-spacing: 4px;">SPEAK "UNLOCK NIK" TO ACCESS</div>
  </div>
</div>
"""
        lock_js = """
function showLockScreen() {
  var ls = document.getElementById('lock-screen');
  ls.style.display = 'flex';
  setTimeout(function() {
    ls.style.opacity = '1';
  }, 10);
}
function hideLockScreen() {
  var ls = document.getElementById('lock-screen');
  ls.style.opacity = '0';
  setTimeout(function() {
    ls.style.display = 'none';
  }, 400);
}
"""
        html = NIK_HTML.replace("</head>", f"<script>{js_src}</script><style>{lock_css}</style></head>")
        html = html.replace("</body>", f"{lock_html}<script>{lock_js}</script></body>")
        
        self._view.setHtml(html, QUrl("qrc:/"))
    
    def _on_sys_update(self, json_str):
        escaped = json_str.replace("\\", "\\\\").replace("'", "\\'"); self._view.page().runJavaScript(f"if(typeof onSysUpdate==='function') onSysUpdate('{escaped}');")
    
    def _on_chat_update(self, json_str):
        escaped = json_str.replace("\\", "\\\\").replace("'", "\\'"); self._view.page().runJavaScript(f"if(typeof onChatUpdate==='function') onChatUpdate('{escaped}');")
    
    def handle_lock_signal(self, locked: bool):
        if locked:
            self.showFullScreen()
            self.raise_()
            self.activateWindow()
            self._view.page().runJavaScript("if(typeof showLockScreen==='function') showLockScreen();")
        else:
            self.setWindowState(Qt.WindowNoState)
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self._view.page().runJavaScript("if(typeof hideLockScreen==='function') hideLockScreen();")
    
    def _fade_in(self):
        self._fade_val = min(1.0, (self._fade_val) + 0.06); self.setWindowOpacity(self._fade_val)
        if self._fade_val >= 1.0:
            self._ft.stop()
            return
    
    def _minimize(self):
        self.showMinimized()
    
    def _maximize(self):
        if self.isMaximized():
            self.showNormal()
            return
        self.showMaximized()
    
    def _close_app(self):
        QApplication.instance().quit()
    
    def _start_agent_background(self):
        try:
            from agent import entrypoint as _entrypoint
            from livekit.agents.cli import run_app
            from livekit.agents import WorkerOptions
            def run_agent():
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    time.sleep(2)
                    run_app(WorkerOptions(entrypoint_fnc=_entrypoint))
                    return
                except:
                    pass
            thr = threading.Thread(target=run_agent, daemon=True)
            thr.name = "NIK-Agent"
            thr.start()
            print(f"🔧 Agent thread: {thr.name}")
        except:
            pass

def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, False); QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True); app = QApplication(sys.argv); app.setApplicationName("NIK"); app.setStyle("Fusion"); app.setQuitOnLastWindowClosed(False); print("🚀 NIK Starting...")
    
    QMessageBox.information(None, "NIK", "🚀 NIK ELYSIAN Assistant Starting...\n\nMake sure you are connected to the Internet!")
    if not wait_for_internet():
        QMessageBox.critical(None, "Error", "Internet required. Exiting.")
        return 1
    
    try:
        init_firebase_from_embedded()
    except Exception as e:
        QMessageBox.critical(None, "Firebase Error", f"Firebase init failed:\n{e}")
        return 1
    
    activation_success, status = safe_activation_gate()
    if activation_success and status == "failed":
        QMessageBox.critical(None, "Activation Failed", "Activation failed. Exiting.")
        return 1
    user_name = ensure_user_name(); print(f"✅ Welcome, {user_name}!")
    
    SysInfo.start()
    
    bridge = Bridge(); win = NIKWindow(bridge)
    
    win._start_agent_background(); win.show(); app.setQuitOnLastWindowClosed(True)
    
    result = app.exec_(); print(f"🔚 Exited: {result}")
    return result

if __name__ == "__main__":
    os._exit(main())
