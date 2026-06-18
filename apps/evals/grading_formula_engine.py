"""Safe evaluation of tenant-configured grading formulas (no arbitrary code exec)."""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass
from typing import Any

_ALLOWED_NAMES = frozenset(
    {
        "min",
        "max",
        "round",
        "abs",
        "sum",
        "len",
        "pow",
        "sqrt",
        "floor",
        "ceil",
    }
)
_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow)
_ALLOWED_UNARY = (ast.UAdd, ast.USub)
_VAR_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class GradingFormulaError(ValueError):
    pass


@dataclass(frozen=True)
class GradingFormulaResult:
    value: float
    scale_key: str
    formula_text: str


def _safe_eval_node(node: ast.AST, variables: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body, variables)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise GradingFormulaError(f"unknown variable: {node.id}")
        return float(variables[node.id])
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
        left = _safe_eval_node(node.left, variables)
        right = _safe_eval_node(node.right, variables)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise GradingFormulaError("division by zero")
            return left / right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            return pow(left, right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, _ALLOWED_UNARY):
        val = _safe_eval_node(node.operand, variables)
        return val if isinstance(node.op, ast.UAdd) else -val
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
        if name not in _ALLOWED_NAMES:
            raise GradingFormulaError(f"function not allowed: {name}")
        args = [_safe_eval_node(arg, variables) for arg in node.args]
        if name == "sqrt":
            return math.sqrt(args[0])
        if name == "floor":
            return float(math.floor(args[0]))
        if name == "ceil":
            return float(math.ceil(args[0]))
        if name == "sum":
            return float(sum(args))
        if name == "len":
            return float(len(args[0]))  # type: ignore[arg-type]
        if name == "round":
            return float(round(args[0], int(args[1]) if len(args) > 1 else 0))
        fn = {"min": min, "max": max, "abs": abs, "pow": pow, "sum": sum, "len": len}.get(name)
        if fn is None:
            raise GradingFormulaError(f"function not allowed: {name}")
        return float(fn(*args))
    raise GradingFormulaError(f"unsupported expression node: {type(node).__name__}")


def evaluate_grading_formula(
    *,
    formula_text: str,
    variables: dict[str, float],
    scale_key: str = "custom",
) -> GradingFormulaResult:
    """Evaluate a plain-text formula with numeric variables only."""
    text = (formula_text or "").strip()
    if not text:
        raise GradingFormulaError("empty formula")
    if len(text) > 512:
        raise GradingFormulaError("formula too long")
    for key in variables:
        if not _VAR_PATTERN.match(key):
            raise GradingFormulaError(f"invalid variable name: {key}")

    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise GradingFormulaError(f"syntax error: {exc}") from exc

    value = _safe_eval_node(tree, variables)
    if not math.isfinite(value):
        raise GradingFormulaError("non-finite result")
    return GradingFormulaResult(value=value, scale_key=scale_key, formula_text=text)


# Preset formulas stored as plain text (wizard / GradingScale metadata).
PRESET_GRADING_FORMULAS: dict[str, str] = {
    "francophone_0_20": "min(20, max(0, (exam * 0.6 + coursework * 0.4)))",
    "uk_gcse_points": "round(exam * 0.5 + coursework * 0.5)",
    "us_gpa_4": "min(4.0, max(0.0, (exam / 25.0) * 4.0))",
    "waec_aggregate": "round((exam + coursework) / 2)",
}
