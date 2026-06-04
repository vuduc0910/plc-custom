# Huong dan cau hinh — config.json

> JSON khong ho tro comment. File nay mo ta y nghia tung truong trong `config.json`.

---

## `plc` — Ket noi PLC Mitsubishi iQ-R

| Truong              | Mo ta                                                        |
| ------------------- | ------------------------------------------------------------ |
| `host`              | Dia chi IP cua PLC                                           |
| `port`              | Cong TCP ket noi PLC (mac dinh 5007)                         |
| `comm_type`         | Giao thuc truyen thong: `"binary"` hoac `"ascii"`            |
| `plc_type`          | Dong PLC: `"iQ-R"`, `"Q"`, `"L"`, ...                       |
| `trigger_bit`       | Dia chi bit PLC gui tin hieu bat dau do (VD: `D1000`)        |
| `done_bit`          | Dia chi bit ung dung ghi lai khi do xong (VD: `D1010`)      |
| `barcode_ready_bit` | Dia chi bit bao barcode da san sang (VD: `D1020`)            |
| `rescan_bit`        | Dia chi bit yeu cau quet lai barcode (VD: `D1002`)           |
| `poll_interval_ms`  | Chu ky doc PLC (ms). Gia tri nho = phan hoi nhanh, CPU cao  |
| `use_fake`          | `true` = dung PLC gia lap de test, `false` = ket noi PLC that |

---

## `n1700` — Dieu khien may do Mahr Millimar N1700

| Truong                | Mo ta                                                           |
| --------------------- | --------------------------------------------------------------- |
| `use_dll`             | `true` = doc gia tri qua DLL, `false` = dieu khien qua UI      |
| `dll_path`            | Duong dan tuyet doi den file `N1700_64.dll`                     |
| `use_fake`            | `true` = dung adapter gia lap, `false` = ket noi may that       |
| `window_title_regex`  | Regex khop voi tieu de cua so N1700 (de pywinauto tim)          |
| `button_name`         | Ten nut "Data" tren giao dien N1700 (dung khi dieu khien qua UI) |
| `fallback_coords`     | Toa do pixel [x, y] cua nut Data (dung khi khong tim thay nut)  |
| `channel_count`       | So kenh do (so port) tren N1700                                  |
| `channel_start_index` | Chi so kenh bat dau (thuong la 1)                                |

---

## `excel_input` — Doc du lieu tu file Excel dau ra N1700

| Truong          | Mo ta                                                    |
| --------------- | -------------------------------------------------------- |
| `path`          | Duong dan den file Excel chua ket qua do tu N1700        |
| `sheet_name`    | Ten sheet can doc                                        |
| `header_row`    | Dong chua tieu de cot (1-indexed)                        |
| `port_columns`  | Danh sach cot Excel tuong ung voi tung port (B -> J = 9 port) |
| `use_fake`      | `true` = dung du lieu mau, `false` = doc file that       |

---

## `excel_template` — Template Excel de tinh toan judgment

| Truong        | Mo ta                                                         |
| ------------- | ------------------------------------------------------------- |
| `path`        | Duong dan den file template Excel chua cong thuc judgment      |
| `sheet_name`  | Ten sheet chua cong thuc                                       |
| `input_cells` | Danh sach o nhap gia tri do cho tung port (B2 -> B10 = 9 port) |

---

## `judgment_groups` — Nhom danh gia OK/NG

Moi nhom la mot doi tuong voi:

| Truong        | Mo ta                                                    |
| ------------- | -------------------------------------------------------- |
| `name`        | Ten nhom: `G1`, `G2`, `G3`                              |
| `output_cell` | O Excel chua ket qua judgment cua nhom (VD: `K2`, `L2`) |

---

## `port_addresses` — Dia chi PLC ghi gia tri do cho tung port

Key la so thu tu port (`"1"` den `"9"`), value la dia chi thanh ghi PLC (kieu `D` register, 32-bit).

VD: Port 1 = `D1200`, Port 2 = `D1202`, ... (moi port cach nhau 2 word vi dung FLOAT 32-bit).

---

## `port_verdict_addresses` — Dia chi PLC ghi ket qua OK/NG cho tung port

Key la so thu tu port, value la dia chi thanh ghi PLC.

VD: Port 1 = `D1311`, Port 2 = `D1312`, ... (moi port 1 word, gia tri: 0 = NG, 1 = OK).

---

## `judgment_addresses` — Dia chi PLC ghi ket qua judgment cho tung nhom

Key la so thu tu nhom (`"1"` den `"3"`), value la dia chi thanh ghi PLC.

VD: Nhom 1 = `D1300`, Nhom 2 = `D1301`, Nhom 3 = `D1302`.

---

## `hmi_control` — Dia chi PLC cho dieu khien HMI (Get Zero, Master, Thong ke)

| Truong             | Mo ta                                                            |
| ------------------ | ---------------------------------------------------------------- |
| `get_zero_trigger` | Dia chi bit HMI gui lenh Get Zero (VD: `D1220`)                 |
| `get_zero_save`    | Dia chi bit xac nhan da luu gia tri zero (VD: `M1220`)          |
| `master_word_1_4`  | Dia chi ghi gia tri master cho port 1-4 (32-bit x2 = 4 port)   |
| `master_word_5_8`  | Dia chi ghi gia tri master cho port 5-8                          |
| `master_word_9`    | Dia chi ghi gia tri master cho port 9                            |
| `master_save`      | Dia chi bit xac nhan da luu master (VD: `M1230`)                |
| `stats_1_4_min`    | Dia chi doc gia tri min thong ke port 1-4                        |
| `stats_1_4_max`    | Dia chi doc gia tri max thong ke port 1-4                        |
| `stats_1_4_avg`    | Dia chi doc gia tri trung binh thong ke port 1-4                 |
| `stats_5_8_min`    | Dia chi doc gia tri min thong ke port 5-8                        |
| `stats_5_8_max`    | Dia chi doc gia tri max thong ke port 5-8                        |
| `stats_5_8_avg`    | Dia chi doc gia tri trung binh thong ke port 5-8                 |
| `zero_display_addresses`   | Dia chi PLC ghi gia tri zero de HMI hien thi (D1400-D1408)      |
| `poll_interval_ms` | Chu ky doc HMI control (ms)                                      |

---

## Cac truong goc (root-level)

| Truong              | Mo ta                                                            |
| ------------------- | ---------------------------------------------------------------- |
| `multiplier`        | He so nhan gia tri do truoc khi ghi vao PLC (1.0 = giu nguyen)  |
| `settling_delay_ms` | Thoi gian cho (ms) sau khi nhan trigger truoc khi doc gia tri do |
| `report_output_dir` | Thu muc xuat bao cao                                             |
| `log_dir`           | Thu muc luu log                                                  |
| `db_path`           | Duong dan file SQLite luu lich su do luong                       |
