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
    trigger_bit: str = "M100"
    done_bit: str = "M101"
    barcode_ready_bit: str = "M102"
    poll_interval_ms: int = 100
    use_fake: bool = True


class N1700Settings(BaseModel):
    """N1700 application settings."""

    window_title_regex: str = "N1700.*"
    button_name: str = "Data"
    fallback_coords: tuple[int, int] | None = None
    use_fake: bool = True


class ExcelSettings(BaseModel):
    """Excel input file settings."""

    path: str = "mocks/sample_n1700_output.xlsx"
    sheet_name: str = "Sheet1"
    header_row: int = 1
    port_columns: list[str] = ["B", "C", "D", "E", "F", "G", "H", "I", "J"]
    use_fake: bool = True


class ThresholdConfig(BaseModel):
    """Threshold configuration for a single port."""

    # TODO(client-Q1.2): Confirm threshold source with client.
    port: int
    lower: float
    upper: float


class AppSettings(BaseSettings):
    """Main application settings.

    Loads from config/config.json with env var overrides (prefix N1700_).
    """

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
        """Add JSON config file as a settings source."""
        return (
            init_settings,
            env_settings,
            JsonConfigSettingsSource(settings_cls, json_file=cls._json_file),
            file_secret_settings,
        )

    plc: PLCSettings = PLCSettings()
    n1700: N1700Settings = N1700Settings()
    excel_input: ExcelSettings = ExcelSettings()
    thresholds: list[ThresholdConfig] = []
    judgment_grouping: list[tuple[int, int, int]] = [(1, 2, 3), (4, 5, 6), (7, 8, 9)]
    settling_delay_ms: int = 500
    report_output_dir: Path = Path("./reports")
    log_dir: Path = Path("./logs")
