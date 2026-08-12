from core.schemas import ToolResult
def tool_nth_prime(**params) -> ToolResult:
    try:
        n = int(params.get("n", 0))
        if n < 1:
            return ToolResult.failure("math.nth_prime", "n phải là số nguyên >= 1")
        count, num = 0, 1
        while count < n:
            num += 1
            if all(num % d for d in range(2, int(num ** 0.5) + 1)):
                count += 1
        return ToolResult.success("math.nth_prime", f"Số nguyên tố thứ {n} là {num}")
    except Exception as exc:
        return ToolResult.failure("math.nth_prime", str(exc))