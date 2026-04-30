# N1700 Bridge

Middleware software bridging N1700 probe amplifier to Mitsubishi FX5U PLC via SLMP protocol.

## Requirements

- Python 3.11 or 3.12 (NOT 3.13)
- Windows 10/11
- Excel installed (for xlwings live reading)

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Run

```bash
python -m n1700_bridge
```

## Run with mock PLC panel

```bash
# Terminal 1
python -m n1700_bridge

# Terminal 2
python -m mocks.plc_control_panel
```

## Architecture

See [docs/architecture.md](docs/architecture.md) and [docs/POC_SPEC.md](docs/POC_SPEC.md).

## Development

```bash
ruff check src/
mypy src/
pytest tests/
```
