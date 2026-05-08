from loguru import logger

from n1700_bridge.core.models import (
    FormulaGroupConfig,
    JudgmentGroup,
    PortReading,
    Verdict,
)
from n1700_bridge.services.formula_evaluator import FormulaError, FormulaEvaluator


class JudgmentService:

    def __init__(self, groups: list[FormulaGroupConfig]) -> None:
        self._groups = groups

    def judge(self, readings: list[PortReading]) -> list[JudgmentGroup]:
        readings_map = {r.port: r.value for r in readings}
        results: list[JudgmentGroup] = []

        for group_cfg in self._groups:
            try:
                computed = FormulaEvaluator.evaluate(
                    group_cfg.formula, readings_map,
                )
            except FormulaError as e:
                logger.error(
                    "Formula error for group {}: {}",
                    group_cfg.ports, e,
                )
                computed = 0.0

            is_ok = group_cfg.lower <= computed <= group_cfg.upper
            verdict = Verdict.OK if is_ok else Verdict.NG

            results.append(JudgmentGroup(
                ports=group_cfg.ports,
                formula=group_cfg.formula,
                computed_value=computed,
                verdict=verdict,
            ))

            logger.debug(
                "Group {} formula='{}' → {:.6f} [{}, {}] → {}",
                group_cfg.ports,
                group_cfg.formula,
                computed,
                group_cfg.lower,
                group_cfg.upper,
                verdict.value,
            )

        return results
