"""Judgment service — computes OK/NG verdicts from measurement readings."""

from loguru import logger

from n1700_bridge.core.models import (
    JudgmentGroup,
    PortReading,
    Threshold,
    Verdict,
)


class JudgmentService:
    """Computes OK/NG judgments for measurement readings.

    A group is OK if and only if ALL ports in it are within their thresholds.
    Default grouping: 3-3-3 (ports 1-3, 4-6, 7-9).
    """

    # TODO(client-Q1.4): Confirm 3-3-3 grouping with client.

    def __init__(
        self,
        thresholds: list[Threshold],
        grouping: list[tuple[int, int, int]],
    ) -> None:
        self._thresholds = {t.port: t for t in thresholds}
        self._grouping = grouping

    def judge(self, readings: list[PortReading]) -> list[JudgmentGroup]:
        """Compute OK/NG for each group of ports.

        Args:
            readings: List of 9 port readings.

        Returns:
            List of JudgmentGroup, one per group.
        """
        readings_map = {r.port: r.value for r in readings}
        results: list[JudgmentGroup] = []

        for group_ports in self._grouping:
            all_ok = True
            for port in group_ports:
                value = readings_map.get(port)
                threshold = self._thresholds.get(port)

                if value is None or threshold is None:
                    all_ok = False
                    continue

                if not (threshold.lower <= value <= threshold.upper):
                    all_ok = False

            verdict = Verdict.OK if all_ok else Verdict.NG
            group = JudgmentGroup(ports=group_ports, verdict=verdict)
            results.append(group)

            logger.debug(
                "Group {} verdict: {} (ports: {})",
                group_ports,
                verdict.value,
                {p: readings_map.get(p) for p in group_ports},
            )

        return results
