"""Built-in tool: calculator — basic arithmetic evaluation.

TOOLS_MCP_SPEC §5: calculator | tool | 算术计算 | F10
"""

from __future__ import annotations

import operator
from typing import Any, Union

from app.core.errors import (
    ERROR_CODE_VALIDATION,
    make_error,
)


_OPERATORS: dict[str, Any] = {
    "add": operator.add,
    "sub": operator.sub,
    "mul": operator.mul,
    "div": operator.truediv,
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
}


async def calculator(
    operation: str,
    a: Union[int, float],
    b: Union[int, float],
) -> float:
    """Evaluate a basic arithmetic operation.

    Supported operations: add/+  sub/-  mul/*  div/
    """
    op_fn = _OPERATORS.get(operation)
    if op_fn is None:
        raise make_error(
            ERROR_CODE_VALIDATION,
            f"Unknown operation '{operation}'. Supported: {', '.join(sorted(_OPERATORS))}",
        )

    if operation in ("div", "/") and b == 0:
        raise make_error(
            ERROR_CODE_VALIDATION,
            "Division by zero",
        )

    return float(op_fn(a, b))
