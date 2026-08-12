import subprocess
import logging
from pathlib import Path

from core.schemas import ToolResult
from core.config import PROJECT_ROOT

logger = logging.getLogger("aura.skill.terminal")

def tool_system_terminal(command: str, cwd: str = "") -> ToolResult:
    """
    Thực thi lệnh terminal và trả về kết quả raw.
    """
    if not command:
        return ToolResult.failure("system.terminal", "Lệnh rỗng.")
    
    target_cwd = Path(cwd) if cwd else PROJECT_ROOT
    if not target_cwd.exists() or not target_cwd.is_dir():
        return ToolResult.failure("system.terminal", f"Thư mục không tồn tại: {target_cwd}")
        
    logger.info("Chạy lệnh: [%s] tại cwd: [%s]", command, target_cwd)
    
    try:
        # Chạy lệnh
        result = subprocess.run(
            command,
            cwd=str(target_cwd),
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60
        )
        
        output = result.stdout.strip()
        err = result.stderr.strip()
        
        if result.returncode != 0:
            msg = f"Lệnh thất bại (mã {result.returncode}):\n{err}"
            if output:
                msg += f"\nSTDOUT:\n{output}"
            return ToolResult.failure("system.terminal", msg)
            
            
        formatted_output = f"```bash\n{command}\n{output}\n```" if output else "Lệnh chạy thành công, không có output."
        return ToolResult.success(
            tool_name="system.terminal",
            output=formatted_output
        )
        
    except subprocess.TimeoutExpired:
        return ToolResult.failure("system.terminal", "Lệnh chạy quá thời gian 60 giây (Timeout).")
    except Exception as exc:
        return ToolResult.failure("system.terminal", f"Lỗi thực thi: {exc}")
