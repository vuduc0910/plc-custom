from __future__ import annotations

from typing import TYPE_CHECKING

from n1700_bridge.ui.resources.strings_vi import STRINGS

if TYPE_CHECKING:
    from n1700_bridge.ui.main_window import MainWindow


def poll_plc(w: MainWindow) -> None:
    if not hasattr(w, "_plc"):
        return
    try:
        connected = w._plc.is_connected()
    except Exception:
        connected = False
    if connected:
        w.plc_status.setText(f"● {STRINGS['status_plc_connected']}")
        w.plc_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
    else:
        w.plc_status.setText(f"● {STRINGS['status_plc_disconnected']}")
        w.plc_status.setStyleSheet("color: #F44336; font-weight: bold;")


def poll_n1700(w: MainWindow) -> None:
    if not hasattr(w, "_n1700") or w._n1700 is None:
        return
    try:
        available = w._n1700.is_window_available()
    except Exception:
        available = False
    if available:
        w.n1700_status.setText(f"● {STRINGS['status_n1700_available']}")
        w.n1700_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
    else:
        w.n1700_status.setText(f"● {STRINGS['status_n1700_unavailable']}")
        w.n1700_status.setStyleSheet("color: #F44336; font-weight: bold;")


def poll_excel(w: MainWindow) -> None:
    if not hasattr(w, "_excel_path") or w._excel_path is None:
        return
    if w._excel_path.exists():
        w.excel_status.setText(f"● {STRINGS['status_excel_open']}")
        w.excel_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
    else:
        w.excel_status.setText(f"● {STRINGS['status_excel_closed']}")
        w.excel_status.setStyleSheet("color: #F44336; font-weight: bold;")


def translate_error(error_msg: str) -> str:
    msg_lower = error_msg.lower()
    if "dll not connected" in msg_lower:
        return STRINGS["error_dll_disconnected"]
    if "timeout" in msg_lower and "n1700" in msg_lower:
        return STRINGS["error_dll_timeout"]
    if "polldata" in msg_lower or "poll channel" in msg_lower:
        return STRINGS["error_dll_poll"]
    if "window" in msg_lower:
        return STRINGS["error_n1700_not_found"]
    if "n1700" in msg_lower:
        return STRINGS["error_dll_general"]
    if "excel" in msg_lower:
        return STRINGS["error_excel_closed"]
    return error_msg
