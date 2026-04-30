"""Script to create the seed sample_n1700_output.xlsx with 2 rows."""

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook


def create_seed() -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None

    # Header
    ws.append(["Timestamp"] + [f"Port{i}" for i in range(1, 10)])

    # 2 seed rows
    ws.append([datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               0.012, -0.003, 0.025, -0.011, 0.008, 0.031, -0.022, 0.015, -0.005])
    ws.append([datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               0.015, -0.001, 0.022, -0.015, 0.011, 0.028, -0.019, 0.018, -0.008])

    out = Path(__file__).parent / "sample_n1700_output.xlsx"
    wb.save(out)
    wb.close()
    print(f"Created {out}")


if __name__ == "__main__":
    create_seed()
