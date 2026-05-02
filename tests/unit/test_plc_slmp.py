"""Tests for SLMPPLCClient adapter."""

import struct
from unittest.mock import MagicMock, patch

import pytest

from n1700_bridge.adapters.plc_slmp import SLMPPLCClient
from n1700_bridge.core.plc import PLCAddressError, PLCConnectionError, PLCError


class TestAddressParsing:
    """Tests for the static address parsing method."""

    def test_parse_d_register(self) -> None:
        """D100 should parse to ('D', 100)."""
        assert SLMPPLCClient._parse_address("D100") == ("D", 100)

    def test_parse_m_register(self) -> None:
        """M200 should parse to ('M', 200)."""
        assert SLMPPLCClient._parse_address("M200") == ("M", 200)

    def test_parse_x_register(self) -> None:
        """X10 should parse to ('X', 10)."""
        assert SLMPPLCClient._parse_address("X10") == ("X", 10)

    def test_parse_y_register(self) -> None:
        """Y0 should parse to ('Y', 0)."""
        assert SLMPPLCClient._parse_address("Y0") == ("Y", 0)

    def test_parse_r_register(self) -> None:
        """R50 should parse to ('R', 50)."""
        assert SLMPPLCClient._parse_address("R50") == ("R", 50)

    def test_invalid_empty(self) -> None:
        """Empty string should raise PLCAddressError."""
        with pytest.raises(PLCAddressError):
            SLMPPLCClient._parse_address("")

    def test_invalid_no_number(self) -> None:
        """'D' alone should raise PLCAddressError."""
        with pytest.raises(PLCAddressError):
            SLMPPLCClient._parse_address("D")

    def test_invalid_device_letter(self) -> None:
        """'Z100' should raise PLCAddressError (Z is not valid)."""
        with pytest.raises(PLCAddressError):
            SLMPPLCClient._parse_address("Z100")

    def test_invalid_lowercase(self) -> None:
        """'d100' should raise PLCAddressError (lowercase)."""
        with pytest.raises(PLCAddressError):
            SLMPPLCClient._parse_address("d100")


class TestConnectionManagement:
    """Tests for connect/disconnect/is_connected."""

    def test_not_connected_initially(self) -> None:
        """Client should not be connected before connect() is called."""
        client = SLMPPLCClient()
        assert client.is_connected() is False

    @patch("n1700_bridge.adapters.plc_slmp.pymcprotocol", create=True)
    def test_connect_success(self, mock_pymc: MagicMock) -> None:
        """Successful connect should set is_connected to True."""
        mock_type3e = MagicMock()
        mock_pymc.Type3E.return_value = mock_type3e

        with patch.dict("sys.modules", {"pymcprotocol": mock_pymc}):
            client = SLMPPLCClient(host="192.168.1.10", port=5007)
            client.connect()

        assert client.is_connected() is True
        mock_type3e.connect.assert_called_once_with("192.168.1.10", 5007)

    @patch("n1700_bridge.adapters.plc_slmp.pymcprotocol", create=True)
    def test_connect_retries_on_failure(self, mock_pymc: MagicMock) -> None:
        """Should retry 3 times and raise PLCConnectionError."""
        mock_type3e = MagicMock()
        mock_type3e.connect.side_effect = ConnectionError("timeout")
        mock_pymc.Type3E.return_value = mock_type3e

        with patch.dict("sys.modules", {"pymcprotocol": mock_pymc}):
            client = SLMPPLCClient()
            with pytest.raises(PLCConnectionError, match="after 3 attempts"):
                client.connect()

        assert client.is_connected() is False

    def test_disconnect(self) -> None:
        """Disconnect should set is_connected to False."""
        client = SLMPPLCClient()
        client._connected = True
        client._plc = MagicMock()

        client.disconnect()

        assert client.is_connected() is False


class TestReadWrite:
    """Tests for read/write operations with mocked PLC."""

    def _make_connected_client(self) -> tuple[SLMPPLCClient, MagicMock]:
        """Create a client in 'connected' state with a mock PLC."""
        client = SLMPPLCClient()
        mock_plc = MagicMock()
        client._plc = mock_plc
        client._connected = True
        return client, mock_plc

    def test_read_bit(self) -> None:
        """read_bit should call batchread_bitunits."""
        client, mock_plc = self._make_connected_client()
        mock_plc.batchread_bitunits.return_value = [1]

        result = client.read_bit("M100")

        assert result is True
        mock_plc.batchread_bitunits.assert_called_once_with(headdevice="M100", readsize=1)

    def test_write_bit(self) -> None:
        """write_bit should call batchwrite_bitunits with 1 or 0."""
        client, mock_plc = self._make_connected_client()

        client.write_bit("M200", True)
        mock_plc.batchwrite_bitunits.assert_called_with(headdevice="M200", values=[1])

        client.write_bit("M201", False)
        mock_plc.batchwrite_bitunits.assert_called_with(headdevice="M201", values=[0])

    def test_read_word(self) -> None:
        """read_word should call batchread_wordunits."""
        client, mock_plc = self._make_connected_client()
        mock_plc.batchread_wordunits.return_value = [12345]

        result = client.read_word("D100")

        assert result == 12345
        mock_plc.batchread_wordunits.assert_called_once_with(headdevice="D100", readsize=1)

    def test_write_word(self) -> None:
        """write_word should call batchwrite_wordunits."""
        client, mock_plc = self._make_connected_client()

        client.write_word("D100", 42)
        mock_plc.batchwrite_wordunits.assert_called_once_with(headdevice="D100", values=[42])

    def test_write_words(self) -> None:
        """write_words should call batchwrite_wordunits with multiple values."""
        client, mock_plc = self._make_connected_client()

        client.write_words("D100", [10, 20, 30])
        mock_plc.batchwrite_wordunits.assert_called_once_with(
            headdevice="D100", values=[10, 20, 30]
        )

    def test_write_float(self) -> None:
        """write_float should pack IEEE 754 and write 2 words."""
        client, mock_plc = self._make_connected_client()

        client.write_float("D100", 1.5)

        packed = struct.pack("<f", 1.5)
        word_lo = int.from_bytes(packed[0:2], "little")
        word_hi = int.from_bytes(packed[2:4], "little")

        mock_plc.batchwrite_wordunits.assert_called_once_with(
            headdevice="D100", values=[word_lo, word_hi]
        )

    def test_read_when_disconnected_raises(self) -> None:
        """Operations when disconnected should raise PLCConnectionError."""
        client = SLMPPLCClient()
        assert client.is_connected() is False

        with pytest.raises(PLCConnectionError):
            client.read_bit("M100")

    def test_comm_error_marks_disconnected(self) -> None:
        """Communication error should mark client as disconnected."""
        client, mock_plc = self._make_connected_client()
        mock_plc.batchread_bitunits.side_effect = RuntimeError("comm failed")

        with pytest.raises(PLCError):
            client.read_bit("M100")

        assert client.is_connected() is False
