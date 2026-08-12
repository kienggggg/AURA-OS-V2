from core.schemas import ToolResult

def tool_factorial(**params) -> ToolResult:
    try:
        n = params.get("n")
        if n is None:
            return ToolResult.failure("math.factorial", "Tham số 'n' là bắt buộc.")
        
        n = int(n)
        if n < 0:
            return ToolResult.failure("math.factorial", "Tham số 'n' phải là số nguyên không âm.")
        
        factorial = 1
        for i in range(1, n + 1):
            factorial *= i
        
        return ToolResult.success("math.factorial", f"Giai thừa của {n} là {factorial}")
    except ValueError:
        return ToolResult.failure("math.factorial", "Tham số 'n' phải là một số nguyên.")
    except Exception as exc:
        return ToolResult.failure("math.factorial", str(exc))