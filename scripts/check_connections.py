"""Connection diagnostic tool — run before launching n1700_bridge.

Usage:
    python scripts/check_connections.py

Checks all configured connections and reports pass/fail for each.
"""

import json
import struct
import sys
from pathlib import Path

# ── Helpers ──────────────────────────────────────────────────────────

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✔ PASS{RESET}  {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✘ FAIL{RESET}  {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠ SKIP{RESET}  {msg}")


def info(msg: str) -> None:
    print(f"  {CYAN}ℹ INFO{RESET}  {msg}")


def section(title: str) -> None:
    print(f"\n{BOLD}{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}{RESET}")


# ── Checks ───────────────────────────────────────────────────────────

def check_python() -> bool:
    section("1. Python Environment")
    v = sys.version_info
    bits = struct.calcsize("P") * 8
    info(f"Python {v.major}.{v.minor}.{v.micro} ({bits}-bit)")

    if v.major != 3 or v.minor not in (10, 11, 12):
        fail(f"Python 3.10/3.11/3.12 required, got {v.major}.{v.minor}")
        return False

    if bits != 64:
        fail(f"64-bit Python required, got {bits}-bit (PySide6 won't install)")
        return False

    ok(f"Python {v.major}.{v.minor} {bits}-bit")
    return True


def check_config() -> dict | None:
    section("2. Config File")
    config_path = Path("config/config.json")
    if not config_path.exists():
        fail(f"{config_path} not found")
        return None

    try:
        config = json.loads(config_path.read_text())
        ok(f"Loaded {config_path}")
        return config
    except json.JSONDecodeError as e:
        fail(f"Invalid JSON in {config_path}: {e}")
        return None


def check_n1700_dll(config: dict) -> bool:
    section("3. N1700 — DLL Mode")
    n1700 = config.get("n1700", {})

    if not n1700.get("use_dll", False):
        warn("use_dll=false → DLL mode disabled, skipping")
        return True

    dll_path_str = n1700.get("dll_path", "N1700.dll")
    dll_path = Path(dll_path_str)
    if not dll_path.is_absolute():
        dll_path = Path.cwd() / dll_path
    info(f"DLL path: {dll_path}")

    if not dll_path.exists():
        fail(f"DLL not found at {dll_path}")
        print(f"       → Sửa dll_path trong config/config.json trỏ đúng tới N1700_64.dll")
        return False

    ok(f"DLL file exists ({dll_path.stat().st_size / 1024 / 1024:.1f} MB)")

    # Try loading DLL (Windows only)
    if sys.platform.startswith("win"):
        try:
            import ctypes
            dll = ctypes.WinDLL(str(dll_path))
            # Check required functions exist
            for func_name in ["N1700InitializeLibrary", "N1700FreeLibrary", "N1700PollData"]:
                if not hasattr(dll, func_name):
                    fail(f"DLL missing function: {func_name}")
                    return False
            ok("DLL loaded, all required functions found")

            # Try initialize (will fail if no hardware, but tests DLL itself)
            num_modules = ctypes.c_uint32(0)
            num_channels = ctypes.c_uint32(0)
            try:
                dll.N1700InitializeLibrary.argtypes = [
                    ctypes.c_bool,
                    ctypes.POINTER(ctypes.c_uint32),
                    ctypes.POINTER(ctypes.c_uint32),
                    ctypes.c_int32,
                ]
                dll.N1700InitializeLibrary.restype = ctypes.c_int
                rc = dll.N1700InitializeLibrary(
                    False, ctypes.byref(num_modules), ctypes.byref(num_channels), 0
                )
                if rc == 0:
                    ok(f"N1700 hardware detected: {num_modules.value} modules, {num_channels.value} channels")
                    dll.N1700FreeLibrary()
                else:
                    codes = {
                        -1: "FAILURE", -2: "TIMEOUT", -3: "INVALID_DEVNO",
                        -4: "NO_MODULES", -5: "FILENOTEXISTS",
                    }
                    msg = codes.get(rc, f"UNKNOWN({rc})")
                    fail(f"N1700InitializeLibrary returned: {msg} (rc={rc})")
                    if rc == -4:
                        print("       → Thiết bị N1700 chưa cắm USB hoặc chưa cài FTDI driver")
                    elif rc == -1:
                        print("       → Tắt MillimarN1700.exe nếu đang mở (tranh USB)")
                    return False
            except Exception as e:
                fail(f"N1700InitializeLibrary call error: {e}")
                return False
        except OSError as e:
            fail(f"Cannot load DLL: {e}")
            print("       → Có thể thiếu FTDI driver hoặc DLL sai architecture (32/64-bit)")
            return False
    else:
        warn("Not Windows — cannot test DLL loading")

    return True


def check_n1700_pywinauto(config: dict) -> bool:
    section("4. N1700 — Pywinauto Mode")
    n1700 = config.get("n1700", {})

    if n1700.get("use_dll", False):
        warn("use_dll=true → Pywinauto mode disabled, skipping")
        return True

    if n1700.get("use_fake", True):
        warn("use_fake=true → Using fake N1700, skipping")
        return True

    if not sys.platform.startswith("win"):
        warn("Not Windows — cannot test pywinauto")
        return True

    title_re = n1700.get("window_title_regex", "N1700.*")
    info(f"Window title regex: {title_re}")

    try:
        from pywinauto.application import Application
        ok("pywinauto imported successfully")
    except ImportError:
        fail("pywinauto not installed (pip install pywinauto)")
        return False

    # Try to find the window
    for backend in ("uia", "win32"):
        try:
            app = Application(backend=backend)
            app.connect(title_re=title_re, timeout=3)
            window = app.window(title_re=title_re)
            if window.exists(timeout=1):
                ok(f"N1700 window found: \"{window.window_text()}\" (backend={backend})")
                return True
        except Exception:
            continue

    fail(f"N1700 window not found (regex=\"{title_re}\")")
    print("       → Mở MillimarN1700.exe trước khi chạy bridge")
    print(f"       → Kiểm tra title cửa sổ có match \"{title_re}\" không")
    return False


def check_plc(config: dict) -> bool:
    section("5. PLC Connection")
    plc = config.get("plc", {})

    if plc.get("use_fake", True):
        warn("use_fake=true → Using fake PLC, skipping")
        return True

    host = plc.get("host", "192.168.1.10")
    port = plc.get("port", 5007)
    info(f"PLC target: {host}:{port}")

    # Ping test
    import subprocess
    try:
        result = subprocess.run(
            ["ping", "-n" if sys.platform.startswith("win") else "-c", "1",
             "-w" if sys.platform.startswith("win") else "-W", "2000" if sys.platform.startswith("win") else "2",
             host],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            ok(f"Ping {host} reachable")
        else:
            fail(f"Ping {host} unreachable — check network/cable")
            return False
    except Exception as e:
        warn(f"Ping failed: {e}")

    # TCP connect test
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((host, port))
        sock.close()
        ok(f"TCP port {host}:{port} open")
    except Exception as e:
        fail(f"TCP port {host}:{port} closed — {e}")
        print("       → PLC chưa bật hoặc port SLMP chưa cấu hình")
        return False

    # SLMP connect test (rk-mcprotocol for FX5U)
    try:
        import rk_mcprotocol
        sock = rk_mcprotocol.open_socket(host, port)
        ok("rk-mcprotocol connected successfully (FX5U)")

        # Test 1: Read trigger bit (M100)
        trigger = plc.get("trigger_bit", "M100")
        try:
            device = trigger[0].lower()
            number = int(trigger[1:])
            values = rk_mcprotocol.read_bit(sock, f"{device}{number}", 1)
            ok(f"Read bit  {trigger} = {values[0]}")
        except Exception as e:
            warn(f"Could not read bit {trigger}: {e}")

        # Test 2: Read D1000 (word)
        try:
            values = rk_mcprotocol.read_sign_word(sock, "d1000", 1, True)
            ok(f"Read word D1000 = {values[0]}")
        except Exception as e:
            warn(f"Could not read word D1000: {e}")

        # Test 3: Read D100 (first port register)
        try:
            values = rk_mcprotocol.read_sign_word(sock, "d100", 1, True)
            ok(f"Read word D100  = {values[0]}")
        except Exception as e:
            warn(f"Could not read word D100: {e}")

        # Test 4: Read M200 (first judgment bit)
        try:
            values = rk_mcprotocol.read_bit(sock, "m200", 1)
            ok(f"Read bit  M200 = {values[0]}")
        except Exception as e:
            warn(f"Could not read bit M200: {e}")

        sock.close()
        return True
    except ImportError:
        fail("rk-mcprotocol not installed (pip install rk-mcprotocol)")
        return False
    except Exception as e:
        fail(f"SLMP connect failed: {e}")
        return False


def check_excel(config: dict) -> bool:
    section("6. Excel Input File")
    n1700 = config.get("n1700", {})

    if n1700.get("use_dll", False):
        warn("use_dll=true → Excel not used in DLL mode, skipping")
        return True

    excel = config.get("excel_input", {})
    excel_path = Path(excel.get("path", "mocks/sample_n1700_output.xlsx"))
    info(f"Excel path: {excel_path}")

    if not excel_path.exists():
        fail(f"Excel file not found: {excel_path}")
        print("       → Đảm bảo MillimarN1700.exe đã export file tới đường dẫn này")
        return False

    ok(f"Excel file exists ({excel_path.stat().st_size} bytes)")
    return True


# ── Main ─────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{BOLD}{'═'*50}")
    print("  N1700 Bridge — Connection Diagnostic")
    print(f"{'═'*50}{RESET}")

    results: dict[str, bool] = {}

    results["python"] = check_python()

    config = check_config()
    results["config"] = config is not None

    if config:
        n1700 = config.get("n1700", {})
        info_mode = (
            "DLL Direct" if n1700.get("use_dll") else
            "Fake" if n1700.get("use_fake", True) else
            "Pywinauto"
        )
        plc_cfg = config.get("plc", {})
        info_plc = "Fake" if plc_cfg.get("use_fake", True) else f"{plc_cfg.get('host')}:{plc_cfg.get('port')}"

        section("Config Summary")
        info(f"N1700 mode  : {info_mode}")
        info(f"PLC target  : {info_plc}")
        info(f"Channels    : {n1700.get('channel_count', 9)}")

        results["n1700_dll"] = check_n1700_dll(config)
        results["n1700_pywinauto"] = check_n1700_pywinauto(config)
        results["plc"] = check_plc(config)
        results["excel"] = check_excel(config)

    # Summary
    section("SUMMARY")
    all_pass = all(results.values())
    for name, passed in results.items():
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"  {name:.<30} {status}")

    print()
    if all_pass:
        print(f"  {GREEN}{BOLD}All checks passed! Run: python -m n1700_bridge{RESET}")
    else:
        print(f"  {RED}{BOLD}Some checks failed. Fix the issues above and retry.{RESET}")
    print()

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
