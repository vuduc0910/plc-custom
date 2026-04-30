"""Tests for JudgmentService."""

from n1700_bridge.core.models import PortReading, Threshold, Verdict
from n1700_bridge.services.judgment_service import JudgmentService


def _make_thresholds(lower: float = -0.05, upper: float = 0.05) -> list[Threshold]:
    """Create thresholds for all 9 ports with the same range."""
    return [Threshold(port=i, lower=lower, upper=upper) for i in range(1, 10)]


def _make_readings(values: list[float]) -> list[PortReading]:
    """Create readings for ports 1..9."""
    return [PortReading(port=i + 1, value=v) for i, v in enumerate(values)]


DEFAULT_GROUPING: list[tuple[int, int, int]] = [(1, 2, 3), (4, 5, 6), (7, 8, 9)]


class TestJudgmentService:
    """Tests for JudgmentService.judge()."""

    def test_all_ok_within_threshold(self) -> None:
        """All values within threshold -> all groups OK."""
        svc = JudgmentService(_make_thresholds(), DEFAULT_GROUPING)
        readings = _make_readings([0.01, -0.02, 0.03, 0.01, -0.01, 0.02, 0.00, 0.01, -0.01])
        result = svc.judge(readings)

        assert len(result) == 3
        for group in result:
            assert group.verdict == Verdict.OK

    def test_one_port_ng_fails_group(self) -> None:
        """One port exceeding threshold makes its group NG."""
        svc = JudgmentService(_make_thresholds(), DEFAULT_GROUPING)
        # Port 2 exceeds upper threshold
        readings = _make_readings([0.01, 0.10, 0.03, 0.01, -0.01, 0.02, 0.00, 0.01, -0.01])
        result = svc.judge(readings)

        assert result[0].verdict == Verdict.NG  # Group 1 (ports 1,2,3)
        assert result[1].verdict == Verdict.OK  # Group 2 (ports 4,5,6)
        assert result[2].verdict == Verdict.OK  # Group 3 (ports 7,8,9)

    def test_all_ng(self) -> None:
        """All ports exceed threshold -> all groups NG."""
        svc = JudgmentService(_make_thresholds(), DEFAULT_GROUPING)
        readings = _make_readings([0.1, -0.1, 0.2, -0.2, 0.1, -0.1, 0.2, -0.2, 0.1])
        result = svc.judge(readings)

        for group in result:
            assert group.verdict == Verdict.NG

    def test_boundary_values(self) -> None:
        """Values exactly at threshold boundaries are OK."""
        svc = JudgmentService(_make_thresholds(), DEFAULT_GROUPING)
        readings = _make_readings([0.05, -0.05, 0.05, -0.05, 0.05, -0.05, 0.05, -0.05, 0.05])
        result = svc.judge(readings)

        for group in result:
            assert group.verdict == Verdict.OK

    def test_below_lower_threshold(self) -> None:
        """Value below lower threshold -> NG."""
        svc = JudgmentService(_make_thresholds(), DEFAULT_GROUPING)
        readings = _make_readings([0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, -0.06])
        result = svc.judge(readings)

        assert result[0].verdict == Verdict.OK
        assert result[1].verdict == Verdict.OK
        assert result[2].verdict == Verdict.NG  # Port 9 fails

    def test_correct_group_ports(self) -> None:
        """Verify groups contain correct port tuples."""
        svc = JudgmentService(_make_thresholds(), DEFAULT_GROUPING)
        readings = _make_readings([0.0] * 9)
        result = svc.judge(readings)

        assert result[0].ports == (1, 2, 3)
        assert result[1].ports == (4, 5, 6)
        assert result[2].ports == (7, 8, 9)

    def test_custom_grouping(self) -> None:
        """Custom grouping should be respected."""
        custom = [(1, 4, 7), (2, 5, 8), (3, 6, 9)]
        svc = JudgmentService(_make_thresholds(), custom)
        # Only port 1 fails
        readings = _make_readings([0.10, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01])
        result = svc.judge(readings)

        assert result[0].verdict == Verdict.NG  # Group with port 1
        assert result[1].verdict == Verdict.OK
        assert result[2].verdict == Verdict.OK

    def test_missing_threshold_for_port(self) -> None:
        """Missing threshold for a port -> group is NG."""
        # Only thresholds for ports 1-6
        thresholds = [Threshold(port=i, lower=-0.05, upper=0.05) for i in range(1, 7)]
        svc = JudgmentService(thresholds, DEFAULT_GROUPING)
        readings = _make_readings([0.0] * 9)
        result = svc.judge(readings)

        assert result[0].verdict == Verdict.OK
        assert result[1].verdict == Verdict.OK
        assert result[2].verdict == Verdict.NG  # Ports 7,8,9 have no thresholds
