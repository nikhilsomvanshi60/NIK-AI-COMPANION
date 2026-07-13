"""
notification_monitor.py
========================
Sirf Windows notifications detect karta hai.
Session aur triggering main_mj.py mein hogi — reminder ki tarah.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def get_active_notifications() -> list:
    """
    Windows Action Center se active toast notifications read karta hai.
    Returns: list of dicts — {app, title, body, time, id}
    Yeh blocking function hai — asyncio.to_thread() se call karo.
    """
    notifications = []

    # ── Method 1: winrt (Windows Runtime — sabse reliable) ──────────────────
    try:
        from winrt.windows.ui.notifications.management import (
            UserNotificationListener,
        )
        from winrt.windows.ui.notifications import (
            NotificationKinds,
            KnownNotificationBindings,
        )

        listener = UserNotificationListener.current
        notifs = listener.get_notifications_async(
            NotificationKinds.TOAST
        ).get()

        for n in notifs:
            try:
                binding = n.notification.visual.get_binding(
                    KnownNotificationBindings.get_toast_generic()
                )
                if binding:
                    elements = binding.get_text_elements()
                    texts    = [str(e.text) for e in elements if e.text]
                    app_info = n.app_info
                    app_name = (
                        app_info.display_info.display_name
                        if app_info else "Unknown"
                    )
                    notifications.append({
                        "app":   app_name,
                        "title": texts[0] if texts else "",
                        "body":  texts[1] if len(texts) > 1 else "",
                        "time":  datetime.now().strftime("%I:%M %p"),
                        "id":    str(n.id),
                    })
            except Exception:
                continue

        return notifications

    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"winrt failed: {e}")

    # ── Method 2: pywinauto fallback ─────────────────────────────────────────
    try:
        from pywinauto import Desktop

        desktop = Desktop(backend="uia")
        tray    = desktop.window(
            class_name="Windows.UI.Core.CoreWindow",
            title_re=".*Notification.*"
        )
        if tray.exists():
            for item in tray.descendants(control_type="ListItem"):
                try:
                    texts = [
                        t.window_text()
                        for t in item.descendants()
                        if t.window_text().strip()
                    ]
                    if texts:
                        notifications.append({
                            "app":   texts[0] if len(texts) > 0 else "System",
                            "title": texts[1] if len(texts) > 1 else texts[0],
                            "body":  texts[2] if len(texts) > 2 else "",
                            "time":  datetime.now().strftime("%I:%M %p"),
                        })
                except Exception:
                    continue

    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"pywinauto failed: {e}")

    return notifications
