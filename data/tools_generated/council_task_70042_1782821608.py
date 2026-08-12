from core.schemas import ToolResult
from datetime import datetime

def tool_days_to_target(**params) -> ToolResult:
    try:
        target_date_str = params.get('target_date')
        if not target_date_str:
            return ToolResult.failure('time.days_to_target', 'Thiếu tham số target_date')
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d')
        except ValueError:
            return ToolResult.failure('time.days_to_target', 'Định dạng target_date không đúng. Sử dụng YYYY-MM-DD')
        today = datetime.today()
        if target_date < today:
            return ToolResult.failure('time.days_to_target', 'Ngày mục tiêu không thể trước ngày hôm nay')
        days_left = (target_date - today).days
        return ToolResult.success('time.days_to_target', f'Còn {days_left} ngày đến {target_date_str}')
    except Exception as exc:
        return ToolResult.failure('time.days_to_target', str(exc))