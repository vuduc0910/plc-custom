import sys
from pathlib import Path
from typing import Any

from loguru import logger
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from n1700_bridge.adapters.excel_xlwings import OpenpyxlExcelSource
from n1700_bridge.adapters.n1700_fake import FakeN1700Controller
from n1700_bridge.adapters.plc_fake import FakePLCClient
from n1700_bridge.config.settings import AppSettings
from n1700_bridge.core.models import ExcelTemplateConfig, JudgmentGroupConfig
from n1700_bridge.services.excel_judgment_service import ExcelJudgmentService
from n1700_bridge.services.measurement_service import MeasurementService
from n1700_bridge.services.measurement_store import MeasurementStore
from n1700_bridge.services.plc_listener import PLCListener
from n1700_bridge.services.register_manager import RegisterManager
from n1700_bridge.ui.main_window import MainWindow
from n1700_bridge.utils.logging_config import setup_logging


def build_app(settings: AppSettings) -> tuple[QApplication, MainWindow]:
    qt_app = QApplication(sys.argv)

    setup_logging(settings.log_dir)
    logger.info("Starting N1700 Bridge")

    excel_path = Path(settings.excel_input.path)
    plc = _create_plc(settings)
    n1700, excel, dll_client = _create_n1700_and_excel(settings, excel_path)

    register_mgr = RegisterManager.load_or_create("config/registers.json")

    template_config = ExcelTemplateConfig(
        path=settings.excel_template.path,
        sheet_name=settings.excel_template.sheet_name,
        input_cells=tuple(settings.excel_template.input_cells),
    )
    judgment_groups = [
        JudgmentGroupConfig(
            name=g.name,
            output_cell=g.output_cell,
            lower=g.lower,
            upper=g.upper,
        )
        for g in settings.judgment_groups
    ]
    judgment = ExcelJudgmentService(template_config, judgment_groups)

    store = MeasurementStore(settings.db_path)
    logger.info("MeasurementStore: {} existing records", store.count())

    measurement_svc = MeasurementService(
        plc=plc,
        n1700=n1700,
        excel=excel,
        judgment=judgment,
        registers=register_mgr,
        settling_delay_ms=settings.settling_delay_ms,
        barcode_ready_bit=settings.plc.barcode_ready_bit,
        done_bit=settings.plc.done_bit,
        trigger_bit=settings.plc.trigger_bit,
        store=store,
    )

    measurement_svc.restore_history(store.load_recent(limit=1000))

    plc_thread, listener = _create_plc_thread(settings, plc)
    measurement_thread = QThread()
    measurement_svc.moveToThread(measurement_thread)
    listener.trigger_received.connect(measurement_svc.run_cycle)
    measurement_thread.start()

    window = MainWindow()
    window.wire_services(
        measurement_svc=measurement_svc,
        register_mgr=register_mgr,
        plc=plc,
        n1700=n1700,
        report_output_dir=settings.report_output_dir,
        excel_path=excel_path,
    )

    listener.rescan_received.connect(window._on_barcode_reset)

    plc.connect()
    plc_thread.start()

    window._refs = {  # type: ignore[attr-defined]
        "plc_thread": plc_thread,
        "measurement_thread": measurement_thread,
        "listener": listener,
        "measurement_svc": measurement_svc,
        "plc": plc,
        "dll_client": dll_client,
        "judgment": judgment,
    }

    logger.info("Application built successfully")
    return qt_app, window


def _create_plc(settings: AppSettings) -> Any:
    if settings.plc.use_fake:
        logger.info("Using FakePLCClient")
        return FakePLCClient()

    from n1700_bridge.adapters.plc_rk import RkSLMPPLCClient

    logger.info("Using RkSLMPPLCClient: {}:{}", settings.plc.host, settings.plc.port)
    return RkSLMPPLCClient(host=settings.plc.host, port=settings.plc.port)


def _create_n1700_and_excel(
    settings: AppSettings, excel_path: Path,
) -> tuple[Any, Any, Any]:
    dll_client: Any = None

    if settings.n1700.use_dll:
        from n1700_bridge.adapters.n1700_dll import (
            DllN1700Controller,
            DllN1700Source,
            N1700DllClient,
        )

        dll_client = N1700DllClient(dll_path=settings.n1700.dll_path)
        dll_client.connect()
        n1700: Any = DllN1700Controller(dll_client)
        excel: Any = DllN1700Source(
            dll_client,
            channel_count=settings.n1700.channel_count,
            channel_start_index=settings.n1700.channel_start_index,
        )
        logger.info(
            "Using N1700 DLL direct mode ({} channels via {})",
            settings.n1700.channel_count, settings.n1700.dll_path,
        )
        return n1700, excel, dll_client

    if settings.n1700.use_fake:
        n1700 = FakeN1700Controller(excel_path)
        logger.info("Using FakeN1700Controller")
    else:
        from n1700_bridge.adapters.n1700_pywinauto import PywinautoN1700Controller

        n1700 = PywinautoN1700Controller(
            window_title_regex=settings.n1700.window_title_regex,
            button_name=settings.n1700.button_name,
            fallback_coords=settings.n1700.fallback_coords,
        )
        logger.info("Using PywinautoN1700Controller: {}", settings.n1700.window_title_regex)

    excel = OpenpyxlExcelSource(
        path=excel_path,
        sheet_name=settings.excel_input.sheet_name,
        header_row=settings.excel_input.header_row,
        port_columns=settings.excel_input.port_columns,
    )
    return n1700, excel, dll_client


def _create_plc_thread(settings: AppSettings, plc: Any) -> tuple[QThread, PLCListener]:
    plc_thread = QThread()
    listener = PLCListener(
        plc=plc,
        trigger_address=settings.plc.trigger_bit,
        rescan_address=settings.plc.rescan_bit,
        poll_ms=settings.plc.poll_interval_ms,
    )
    listener.moveToThread(plc_thread)
    plc_thread.started.connect(listener.start_polling)
    return plc_thread, listener
