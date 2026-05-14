"""Entry point for running the application: python -m n1700_bridge."""

import os
import sys
from pathlib import Path


def _get_base_dir() -> Path:
    """Get base directory — handles both dev mode and PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle
        return Path(sys.executable).parent
    return Path.cwd()


def main() -> None:
    """Launch the N1700 Bridge application."""
    base_dir = _get_base_dir()

    # If running from PyInstaller, extract bundled data to working dir
    if getattr(sys, "frozen", False):
        bundle_dir = Path(getattr(sys, "_MEIPASS", "."))
        # Copy config example if config.json doesn't exist
        config_path = base_dir / "config" / "config.json"
        if not config_path.exists():
            bundled_example = bundle_dir / "config" / "config.example.json"
            if bundled_example.exists():
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(bundled_example.read_text())

        # Copy sample Excel if not present
        mocks_path = base_dir / "mocks" / "sample_n1700_output.xlsx"
        if not mocks_path.exists():
            bundled_xlsx = bundle_dir / "mocks" / "sample_n1700_output.xlsx"
            if bundled_xlsx.exists():
                mocks_path.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(bundled_xlsx, mocks_path)

        os.chdir(base_dir)
    else:
        # Dev mode: ensure config file exists
        config_path = Path("config/config.json")
        if not config_path.exists():
            example = Path("config/config.example.json")
            if example.exists():
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(example.read_text())

    from n1700_bridge.app import build_app
    from n1700_bridge.config.settings import AppSettings

    settings = AppSettings()
    qt_app, window, warnings = build_app(settings)
    window.show()
    window.show_connection_warnings(warnings)
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
