"""Build script for creating n1700_bridge executable with PyInstaller.

Usage:
    python build.py

On Windows, this creates: dist/n1700_bridge.exe  (with Desktop shortcut)
On macOS, this creates: dist/n1700_bridge (for testing the build process)
"""

import platform
import subprocess
import sys
from pathlib import Path


def create_icon(assets_dir: Path) -> Path | None:
    """Generate a simple ICO file using Pillow. Returns path or None on failure."""
    ico_path = assets_dir / "icon.ico"
    if ico_path.exists():
        return ico_path

    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore[import]
    except ImportError:
        print("Pillow not installed — skipping icon generation (pip install Pillow)")
        return None

    sizes = [256, 128, 64, 48, 32, 16]
    images: list[Image.Image] = []

    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Circle background — deep blue
        margin = max(1, size // 16)
        draw.ellipse(
            [margin, margin, size - margin - 1, size - margin - 1],
            fill=(26, 86, 161, 255),
        )

        # Letter "N" centered — scale font to size
        font_size = max(8, int(size * 0.55))
        font: ImageFont.ImageFont | ImageFont.FreeTypeFont
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

        text = "N"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (size - text_w) / 2 - bbox[0]
        y = (size - text_h) / 2 - bbox[1]
        draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

        images.append(img)

    images[0].save(
        ico_path,
        format="ICO",
        sizes=[(img.width, img.height) for img in images],
        append_images=images[1:],
    )
    print(f"Icon created: {ico_path}")
    return ico_path


def create_desktop_shortcut(exe_path: Path, icon_path: Path | None) -> None:
    """Create a Windows Desktop shortcut (.lnk) for the built executable."""
    if platform.system() != "Windows":
        print("Shortcut creation is Windows-only — skipping on this platform.")
        return

    try:
        import winreg  # noqa: F401  — guard: confirms we're on Windows
        from win32com.shell import shell  # type: ignore[import]
        import pythoncom  # type: ignore[import]
    except ImportError:
        print(
            "pywin32 not installed — skipping shortcut creation.\n"
            "  Install with: pip install pywin32"
        )
        return

    pythoncom.CoInitialize()
    try:
        desktop = Path(shell.SHGetFolderPath(0, 0x0010, None, 0))  # CSIDL_DESKTOP
        lnk_path = desktop / "N1700 Bridge.lnk"

        shortcut = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IShellLink,
        )
        shortcut.SetPath(str(exe_path))
        shortcut.SetWorkingDirectory(str(exe_path.parent))
        shortcut.SetDescription("N1700 Bridge — PLC measurement tool")
        if icon_path and icon_path.exists():
            shortcut.SetIconLocation(str(exe_path), 0)

        persist = shortcut.QueryInterface(pythoncom.IID_IPersistFile)
        persist.Save(str(lnk_path), True)
        print(f"Shortcut created: {lnk_path}")
    finally:
        pythoncom.CoUninitialize()


def build() -> None:
    """Run PyInstaller to create a single executable."""
    root = Path(__file__).parent
    assets_dir = root / "assets"
    assets_dir.mkdir(exist_ok=True)
    entry = root / "src" / "n1700_bridge" / "__main__.py"

    icon_path = create_icon(assets_dir)

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

    if icon_path and icon_path.exists():
        cmd.extend(["--icon", str(icon_path)])

    # Data files
    separator = ";" if platform.system() == "Windows" else ":"
    for src, dst in datas:
        cmd.extend(["--add-data", f"{src}{separator}{dst}"])

    # Hidden imports that PyInstaller might miss
    cmd.extend([
        "--hidden-import", "n1700_bridge",
        "--hidden-import", "n1700_bridge.app",
        "--hidden-import", "n1700_bridge.config.settings",
        "--hidden-import", "n1700_bridge.adapters.plc_fake",
        "--hidden-import", "n1700_bridge.adapters.plc_slmp",
        "--hidden-import", "n1700_bridge.adapters.n1700_fake",
        "--hidden-import", "n1700_bridge.adapters.n1700_pywinauto",
        "--hidden-import", "n1700_bridge.adapters.excel_xlwings",
        "--hidden-import", "n1700_bridge.adapters.n1700_dll",
        "--hidden-import", "n1700_bridge.services.measurement_service",
        "--hidden-import", "n1700_bridge.services.measurement_store",
        "--hidden-import", "n1700_bridge.services.plc_listener",
        "--hidden-import", "n1700_bridge.services.excel_judgment_service",
        "--hidden-import", "n1700_bridge.services.register_manager",
        "--hidden-import", "n1700_bridge.services.report_exporter",
        "--hidden-import", "n1700_bridge.ui.main_window",
        "--hidden-import", "n1700_bridge.ui.handlers",
        "--hidden-import", "n1700_bridge.ui.widgets.judgment_panel",
        "--hidden-import", "n1700_bridge.utils.qt_signals",
        "--hidden-import", "n1700_bridge.utils.logging_config",
        "--hidden-import", "pydantic_settings",
        "--hidden-import", "openpyxl",
        "--hidden-import", "pymcprotocol",
        "--hidden-import", "pywinauto",
    ])

    cmd.extend(["--paths", str(root / "src")])
    cmd.append(str(entry))

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(root))

    if result.returncode == 0:
        exe_name = "n1700_bridge.exe" if platform.system() == "Windows" else "n1700_bridge"
        exe_path = root / "dist" / exe_name
        print(f"\nBuild successful! Executable: {exe_path}")
        print(f"Size: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
        create_desktop_shortcut(exe_path, icon_path)
    else:
        print("\nBuild failed!", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    build()
