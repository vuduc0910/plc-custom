import ast
import math
import operator
from typing import Any

_ALLOWED_OPERATORS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_ALLOWED_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "max": max,
    "min": min,
    "sqrt": math.sqrt,
}

_MAX_FORMULA_LENGTH = 500


class FormulaError(Exception):
    pass


class FormulaEvaluator:

    @staticmethod
    def evaluate(formula: str, port_values: dict[int, float]) -> float:
        if len(formula) > _MAX_FORMULA_LENGTH:
            raise FormulaError(f"Formula too long ({len(formula)} chars)")

        variables = {f"p{k}": v for k, v in port_values.items()}

        try:
            tree = ast.parse(formula, mode="eval")
        except SyntaxError as e:
            raise FormulaError(f"Syntax error: {e}") from e

        return _eval_node(tree.body, variables)

    @staticmethod
    def validate(formula: str) -> str | None:
        if not formula.strip():
            return "Formula is empty"
        if len(formula) > _MAX_FORMULA_LENGTH:
            return f"Formula too long ({len(formula)} chars)"
        try:
            tree = ast.parse(formula, mode="eval")
        except SyntaxError as e:
            return f"Syntax error: {e}"

        try:
            _check_node_safety(tree.body)
        except FormulaError as e:
            return str(e)

        return None


def _eval_node(node: ast.AST, variables: dict[str, float]) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise FormulaError(f"Unsupported constant: {node.value!r}")

    if isinstance(node, ast.Name):
        if node.id in variables:
            return variables[node.id]
        raise FormulaError(f"Unknown variable: {node.id}")

    if isinstance(node, ast.BinOp):
        op_func = _ALLOWED_OPERATORS.get(type(node.op))
        if op_func is None:
            raise FormulaError(f"Unsupported operator: {type(node.op).__name__}")
        left = _eval_node(node.left, variables)
        right = _eval_node(node.right, variables)
        try:
            return float(op_func(left, right))
        except ZeroDivisionError:
            raise FormulaError("Division by zero") from None

    if isinstance(node, ast.UnaryOp):
        op_func = _ALLOWED_OPERATORS.get(type(node.op))
        if op_func is None:
            raise FormulaError(f"Unsupported operator: {type(node.op).__name__}")
        val = _eval_node(node.operand, variables)
        return float(op_func(val))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise FormulaError("Only simple function calls allowed")
        func = _ALLOWED_FUNCTIONS.get(node.func.id)
        if func is None:
            raise FormulaError(f"Unknown function: {node.func.id}")
        args = [_eval_node(arg, variables) for arg in node.args]
        try:
            return float(func(*args))
        except Exception as e:
            raise FormulaError(f"Function error: {e}") from e

    raise FormulaError(f"Unsupported expression: {type(node).__name__}")


def _check_node_safety(node: ast.AST) -> None:
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise FormulaError(f"Only numbers allowed, got: {type(node.value).__name__}")
        return

    if isinstance(node, ast.Name):
        if not node.id.startswith("p") or not node.id[1:].isdigit():
            if node.id not in _ALLOWED_FUNCTIONS:
                raise FormulaError(f"Unknown variable: {node.id}")
        return

    if isinstance(node, ast.BinOp):
        if type(node.op) not in _ALLOWED_OPERATORS:
            raise FormulaError(f"Unsupported operator: {type(node.op).__name__}")
        _check_node_safety(node.left)
        _check_node_safety(node.right)
        return

    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in _ALLOWED_OPERATORS:
            raise FormulaError(f"Unsupported operator: {type(node.op).__name__}")
        _check_node_safety(node.operand)
        return

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise FormulaError("Only simple function calls allowed")
        if node.func.id not in _ALLOWED_FUNCTIONS:
            raise FormulaError(f"Unknown function: {node.func.id}")
        for arg in node.args:
            _check_node_safety(arg)
        return

    raise FormulaError(f"Unsupported expression: {type(node).__name__}")
