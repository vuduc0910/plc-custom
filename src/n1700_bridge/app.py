"""Application bootstrap with dependency injection wiring."""

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
from n1700_bridge.core.models import FormulaGroupConfig
from n1700_bridge.services.judgment_service import JudgmentService
from n1700_bridge.services.measurement_service import MeasurementService
from n1700_bridge.services.measurement_store import MeasurementStore
from n1700_bridge.services.plc_listener import PLCListener
from n1700_bridge.services.register_manager import RegisterManager
from n1700_bridge.ui.main_window import MainWindow
from n1700_bridge.utils.logging_config import setup_logging


def build_app(settings: AppSettings) -> tuple[QApplication, MainWindow]:
    """Build the application with all dependencies wired.

    Args:
        settings: Application settings.

    Returns:
        Tuple of (QApplication, MainWindow).
    """
    qt_app = QApplication(sys.argv)

    # Setup logging
    setup_logging(settings.log_dir)
    logger.info("Starting N1700 Bridge")

    # --- Adapters (swap real/fake by config) ---
    excel_path = Path(settings.excel_input.path)

    if settings.plc.use_fake:
        plc: Any = FakePLCClient()
        logger.info("Using FakePLCClient")
    else:
        from n1700_bridge.adapters.plc_rk import RkSLMPPLCClient

        plc = RkSLMPPLCClient(
            host=settings.plc.host,
            port=settings.plc.port,
        )
        logger.info("Using RkSLMPPLCClient (FX5U): {}:{}", settings.plc.host, settings.plc.port)

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
    else:
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
            logger.info(
                "Using PywinautoN1700Controller: {}",
                settings.n1700.window_title_regex,
            )

        excel = OpenpyxlExcelSource(
            path=excel_path,
            sheet_name=settings.excel_input.sheet_name,
            header_row=settings.excel_input.header_row,
            port_columns=settings.excel_input.port_columns,
        )

    # --- Services ---
    register_mgr = RegisterManager.load_or_create("config/registers.json")

    formula_groups = [
        FormulaGroupConfig(
            ports=tuple(g.ports),
            formula=g.formula,
            lower=g.lower,
            upper=g.upper,
        )
        for g in settings.formula_groups
    ]
    judgment = JudgmentService(formula_groups)

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

    # Restore recent history from DB so Export reflects past sessions
    measurement_svc.restore_history(store.load_recent(limit=1000))

    # --- Threads ---
    plc_thread = QThread()
    listener = PLCListener(
        plc=plc,
        trigger_address=settings.plc.trigger_bit,
        rescan_address=settings.plc.rescan_bit,
        poll_ms=settings.plc.poll_interval_ms,
    )
    listener.moveToThread(plc_thread)
    plc_thread.started.connect(listener.start_polling)

    measurement_thread = QThread()
    measurement_svc.moveToThread(measurement_thread)
    listener.trigger_received.connect(measurement_svc.run_cycle)
    measurement_thread.start()

    # --- UI ---
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

    # Connect PLC and start polling
    plc.connect()
    plc_thread.start()

    # Keep references alive on the window to prevent GC
    window._refs = {  # type: ignore[attr-defined]
        "plc_thread": plc_thread,
        "measurement_thread": measurement_thread,
        "listener": listener,
        "measurement_svc": measurement_svc,
        "plc": plc,
        "dll_client": dll_client,
    }

    logger.info("Application built successfully")
    return qt_app, window
