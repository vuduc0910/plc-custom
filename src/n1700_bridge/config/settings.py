from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel
from pydantic_settings import BaseSettings, JsonConfigSettingsSource, PydanticBaseSettingsSource


class PLCSettings(BaseModel):

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

    window_title_regex: str = "N1700.*"
    button_name: str = "Data"
    fallback_coords: tuple[int, int] | None = None
    use_fake: bool = True
    use_dll: bool = False
    dll_path: str = "N1700.dll"
    channel_count: int = 9
    channel_start_index: int = 1


class ExcelInputSettings(BaseModel):

    path: str = "mocks/sample_n1700_output.xlsx"
    sheet_name: str = "Sheet1"
    header_row: int = 1
    port_columns: list[str] = ["B", "C", "D", "E", "F", "G", "H", "I", "J"]
    use_fake: bool = True


class ExcelTemplateSettings(BaseModel):

    path: str = "./config/template.xlsx"
    sheet_name: str = "Sheet1"
    input_cells: list[str] = [
        "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "B10",
    ]


class JudgmentGroupSettings(BaseModel):

    name: str
    output_cell: str


class HMIControlSettings(BaseModel):

    get_zero_trigger: str = "D1220"
    get_zero_save: str = "M1220"
    master_word_1_4: str = "D1230"
    master_word_5_8: str = "D1232"
    master_word_9: str = "D1234"
    master_save: str = "M1230"
    stats_1_4_min: str = "D1240"
    stats_1_4_max: str = "D1242"
    stats_1_4_avg: str = "D1244"
    stats_5_8_min: str = "D1250"
    stats_5_8_max: str = "D1252"
    stats_5_8_avg: str = "D1254"
    poll_interval_ms: int = 200


class AppSettings(BaseSettings):

    model_config = {"extra": "ignore"}
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
    excel_input: ExcelInputSettings = ExcelInputSettings()
    excel_template: ExcelTemplateSettings = ExcelTemplateSettings()
    judgment_groups: list[JudgmentGroupSettings] = [
        JudgmentGroupSettings(name="G1", output_cell="K2"),
        JudgmentGroupSettings(name="G2", output_cell="L2"),
        JudgmentGroupSettings(name="G3", output_cell="M2"),
    ]
    multiplier: float = 1.0
    port_addresses: dict[str, str] = {
        str(i): f"D{1198 + i * 2}" for i in range(1, 10)
    }
    port_verdict_addresses: dict[str, str] = {
        str(i): f"D{1130 + i}" for i in range(1, 10)
    }
    judgment_addresses: dict[str, str] = {
        "1": "D1300", "2": "D1301", "3": "D1302",
    }
    hmi_control: HMIControlSettings = HMIControlSettings()
    settling_delay_ms: int = 500
    report_output_dir: Path = Path("./reports")
    log_dir: Path = Path("./logs")
    db_path: Path = Path("./data/measurements.db")
