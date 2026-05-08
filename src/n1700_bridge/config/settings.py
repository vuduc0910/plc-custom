"""Application settings loaded from config.json and environment variables."""

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel
from pydantic_settings import BaseSettings, JsonConfigSettingsSource, PydanticBaseSettingsSource


class PLCSettings(BaseModel):
    """PLC connection settings."""

    host: str = "192.168.1.10"
    port: int = 5007
    comm_type: str = "binary"
    plc_type: str = "iQ-R"
    trigger_bit: str = "M100"
    done_bit: str = "M101"
    barcode_ready_bit: str = "M102"
    rescan_bit: str = "D1002"
    poll_interval_ms: int = 100
    use_fake: bool = True


class N1700Settings(BaseModel):
    """N1700 application settings."""

    window_title_regex: str = "N1700.*"
    button_name: str = "Data"
    fallback_coords: tuple[int, int] | None = None
    use_fake: bool = True
    # When True, bypass pywinauto + Excel and read directly via N1700.dll.
    # Requires Windows + FTDI CDM21224 driver. Overrides use_fake for real hw.
    use_dll: bool = False
    dll_path: str = "N1700.dll"
    channel_count: int = 9
    channel_start_index: int = 1


class ExcelSettings(BaseModel):
    """Excel input file settings."""

    path: str = "mocks/sample_n1700_output.xlsx"
    sheet_name: str = "Sheet1"
    header_row: int = 1
    port_columns: list[str] = ["B", "C", "D", "E", "F", "G", "H", "I", "J"]
    use_fake: bool = True


class FormulaGroupSettings(BaseModel):
    ports: list[int]
    formula: str
    lower: float
    upper: float


class AppSettings(BaseSettings):

    _json_file: ClassVar[str] = "config/config.json"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            JsonConfigSettingsSource(settings_cls, json_file=cls._json_file),
            file_secret_settings,
        )

    plc: PLCSettings = PLCSettings()
    n1700: N1700Settings = N1700Settings()
    excel_input: ExcelSettings = ExcelSettings()
    formula_groups: list[FormulaGroupSettings] = [
        FormulaGroupSettings(ports=[1, 2, 3, 4], formula="(p1+p2+p3+p4)/4", lower=-0.05, upper=0.05),
        FormulaGroupSettings(ports=[5, 6, 7, 8], formula="(p5+p6+p7+p8)/4", lower=-0.05, upper=0.05),
        FormulaGroupSettings(ports=[9], formula="p9", lower=-0.05, upper=0.05),
    ]
    settling_delay_ms: int = 500
    report_output_dir: Path = Path("./reports")
    log_dir: Path = Path("./logs")
    db_path: Path = Path("./data/measurements.db")
