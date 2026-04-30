"""Build script for creating n1700_bridge executable with PyInstaller.

Usage:
    python build.py

On Windows, this creates: dist/n1700_bridge.exe
On macOS, this creates: dist/n1700_bridge (for testing the build process)
"""

import platform
import subprocess
import sys
from pathlib import Path


def build() -> None:
    """Run PyInstaller to create a single executable."""
    root = Path(__file__).parent
    entry = root / "src" / "n1700_bridge" / "__main__.py"

    # Data files to include
    datas = [
        (str(root / "config" / "config.example.json"), "config"),
        (str(root / "mocks" / "sample_n1700_output.xlsx"), "mocks"),
        (str(root / "src" / "n1700_bridge" / "ui" / "resources" / "styles.qss"),
         str(Path("n1700_bridge") / "ui" / "resources")),
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "n1700_bridge",
        "--clean",
    ]

    # Add data files
    separator = ";" if platform.system() == "Windows" else ":"
    for src, dst in datas:
        cmd.extend(["--add-data", f"{src}{separator}{dst}"])

    # Hidden imports that PyInstaller might miss
    cmd.extend([
        "--hidden-import", "n1700_bridge",
        "--hidden-import", "n1700_bridge.app",
        "--hidden-import", "n1700_bridge.config.settings",
        "--hidden-import", "n1700_bridge.adapters.plc_fake",
        "--hidden-import", "n1700_bridge.adapters.n1700_fake",
        "--hidden-import", "n1700_bridge.adapters.excel_xlwings",
        "--hidden-import", "n1700_bridge.services.measurement_service",
        "--hidden-import", "n1700_bridge.services.plc_listener",
        "--hidden-import", "n1700_bridge.services.judgment_service",
        "--hidden-import", "n1700_bridge.services.register_manager",
        "--hidden-import", "n1700_bridge.ui.main_window",
        "--hidden-import", "n1700_bridge.utils.qt_signals",
        "--hidden-import", "n1700_bridge.utils.logging_config",
        "--hidden-import", "pydantic_settings",
        "--hidden-import", "openpyxl",
    ])

    # Add paths
    cmd.extend(["--paths", str(root / "src")])

    # Entry point
    cmd.append(str(entry))

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(root))

    if result.returncode == 0:
        exe_name = "n1700_bridge.exe" if platform.system() == "Windows" else "n1700_bridge"
        exe_path = root / "dist" / exe_name
        print(f"\nBuild successful! Executable: {exe_path}")
        print(f"Size: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        print("\nBuild failed!", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    build()
