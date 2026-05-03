# N1700 Bridge

Middleware bridging **Mahr Millimar N1700** probe amplifier to **Mitsubishi FX5U** PLC via SLMP protocol.

## Connection Modes

| Mode | How it works | When to use |
|------|-------------|-------------|
| **DLL Direct** ★ | Calls `N1700.dll` via ctypes → `N1700PollData()` | **Production** — fast, no GUI needed |
| **Pywinauto** | Clicks "Data" button on N1700 desktop app → reads Excel | Legacy / fallback |
| **Fake** | Simulated data for development | Dev / testing on macOS |

> **Recommended**: Use DLL Direct mode. Set `"use_dll": true` in `config/config.json`.

## Requirements

- Python 3.11 or 3.12 (NOT 3.13)
- Windows 10/11 (macOS for dev with fake adapters only)
- FTDI D2XX driver (CDM21224) — required for DLL Direct mode
- `N1700.dll` (Win32) or `N1700_64.dll` (Win64) from Mahr SDK

## Quick Start

```bash
# 1. Setup
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 2. Configure
cp config/config.example.json config/config.json
# Edit config.json — set use_dll, PLC host, thresholds, etc.

# 3. Run
python -m n1700_bridge
```

## Configuration

Edit `config/config.json`:

```jsonc
{
  "n1700": {
    "use_dll": true,             // ★ DLL Direct mode (recommended)
    "dll_path": "N1700.dll",     // Path to vendor DLL
    "channel_count": 9,          // Number of measurement channels
    "use_fake": false            // Set true for dev without hardware
  },
  "plc": {
    "host": "192.168.1.10",
    "port": 5007,
    "use_fake": false             // Set true for dev without PLC
  }
}
```

## Run with Mock PLC Panel

```bash
# Terminal 1 — main app (fake mode)
python -m n1700_bridge

# Terminal 2 — simulated PLC control panel
python -m mocks.plc_control_panel
```

## Development

```bash
ruff check src/                   # Lint
mypy src/                         # Type check
pytest tests/                     # Unit + integration tests
pytest tests/ --cov=n1700_bridge  # With coverage
```

## Build Standalone Executable

```bash
python build.py    # → dist/n1700_bridge.exe (PyInstaller one-file)
```

## Docs

- [Architecture](docs/architecture.md) — layering, threading, data flow
- [POC Spec](docs/POC_SPEC.md) — original requirements specification
- [Project Overview](PROJECT_OVERVIEW.md) — full codebase walkthrough
