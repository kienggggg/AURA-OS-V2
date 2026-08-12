from core.schemas import ToolResult

def tool_is_prime(**params) -> ToolResult:
    try:
        n = params.get("n")
        if n is None:
            return ToolResult.failure("math.is_prime", "Tham số 'n' là bắt buộc.")
        
        n = int(n)
        if n < 2:
            return ToolResult.failure("math.is_prime", "Số phải lớn hơn hoặc bằng 2 để kiểm tra số nguyên tố.")
        
        for i in range(2, int(n ** 0.5) + 1):
            if n % i == 0:
                return ToolResult.success("math.is_prime", f"{n} không phải là số nguyên tố.")
        
        return ToolResult.success("math.is_prime", f"{n} là số nguyên tố.")
    except ValueError:
        return ToolResult.failure("math.is_prime", "Tham số 'n' phải là một số nguyên hợp lệ.")
    except Exception as exc:
        return ToolResult.failure("math.is_prime", str(exc))