from core.schemas import ToolResult
import os
import requests
import psutil

def tool_download_video(**params) -> ToolResult:
    try:
        url = params.get("url")
        output_path = params.get("output_path", "data/downloads/video.mp4")
        
        if not url:
            return ToolResult.failure("download.video", "URL không được để trống")
        
        # Kiểm tra RAM khả dụng trước khi tải
        mem = psutil.virtual_memory()
        if mem.available < 500 * 1024 * 1024:  # Dưới 500MB RAM khả dụng
            return ToolResult.failure("download.video", "RAM không đủ để tải video, cần ít nhất 500MB RAM trống")
        
        # Tạo thư mục nếu chưa tồn tại
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Tải video
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        return ToolResult.success("download.video", f"Video đã được tải về: {output_path}")
    except Exception as exc:
        return ToolResult.failure("download.video", str(exc))