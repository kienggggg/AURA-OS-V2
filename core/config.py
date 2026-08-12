"""
core/config.py
==============
Cấu hình tập trung cho AURA 2.0. MỘT nơi duy nhất đọc biến môi trường / .env.

Triết lý:
- Không một module nào khác được phép gọi os.getenv() rải rác. Tất cả đi qua đây.
- Dùng pydantic-settings để vừa đọc .env, vừa validate kiểu, vừa có giá trị mặc định.
- TUYỆT ĐỐI không hard-code API key trong source (bài học từ key Google bị lộ).
  Key chỉ đến từ .env hoặc biến môi trường thật.

Cài đặt phụ thuộc:
    pip install pydantic-settings

Cách dùng ở các module khác:
    from core.config import settings
    model = settings.ollama_model
    api_key = settings.google_api_key.get_secret_value()  # khi thực sự cần
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Gốc dự án = thư mục cha của core/. Mọi đường dẫn data suy ra từ đây.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """
    Toàn bộ cấu hình runtime của AURA.

    Mỗi field map tới một biến môi trường (không phân biệt hoa thường nhờ
    case_sensitive=False). Ví dụ field `ollama_model` đọc từ `OLLAMA_MODEL`.
    SecretStr giúp key không bị in ra log khi lỡ print(settings).
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # bỏ qua biến môi trường lạ, không làm app crash
    )

    # --- System 1: Local brain (Ollama) ---
    ollama_host: str = Field(
        default="http://localhost:11434",
        description="Địa chỉ Ollama server cục bộ.",
    )
    ollama_model: str = Field(
        default="gemma4:e2b",
        description="Model local mặc định (ép cân ~1.6GB cho máy 12GB RAM; pull: ollama pull gemma4:e2b).",
    )
    ollama_timeout_s: float = Field(
        default=1000.0, gt=0, description="Timeout mỗi request tới Ollama (giây)."
    )
    chat_turn_budget_s: float = Field(
        default=90.0,
        ge=0,
        description=(
            "Trần thời gian cho MỘT lượt chat (giây). Từng backend có hạn giờ riêng "
            "nhưng cả đường đi thì không: local gục -> cloud -> lập lại kế hoạch, cộng "
            "dồn thành treo vô hạn (đo được 500s vẫn chưa trả về). Quá hạn thì AURA "
            "trả lời thật thà thay vì im lặng. Đặt 0 để tắt trần."
        ),
    )
    ollama_keep_alive: str = Field(
        default="0",
        description=(
            "Thời gian Ollama GIỮ model trong RAM sau khi trả lời xong. "
            "'0' = nhả ngay 9.6GB (mặc định cho máy 12GB RAM); "
            "'5m'/'1h' = giữ lâu hơn; '-1' = giữ mãi. "
            "Gửi kèm mỗi request (thắng cả default của server)."
        ),
    )

    # --- System 2: Cloud brain (Claude) ---
    anthropic_api_key: SecretStr | None = Field(
        default=None, description="API key Anthropic cho tác vụ suy luận sâu."
    )
    cloud_model: str = Field(
        default="claude-sonnet-4-6",
        description="Model cloud cho coding / heavy reasoning.",
    )

    # --- System 2b: Cloud brain MIỄN PHÍ (OpenAI-compatible: Groq / Gemini / OpenRouter) ---
    # Bật bằng cách đặt cloud_provider=openai và điền openai_* dưới đây.
    cloud_provider: str = Field(
        default="claude",
        description="Nhà cung cấp cho CloudEngine: 'claude' (Anthropic) hoặc 'openai' "
        "(endpoint OpenAI-compatible như Groq/Gemini/OpenRouter).",
    )
    openai_api_key: SecretStr | None = Field(
        default=None,
        description="API key cho endpoint OpenAI-compatible (Groq/Gemini...). Free-tier OK.",
    )
    openai_base_url: str = Field(
        default="https://api.groq.com/openai/v1",
        description="Base URL OpenAI-compatible. Groq: https://api.groq.com/openai/v1 ; "
        "Gemini: https://generativelanguage.googleapis.com/v1beta/openai .",
    )
    openai_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Model trên endpoint OpenAI-compatible (vd Groq 'llama-3.3-70b-versatile', "
        "Gemini 'gemini-2.0-flash').",
    )
    # Tier cho Agent_Generator của Triad Council: 'local' | 'cloud' | 'auto'.
    council_generator_tier: str = Field(
        default="local",
        description="Generator của Triad Council chạy ở tier nào (local|cloud|auto). "
        "Đặt 'cloud' để mở khoá codegen khi đã cắm não cloud free.",
    )

    # --- Manga / web scraping ---
    google_api_key: SecretStr | None = Field(
        default=None, description="Key Google (nếu còn dùng cho dịch vụ phụ trợ)."
    )
    manga_proxy: str | None = Field(
        default=None, description="Proxy đơn cho scraper, vd http://user:pass@host:port."
    )

    # --- Memory (ChromaDB) ---
    chroma_path: Path = Field(
        default=PROJECT_ROOT / "data" / "chroma",
        description="Thư mục lưu ChromaDB persistent.",
    )
    chroma_collection: str = Field(
        default="quangia_memory", description="Tên collection ký ức."
    )
    memory_recall_k: int = Field(
        default=5, ge=1, le=50, description="Số ký ức gần nhất lấy ra mỗi lần recall."
    )
    # --- Trí nhớ biết chọn (core/recall.py — HyDE + Self-RAG, đợt sàng 06/08/2026) ---
    recall_smart_enabled: bool = Field(
        default=True,
        description="Bật cổng [Retrieve] + lọc ký ức lạc đề. Tắt: RECALL_SMART_ENABLED=false.",
    )
    recall_hyde_enabled: bool = Field(
        default=False,
        description="HyDE: bảo LLM viết câu trả lời giả rồi đem đi tìm. Khớp tốt hơn "
                    "nhưng TỐN THÊM 1 lượt gọi LLM mỗi lần recall — mặc định TẮT.",
    )
    recall_max_distance: float = Field(
        default=1.20, ge=0.0, le=2.0,
        description="Ngưỡng loại ký ức lạc đề (ChromaDB: nhỏ = giống). Để RỘNG; "
                    "hạ xuống nếu AURA hay nhớ nhầm chuyện không liên quan.",
    )

    # --- Daemon ---
    sensor_interval_s: float = Field(
        default=5.0, gt=0, description="Chu kỳ quét sensors (thư mục, RAM) — giây."
    )
    ws_host: str = Field(default="localhost", description="Host WebSocket nói với mascot desktop.")
    ws_port: int = Field(default=8765, ge=1, le=65535, description="Cổng WebSocket.")
    ram_yield_threshold: float = Field(
        default=0.85, gt=0.0, le=1.0,
        description=(
            "Ngưỡng RAM hệ thống (0..1). Vượt ngưỡng -> tác vụ ngầm (tin tức, "
            "trưởng thành) 'ngủ đông' nhường RAM cho Sếp. Mặc định 0.85 = 85%."
        ),
    )
    ram_recheck_s: float = Field(
        default=300.0, gt=0,
        description="Khi đang ngủ đông vì RAM cao, bao lâu (giây) dò lại một lần.",
    )

    # --- Health Guard (ép nghỉ kỷ luật) ---
    health_enabled: bool = Field(default=True, description="Bật Health Guard ép nghỉ.")
    health_work_limit_min: float = Field(
        default=50.0, gt=0, description="Ngồi liên tục bao nhiêu PHÚT thì ép nghỉ."
    )
    health_break_min: float = Field(
        default=5.0, gt=0, description="Thời lượng KHOÁ màn hình (phút, đồng hồ đếm ngược)."
    )
    health_busy_delay_min: float = Field(
        default=30.0, gt=0, description="Hoãn ép nghỉ thêm bao nhiêu PHÚT khi đang render nặng."
    )
    health_tick_s: float = Field(
        default=60.0, gt=0, description="Nhịp đếm thời gian của Health Guard (giây)."
    )
    # Ép nghỉ CẢ điện thoại Android (tắt màn hình qua ADB) khi tới giờ nghỉ.
    phone_sleep_on_break: bool = Field(
        default=False,
        description="Tới giờ ép nghỉ thì tắt luôn màn hình điện thoại Android qua ADB "
        "(cần bật USB debugging + cắm/adb-wifi). Bật bằng PHONE_SLEEP_ON_BREAK=true."
    )
    adb_path: str = Field(
        default="adb",
        description="Đường dẫn tới adb.exe (nếu không nằm trên PATH). Điền ADB_PATH trong .env."
    )
    adb_connect: str = Field(
        default="",
        description="Địa chỉ WiFi của điện thoại 'ip:port' (vd 192.168.1.50:5555) để ADB "
        "KHÔNG DÂY. Rỗng = chỉ dùng USB. AURA tự `adb connect` trước mỗi lần tắt màn."
    )
    phone_sleep_repeat_s: float = Field(
        default=45.0, gt=0,
        description="Trong ca nghỉ, cứ ngần này giây lại tắt màn hình ĐT một lần (chống bật lại)."
    )

    # --- QUẢN LÝ GIỜ MÀN HÌNH (30/07/2026) ---
    # Khác Health Guard: Health Guard đo giờ NGỒI LIÊN TỤC rồi khoá màn 5 phút;
    # cái này đo TỔNG giờ màn hình sáng CẢ NGÀY (laptop + điện thoại) và phạt nặng
    # hơn — tắt máy. Tắt máy là hành động PHÁ HUỶ nên mặc định KHÔNG cưỡng chế.
    screen_time_enabled: bool = Field(
        default=True,
        description="Đếm giờ màn hình sáng mỗi ngày (laptop + điện thoại). Chỉ đếm và báo.",
    )
    screen_time_enforce: bool = Field(
        default=False,
        description=(
            "CƯỠNG CHẾ TẮT MÁY khi quá hạn. Mặc định TẮT vì có thể mất việc chưa lưu. "
            "Bật bằng SCREEN_TIME_ENFORCE=true khi Sếp thật sự muốn bị ép."
        ),
    )
    screen_time_daily_limit_min: float = Field(
        default=480.0, gt=0,
        description="Hạn giờ màn hình mỗi ngày (phút). 480 = 8 tiếng.",
    )
    screen_time_shutdown_delay_min: int = Field(
        default=5, ge=1, le=60,
        description=(
            "Đếm ngược bao nhiêu PHÚT trước khi tắt máy — phải đủ dài để Sếp lưu việc. "
            "Huỷ khẩn bằng lệnh: shutdown /a"
        ),
    )
    screen_time_tick_s: float = Field(
        default=60.0, gt=0, description="Nhịp đo giờ màn hình (giây)."
    )

    # --- Nhịp sinh học: Briefing sáng / Review tối (giờ local) ---
    briefing_time: str = Field(default="08:00", description="Mốc Briefing sáng (HH:MM).")
    review_time: str = Field(default="21:00", description="Mốc Review tối (HH:MM).")
    briefing_catchup_min: float = Field(
        default=180.0, gt=0,
        description="Khung bắt-kịp (phút) sau mốc: máy bật trễ trong khung này vẫn chạy bù."
    )
    briefing_poll_s: float = Field(
        default=60.0, gt=0, description="Nhịp dò giờ của bộ briefing (giây)."
    )
    briefing_allow_cloud: bool = Field(
        default=True,
        description="Cho briefing/review TỰ gọi Cloud (pre-approve, không hỏi Y mỗi sáng)."
    )
    briefing_cloud_daily_cap: int = Field(
        default=2, ge=0, le=20,
        description="Trần số lần gọi Cloud/ngày cho briefing (kiểm soát chi phí; 2 = sáng+tối)."
    )
    briefing_persona: str = Field(
        default="alpha",
        description="Giọng báo cáo: 'alpha' (đanh đá, mỏ hỗn) hoặc 'gentle' (hiền, thân tình)."
    )
    briefing_scan_jobs: bool = Field(
        default=True, description="Briefing sáng có quét job.scout (cơ hội ra tiền) không."
    )
    job_keywords: str | None = Field(
        default=None, description="Từ khoá chấm điểm job 'kw:trọng,kw' (rỗng = bộ mặc định của Sếp)."
    )
    job_urls: str | None = Field(
        default=None, description="URL tuyển dụng, phân tách dấu phẩy (rỗng = bộ URL mẫu)."
    )
    # Hồ sơ freelance để cloud SOẠN PITCH đúng người. Cloud KHÔNG được bịa ngoài
    # hồ sơ này.
    #
    # 12/08/2026: mặc định từng ghi sẵn tỉnh đang ở và bộ kỹ năng thật của Sếp.
    # Đã gỡ khi soi bản đẩy lên GitHub — ghép với `scout_keywords` cũ thì đọc ra
    # người này ở đâu, có chứng chỉ gì, đang tìm việc gì. Bí mật thì đổi được,
    # chỗ ở và nghề nghiệp thì không. Điền vào `.env` (FREELANCE_PROFILE).
    freelance_profile: str = Field(
        default=(
            "Freelancer. Thành thạo Python: tự động hoá, crawl/scrape dữ liệu, "
            "viết script/tool nhỏ. Biết dựng video: chỉnh sửa, làm phụ đề. "
            "Nhận việc remote, giao đúng hạn, giao tiếp rõ ràng."
        ),
        description="Hồ sơ ngắn để cloud viết thư ứng tuyển/pitch (kỹ năng, kinh nghiệm, nơi ở, giá)."
    )
    # TỰ SOẠN HỒ SƠ: scout thấy việc THẬT hợp -> tự chạy freelance.apply (pitch sẵn)
    # -> Sếp chỉ mở VIỆC_HÔM_NAY.md là gửi được (diệt ma sát "lười không nhấn link").
    job_auto_apply: bool = Field(
        default=True,
        description="Scout thấy tin việc thật đủ điểm thì tự soạn bộ hồ sơ ứng tuyển. "
                    "JOB_AUTO_APPLY=false để tắt."
    )
    job_auto_apply_threshold: float = Field(
        default=0.72, ge=0, le=1,
        description="Điểm tối thiểu để tự soạn hồ sơ (chỉ áp cho tin việc THẬT, không phải bài báo)."
    )
    job_auto_apply_per_scan: int = Field(
        default=2, ge=1, le=5, description="Mỗi lượt quét tự soạn tối đa mấy bộ hồ sơ."
    )
    freelance_autopilot_enabled: bool = Field(
        default=True,
        description="Bật nhịp tự động quét việc freelance, tạo demo & soạn hồ sơ."
    )
    freelance_auto_demo_enabled: bool = Field(
        default=True,
        description="Tự động tạo sản phẩm mẫu (Demo) đính kèm hồ sơ ứng tuyển."
    )
    freelance_auto_apply_threshold: float = Field(
        default=0.70, ge=0, le=1,
        description="Điểm mốc (0..1) để tự tạo demo và ứng tuyển."
    )

    # --- Work-for-hire: kiếm tiền từ việc thuê thật, không chạy theo kho nội dung ---
    work_for_hire_mode_enabled: bool = Field(
        default=True,
        description=(
            "Ưu tiên pipeline nhận việc: săn tin thật → soạn hồ sơ → Sếp tự gửi → "
            "theo dõi tới khi đã nhận tiền. Khi bật, tạm dừng autopilot tự sản xuất "
            "truyện/video để CPU và sự chú ý tập trung cho việc thuê."
        ),
    )
    work_for_hire_pause_content_autopilot: bool = Field(
        default=True,
        description="Trong Work-for-hire mode, không tự đẩy job viết truyện/video/sách tô màu mới.",
    )
    work_for_hire_min_fit: int = Field(
        default=75, ge=0, le=100,
        description="Chỉ đưa hồ sơ có điểm hợp từ mức này lên hàng Sếp cần duyệt.",
    )
    work_for_hire_daily_draft_cap: int = Field(
        default=3, ge=1, le=10,
        description="Trần số bộ hồ sơ AURA tự soạn mỗi ngày để ưu tiên chất lượng.",
    )
    work_for_hire_manual_send_only: bool = Field(
        default=True,
        description=(
            "Luôn để người thật tự gửi đơn, ký hợp đồng, xác nhận bàn giao và xác nhận tiền. "
            "AURA chỉ chuẩn bị hồ sơ/deliverable và theo dõi pipeline."
        ),
    )

    # --- One-percent owner: AURA vận hành bán sản phẩm số sau một lần chủ xác thực payout ---
    one_percent_operator_enabled: bool = Field(
        default=True,
        description=(
            "Bật nhịp kiểm tra kênh bán 1% Chủ / 99% AURA. Trước khi Chủ xác nhận đã nối "
            "Payhip+payout, nhịp này chỉ báo điều kiện còn thiếu và không đăng gì ra ngoài."
        ),
    )
    one_percent_run_interval_h: float = Field(
        default=6.0, gt=0.0, le=72.0,
        description="Bao lâu AURA kiểm tra/vận hành kênh sản phẩm số một lần (giờ).",
    )
    one_percent_daily_publish_cap: int = Field(
        default=1, ge=1, le=5,
        description="Số sản phẩm số nguyên gốc tối đa AURA công khai mỗi ngày trên Payhip.",
    )
    one_percent_product_price_usd: float = Field(
        default=3.99, gt=0.0, le=999.0,
        description="Giá USD mặc định khi AURA đăng sản phẩm số Payhip.",
    )

    # --- Revenue Operator: chuẩn bị lead + tài sản cục bộ, không tự gửi đề xuất ---
    revenue_operator_enabled: bool = Field(
        default=True,
        description=(
            "Bật nhịp chuẩn bị lead và demo Growth Operator. Nhịp này không tự gửi đề xuất, "
            "không tự đăng bài và không tự xác nhận doanh thu."
        ),
    )
    revenue_operator_interval_h: float = Field(
        default=24.0, gt=0.0, le=168.0,
        description="Khoảng cách tối thiểu giữa hai chu kỳ Revenue Operator (giờ).",
    )
    revenue_operator_poll_interval_min: float = Field(
        default=15.0, ge=1.0, le=120.0,
        description="Tần suất daemon kiểm tra chu kỳ Revenue Operator đã đến hạn hay chưa (phút).",
    )
    revenue_operator_target_count: int = Field(
        default=20, ge=1, le=100,
        description="Số lead công khai tối đa cần chuẩn bị trong mỗi chu kỳ.",
    )

    # Tình báo tĩnh lặng (skills/scouts/job_scout.py)
    freelance_urls: str | None = Field(
        default=None, description="URL/RSS nguồn FREELANCE (kiếm tiền), phân tách dấu phẩy."
    )
    pedagogy_urls: str | None = Field(
        default=None, description="URL/RSS nguồn SỰ NGHIỆP (việc ổn định + chứng chỉ), phân tách dấu phẩy."
    )
    scout_keywords: str = Field(
        default="Python, automation, crawl data, video editor",
        description="Bộ từ khoá cốt lõi để LLM chấm độ phù hợp cơ hội. "
                    "Đặt SCOUT_KEYWORDS trong .env cho đúng nghề của bạn."
    )
    scout_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Ngưỡng lọc rác: bỏ tin có điểm < ngưỡng này."
    )
    scout_local_only: bool = Field(
        default=True,
        description="Bỏ tin việc CHỈ tuyển người ở nước ngoài (vd 'US/Europe based only') — "
        "giữ việc remote-toàn-cầu và việc trong nước, vì việc buộc cư trú nước ngoài là ngõ cụt."
    )
    scout_priority_terms: str = Field(
        default="",
        description="Từ/cụm ĐỊA PHƯƠNG ưu tiên (CSV). Tin chứa các từ này được CỘNG điểm để "
                    "nổi lên top. RỖNG = tắt hẳn phần ưu tiên địa phương; đặt "
                    "SCOUT_PRIORITY_TERMS trong .env nếu muốn bật."
    )
    scout_priority_boost: float = Field(
        default=0.25, ge=0.0, le=1.0,
        description="Mức cộng điểm cho tin chứa scout_priority_terms (0 = tắt). Giúp tin địa phương vượt tin cả nước."
    )
    scout_priority_min_base: float = Field(
        default=0.6, ge=0.0, le=1.0,
        description="CHỈ ưu tiên tin địa phương khi điểm NỀN (trước boost) >= mốc này — "
        "tránh kéo tin đúng địa phương nhưng lệch chủ đề (điểm thấp) lên top."
    )
    scout_use_jina: bool = Field(
        default=True, description="Cào thất bại -> thử lại qua Jina Reader (r.jina.ai, không cookie)."
    )
    # Calib điểm của công nhân embedding: cosine <= low -> 0.0, >= high -> 1.0.
    # Đây là "gen cấu hình" — vòng feedback sẽ tiến hoá 2 số này, KHÔNG đụng trọng số model.
    # Đo thực tế 2026-07: tiêu đề job KHỚP TỐT với chuỗi từ khoá ngắn chỉ đạt cosine
    # ~0.45-0.55 (không phải 0.7+ như cặp câu gần-trùng), tin rác ~0.25-0.30.
    scout_embed_low: float = Field(
        default=0.20, ge=-1.0, le=1.0,
        description="Mốc cosine coi là KHÔNG liên quan (điểm 0.0) khi chấm bằng công nhân embedding."
    )
    scout_embed_high: float = Field(
        default=0.55, ge=-1.0, le=1.0,
        description="Mốc cosine coi là RẤT liên quan (điểm 1.0) khi chấm bằng công nhân embedding."
    )
    scout_feedback_weight: float = Field(
        default=0.15, ge=0.0, le=0.5,
        description="Trọng số cộng/trừ điểm theo phản hồi của Sếp (tin giống tin đã khen +, giống tin đã chê -)."
    )
    # Calib RIÊNG cho news.scout: feed tin tức toàn bài "gần chủ đề" (đo 2026-07:
    # p50 cosine ~0.40, p90 ~0.58) nên phải gắt hơn job_scout kẻo cái gì cũng "hữu ích".
    news_embed_low: float = Field(
        default=0.35, ge=-1.0, le=1.0,
        description="Mốc cosine coi là KHÔNG hữu ích (điểm 0.0) khi công nhân embedding chấm tin tức."
    )
    news_embed_high: float = Field(
        default=0.85, ge=-1.0, le=1.0,
        description="Mốc cosine coi là RẤT hữu ích (điểm 1.0) khi công nhân embedding chấm tin tức."
    )

    # --- Công nhân (worker models: model nhỏ local gắn vào pipeline) ---
    worker_models_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "models",
        description="Thư mục cache model nhỏ của công nhân (ONNX, tải 1 lần từ HuggingFace)."
    )

    # --- Công nhân dọn rác (skills/janitor) ---
    janitor_enabled: bool = Field(
        default=True, description="Bật nhịp dọn rác ngầm (1 lần/ngày, Recycle Bin, hoàn tác được)."
    )
    janitor_rule_dirs: str | None = Field(
        default=None,
        description="Thư mục quét rác theo LUẬT (CSV). Rỗng = %TEMP% của Windows."
    )
    janitor_suggest_dirs: str | None = Field(
        default=None,
        description="Thư mục model ĐỀ XUẤT phân loại (CSV, không tự dọn). Rỗng = ~/Downloads."
    )
    janitor_min_age_days: float = Field(
        default=30.0, ge=1.0,
        description="Chỉ đụng file CŨ hơn ngần này ngày (vành đai an toàn số 1)."
    )
    janitor_max_recycle: int = Field(
        default=200, ge=1, le=5000,
        description="Trần số file đưa vào Recycle Bin mỗi lượt (vành đai an toàn số 2)."
    )

    # --- Tổ trưởng công nhân (core/crew.py) — nhịp 'tới hạn' mỗi công nhân (giờ) ---
    crew_job_interval_h: float = Field(
        default=24.0, gt=0, description="Bao lâu (giờ) job.scout mới tới hạn chạy lại trong tổ."
    )
    crew_news_interval_h: float = Field(
        default=8.0, gt=0, description="Bao lâu (giờ) news.scout mới tới hạn chạy lại trong tổ."
    )
    crew_janitor_interval_h: float = Field(
        default=24.0, gt=0, description="Bao lâu (giờ) trash.janitor mới tới hạn chạy lại trong tổ."
    )
    crew_radar_interval_h: float = Field(
        default=24.0, gt=0, description="Bao lâu (giờ) trend.radar mới tới hạn chạy lại trong tổ."
    )

    # --- Cấu hình đăng YouTube ---
    youtube_default_privacy: str = Field(
        default="public",
        description="Mặc định trạng thái đăng YouTube: 'public' (Công khai) hoặc 'unlisted' / 'private'.",
    )

    # --- Công nhân radar trend (skills/trend-radar) ---
    trend_sources: str | None = Field(
        default=None, description="Nguồn RSS trend (CSV). Rỗng = Google Trends theo geo + Hacker News."
    )
    trend_angle: str | None = Field(
        default=None, description="Góc riêng của Sếp để chấm độ hợp chủ đề (rỗng = giáo dục/Python/video)."
    )
    trend_geo: str = Field(default="VN", description="Mã quốc gia Google Trends (VN, US...).")
    trend_top: int = Field(default=5, ge=1, le=10, description="Số chủ đề đưa vào brief.")
    trend_use_cloud: bool = Field(
        default=False, description="Nhờ cloud viết brief (tốn lượt gọi). Tắt = khung mẫu offline."
    )
    trend_embed_low: float = Field(
        default=0.30, ge=-1.0, le=1.0, description="Mốc cosine coi là KHÔNG hợp góc (điểm 0)."
    )
    trend_embed_high: float = Field(
        default=0.68, ge=-1.0, le=1.0, description="Mốc cosine coi là RẤT hợp góc (điểm 1)."
    )
    trend_min_fit: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Chỉ đưa vào brief chủ đề có điểm hợp góc >= mốc này (lọc nhiễu giải trí/thể thao)."
    )

    # --- Connectors "Quản gia gánh việc" (CHỈ ĐỌC) ---
    calendar_ics_url: str | None = Field(
        default=None, description="URL .ics (Google Calendar secret link) để đọc sự kiện hôm nay."
    )
    gmail_user: str | None = Field(
        default=None, description="Địa chỉ Gmail để đọc email CHƯA ĐỌC (IMAP read-only)."
    )
    gmail_app_password: SecretStr | None = Field(
        default=None, description="App Password Gmail (KHÔNG phải mật khẩu chính). Lưu trong .env."
    )
    imap_host: str = Field(default="imap.gmail.com", description="Máy chủ IMAP.")
    email_unread_limit: int = Field(
        default=7, ge=1, le=30, description="Số email chưa đọc gần nhất kéo về cho briefing."
    )

    # --- Đường dẫn dữ liệu ---
    downloads_dir: Path = Field(default=PROJECT_ROOT / "data" / "downloads")
    outputs_dir: Path = Field(default=PROJECT_ROOT / "data" / "outputs")
    generated_tools_dir: Path = Field(default=PROJECT_ROOT / "data" / "tools_generated")

    # --- XƯỞNG KIẾM TIỀN (factory) — hàng đợi job + dashboard web ---
    factory_enabled: bool = Field(
        default=True, description="Bật vòng worker xưởng (1 job nặng/lúc) trong daemon."
    )
    factory_poll_s: float = Field(
        default=5.0, gt=0, description="Chu kỳ worker dò hàng đợi job (giây)."
    )
    factory_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "factory",
        description="Thư mục trạng thái xưởng: jobs.db (sqlite) + cache tải về."
    )
    ledger_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "ledger",
        description="Thư mục sổ sách tiền nong (income.jsonl)."
    )
    dashboard_host: str = Field(
        default="127.0.0.1",
        description="Địa chỉ bind dashboard web. GIỮ localhost — không mở ra mạng ngoài."
    )
    dashboard_port: int = Field(default=8766, description="Cổng dashboard web local.")
    dashboard_allow_lan: bool = Field(
        default=False,
        description=(
            "CHỐT AN TOÀN. Dashboard có ~30 route KHÔNG xác thực, trong đó có route "
            "bật/tắt điều khiển chuột+bàn phím (/api/desktop-autopilot/control). "
            "Thứ duy nhất che chúng là bind loopback. Nếu dashboard_host bị đổi sang "
            "địa chỉ ngoài mà cờ này vẫn False -> dashboard TỪ CHỐI khởi động. "
            "Chỉ đặt True khi Sếp CỐ Ý mở ra mạng và hiểu rủi ro."
        ),
    )
    income_currency: str = Field(default="VND", description="Đơn vị tiền mặc định của sổ thu nhập.")
    cashflow_voice_alert_enabled: bool = Field(
        default=False,
        description=(
            "Khi nguồn thông báo ngân hàng đã được kết nối báo có, AURA phát chuông/đọc số tiền "
            "qua loa mặc định của Windows. Không đọc tên người gửi hay số tài khoản."
        ),
    )
    cashflow_telegram_alert_enabled: bool = Field(
        default=True,
        description=(
            "Khi có báo có mới, AURA gửi tóm tắt qua Telegram của Chủ. Báo có vẫn chờ đối soát "
            "trước khi được cộng vào doanh thu."
        ),
    )
    cashflow_ingest_token: SecretStr | None = Field(
        default=None,
        description=(
            "Mã bí mật cho cầu nối thông báo ngân hàng/Android gửi báo có vào AURA. "
            "Không đặt thì AURA chỉ hiển thị sổ thủ công, không nhận báo có tự động."
        ),
    )

    # Donate QR (VietQR) — AURA chèn cuối mỗi chương truyện để độc giả quét chuyển thẳng.
    donate_bank_bin: str = Field(
        default="", description="Mã BIN ngân hàng (MB=970422). DONATE_BANK_BIN trong .env."
    )
    donate_bank_account: str = Field(
        default="", description="Số tài khoản nhận donate. DONATE_BANK_ACCOUNT trong .env."
    )
    donate_bank_name: str = Field(
        default="", description="Tên chủ tài khoản (in trên QR). DONATE_BANK_NAME."
    )

    # Dây chuyền video (video.factory) — dùng lại video_dub qua venv riêng của nó.
    videodub_python: Path = Field(
        default=PROJECT_ROOT / "video_dub" / ".venv" / "Scripts" / "python.exe",
        description="Python trong .venv riêng của video_dub (KHÔNG dùng venv chính)."
    )
    videodub_script: Path = Field(default=PROJECT_ROOT / "video_dub" / "dub.py")
    videodub_whisper_model: str = Field(
        default="small", description="Cỡ model faster-whisper cho dây chuyền video."
    )
    ytdlp_format: str = Field(
        default="bv*[height<=720]+ba/b[height<=720]",
        description="Format yt-dlp (≤720p cho nhẹ RAM/đĩa máy 12GB)."
    )
    ytdlp_cookies: Path | None = Field(
        default=None,
        description="File cookies.txt cho site cần đăng nhập (YTDLP_COOKIES trong .env)."
    )
    ytdlp_cookies_browser: str = Field(
        default="",
        description="Đường dẫn 'User Data' của trình duyệt Chromium để MƯỢN COOKIE "
        "TƯƠI tự động (vd CocCoc — không dính khóa App-Bound như Chrome). Ưu tiên "
        "hơn file cookies.txt; lỗi thì tự rơi về file. YTDLP_COOKIES_BROWSER trong .env."
    )

    # Dịch truyện chữ (novel.translate)
    novel_llm_tier: str = Field(
        default="bulk", description="Tầng router LLM cho dịch số lượng lớn (bulk/fast/smart)."
    )
    novel_rate_limit_rpm: int = Field(
        default=8, ge=1, le=60,
        description="Trần số call LLM/phút khi dịch truyện dài (né 429 pool free)."
    )

    # Viết truyện TỰ VẬN HÀNH (story.factory autopilot) — AURA tự viết chương mới
    # theo lịch, không cần user bấm. Đây là phần "AI tự vận hành" đúng nghĩa.
    story_autopilot_enabled: bool = Field(
        default=True,
        description="Bật nhịp tự viết truyện. Tắt: STORY_AUTOPILOT_ENABLED=false."
    )
    story_autopilot_interval_h: float = Field(
        default=12.0, gt=0,
        description="Cứ ngần này giờ AURA tự viết thêm 1 lượt chương cho bộ đang chạy."
    )
    story_autopilot_series: str = Field(
        default="",
        description="Tên bộ để tự viết tiếp (rỗng = tự chọn bộ mới nhất có bible)."
    )
    story_autopilot_chapters: int = Field(
        default=1, ge=1, le=5,
        description="Mỗi lượt tự viết bao nhiêu chương."
    )
    story_self_edit: bool = Field(
        default=True,
        description="Sau khi viết xong mỗi chương, chạy THÊM 1 lượt tự biên tập (biên "
                    "tập viên khó tính viết lại cho hay hơn: hook, show-don't-tell, "
                    "cắt sáo rỗng — giữ nguyên cốt). Gấp đôi call LLM/chương. "
                    "STORY_SELF_EDIT=false để tắt (nhanh + tiết kiệm quota)."
    )
    story_autopilot_words: int = Field(
        default=1800, ge=800, le=4000, description="Độ dài mỗi chương tự viết (từ)."
    )
    story_autopilot_video_enabled: bool = Field(
        default=True,
        description="Tích kho video: chương đã viết mà chưa có video kể chuyện thì "
                    "autopilot tự đẩy job story.video. STORY_AUTOPILOT_VIDEO_ENABLED=false để tắt."
    )
    story_autopilot_video_per_tick: int = Field(
        default=3, ge=1, le=10,
        description="Mỗi lượt autopilot đẩy tối đa bao nhiêu job video còn thiếu "
                    "(hàng đợi gọn; lượt sau đẩy tiếp)."
    )
    story_autopilot_youtube_enabled: bool = Field(
        default=True,
        description="Tự ĐĂNG video kể chuyện đã dựng lên YouTube (Unlisted) qua "
                    "youtube.upload — chương nào có video mà chưa đăng thì đẩy job. "
                    "STORY_AUTOPILOT_YOUTUBE_ENABLED=false để tắt."
    )
    story_autopilot_youtube_per_tick: int = Field(
        default=3, ge=1, le=10,
        description="Mỗi lượt autopilot đẩy tối đa bao nhiêu job đăng YouTube còn thiếu."
    )
    story_autopilot_youtube_privacy: str = Field(
        default="private",
        description="Chế độ khi autopilot TỰ đăng: private (riêng tư — chỉ Sếp xem) / "
                    "unlisted / public. Mặc định private để Sếp duyệt trước khi công khai."
    )
    story_autopilot_comic_enabled: bool = Field(
        default=True,
        description="Tích kho TRUYỆN TRANH: chương đã viết mà chưa có bản tranh thì "
                    "autopilot tự đẩy job story.comic. STORY_AUTOPILOT_COMIC_ENABLED=false để tắt."
    )
    story_autopilot_comic_per_tick: int = Field(
        default=1, ge=1, le=5,
        description="Mỗi lượt đẩy tối đa bao nhiêu job truyện tranh (nặng ~20 ảnh/"
                    "chương nên để thấp; lượt sau đẩy tiếp)."
    )
    coloring_autopilot_enabled: bool = Field(
        default=True,
        description="AURA TỰ nghĩ chủ đề sách tô màu mới mỗi lượt (khác cuốn đã làm) "
                    "và dựng. COLORING_AUTOPILOT_ENABLED=false để tắt."
    )
    coloring_autopilot_max_books: int = Field(
        default=15, ge=1,
        description="Dừng tự dựng khi đã có ngần này cuốn (tránh chất kho vô hạn khi "
                    "chưa bán; Sếp nâng lên khi bắt đầu bán được)."
    )
    coloring_autopilot_pages: int = Field(
        default=12, ge=3, le=30, description="Số trang tô mỗi cuốn tự dựng."
    )
    author_pen_name: str = Field(
        default="",
        description="Bút danh tác giả — in lên PDF/EPUB + cuối chương. AUTHOR_PEN_NAME."
    )

    # Truyện tranh (comic.translate v2 + comic.create)
    comic_font_path: Path = Field(
        default=PROJECT_ROOT / "assets" / "fonts" / "NotoSans-Regular.ttf",
        description="Font TTF có dấu tiếng Việt để đặt chữ vào bóng thoại/PDF."
    )
    image_api_primary: str = Field(
        default="pollinations",
        description="Nguồn tạo ảnh chính cho comic.create (pollinations/gemini)."
    )
    image_api_fallback: str = Field(
        default="gemini", description="Nguồn tạo ảnh dự phòng khi nguồn chính lỗi/hết lượt."
    )

    # story.video nâng cấp: chuyển động Ken Burns + xfade + nhạc nền (free, không GPU).
    story_video_music_dir: Path = Field(
        default=PROJECT_ROOT / "assets" / "music",
        description="Thư mục nhạc nền không bản quyền (.mp3/.m4a). Có file thì "
                    "story.video trộn nhẹ dưới giọng đọc; trống thì bỏ qua (chỉ giọng)."
    )
    story_video_motion: bool = Field(
        default=True,
        description="Bật hiệu ứng Ken Burns (pan/zoom) + chuyển cảnh xfade. Tắt "
                    "STORY_VIDEO_MOTION=false để về slideshow tĩnh (nhẹ CPU hơn)."
    )
    story_video_seconds_per_scene: float = Field(
        default=16.0, gt=4,
        description="Cứ ngần này giây giọng thì đổi 1 cảnh ảnh (nhỏ hơn = nhiều cảnh, "
                    "đỡ tĩnh, khớp thoại chặt hơn — nhưng nhiều ảnh Pollinations hơn)."
    )
    story_video_max_scenes: int = Field(
        default=30, ge=4, le=80,
        description="Trần số cảnh/video (né vẽ quá nhiều ảnh cho video dài)."
    )
    # explainer.video — kênh faceless TIẾNG ANH thị trường Mỹ (CPM cao).
    explainer_niche: str = Field(
        default="Ancient mysteries and history explained",
        description="Ngách kênh Anh mặc định (giọng/khung kịch bản). Ngách HẸP dễ lên view."
    )
    explainer_voice: str = Field(
        default="en-US-ChristopherNeural", description="Giọng đọc Mỹ (edge-tts)."
    )
    explainer_words: int = Field(
        default=900, ge=400, le=3000, description="Độ dài kịch bản mỗi video (từ)."
    )
    explainer_autopilot_enabled: bool = Field(
        default=False,
        description="AURA tự nghĩ chủ đề trong ngách explainer_niche + dựng video Anh. "
                    "MẶC ĐỊNH TẮT — bật khi đã lập kênh YouTube Mỹ riêng (video dồn kho "
                    "vô nghĩa nếu chưa có kênh). EXPLAINER_AUTOPILOT_ENABLED=true để bật."
    )
    explainer_autopilot_max: int = Field(
        default=10, ge=1, description="Trần số video Anh tự dựng (chờ Sếp đăng bớt)."
    )

    # video.shorts — video ngắn dọc (footage thật) qua MoneyPrinterTurbo.
    mpt_dir: str = Field(
        default=r"D:\MoneyPrinterTurbo",
        description="Thư mục cài MoneyPrinterTurbo (có venv riêng + config.toml + key)."
    )
    shorts_autopilot_enabled: bool = Field(
        default=False,
        description="AURA tự lấy đề tài NÓNG từ trend_radar -> dựng video ngắn dọc. "
                    "MẶC ĐỊNH TẮT — bật khi đã có kênh Shorts/TikTok để đăng. "
                    "SHORTS_AUTOPILOT_ENABLED=true để bật."
    )
    shorts_autopilot_max: int = Field(
        default=12, ge=1, description="Trần số video ngắn tự dựng (chờ Sếp đăng bớt)."
    )
    shorts_voice: str = Field(
        default="vi-VN-HoaiMyNeural-Female", description="Giọng đọc video ngắn (edge-tts)."
    )
    # --- PHỤ ĐỀ CHÁY VÀO HÌNH (29/07/2026) ---
    # Xem lại video AURA làm bằng skill 'watch' thì thấy KHÔNG khung nào có chữ, dù
    # subtitle.srt vẫn nằm trong thư mục. Người lướt TikTok tắt tiếng sẽ không hiểu gì.
    shorts_subtitle_enabled: bool = Field(
        default=True,
        description="Cháy phụ đề vào video ngắn. TẮT là mất người xem tắt tiếng.",
    )
    shorts_subtitle_font: str = Field(
        default="BeVietnamPro-Bold.ttf",
        description=(
            "Font phụ đề. PHẢI là font có dấu tiếng Việt — mặc định của MPT là "
            "MicrosoftYaHeiBold.ttc (tiếng Trung), dùng nó là MẤT DẤU."
        ),
    )
    shorts_subtitle_size: int = Field(
        default=72, ge=20, le=200,
        description="Cỡ chữ phụ đề cho khung dọc 1080x1920 (72 là to, dễ đọc trên điện thoại).",
    )
    shorts_subtitle_position: str = Field(
        default="center",
        description=(
            "Vị trí phụ đề: top/center/bottom. Để 'center' vì TikTok che ĐÁY màn "
            "(tên + caption) và CẠNH PHẢI (nút tim/chia sẻ)."
        ),
    )
    shorts_youtube_autopilot_enabled: bool = Field(
        default=False,
        description="Tự ĐĂNG video ngắn đã dựng lên YouTube (Shorts). MẶC ĐỊNH TẮT — bật "
                    "khi đã có kênh. SHORTS_YOUTUBE_AUTOPILOT_ENABLED=true."
    )
    shorts_youtube_privacy: str = Field(
        default="private",
        description="Chế độ đăng Shorts tự động: private (mặc định — Sếp xem rồi bật public)."
    )
    shorts_youtube_per_tick: int = Field(
        default=3, ge=0, description="Số Shorts tự đăng mỗi nhịp (quota YouTube ~6/ngày)."
    )
    shorts_youtube_channel: str = Field(
        default="",
        description="Key kênh YouTube đăng Shorts (theo sổ kênh). Rỗng = dùng kênh video mặc định."
    )

    # Hội đồng Triad + evolution: NGỦ ĐÔNG khi tập trung kiếm tiền (bật lại khi cần).
    council_enabled: bool = Field(
        default=False,
        description="False = main.py bỏ qua TriadCouncil/evolution (tiết kiệm RAM, giảm nhiễu)."
    )

    # --- Nhắn tin qua app (Telegram) — điều khiển AURA + nhận báo cáo từ điện thoại ---
    telegram_enabled: bool = Field(
        default=False,
        description="Bật kênh Telegram (AURA nhắn tin/nhận lệnh qua điện thoại). "
        "Cần TELEGRAM_BOT_TOKEN + TELEGRAM_OWNER_ID. TELEGRAM_ENABLED=true để bật."
    )
    telegram_bot_token: SecretStr | None = Field(
        default=None,
        description="Token bot Telegram (tạo qua @BotFather). Lưu trong .env, KHÔNG commit."
    )
    telegram_owner_id: str = Field(
        default="",
        description="Chat ID Telegram của DUY NHẤT Sếp — bot chỉ nghe lệnh từ id này "
        "(khoá an ninh: bot điều khiển được máy, người lạ tuyệt đối không được ra lệnh). "
        "Lấy id bằng cách nhắn cho @userinfobot."
    )

    # --- SkillOpt-Sleep: AURA tự tiến hoá KỸ NĂNG ban đêm (không đụng trọng số) ---
    skillopt_enabled: bool = Field(
        default=False,
        description="Bật nhịp 'đêm tiến hoá' (SkillOpt-Sleep) — thu hoạch phiên làm "
        "việc, đào tác vụ lặp, đề xuất skill tốt hơn qua cổng kiểm định. "
        "SKILLOPT_ENABLED=true để bật."
    )
    skillopt_backend: str = Field(
        default="mock",
        description="Backend chạy thử: 'mock' (chạy khô, KHÔNG tốn quota) hoặc "
        "'claude'/'codex'/'copilot' (dùng thật, TỐN quota LLM)."
    )
    skillopt_source: str = Field(
        default="claude", description="Nguồn transcript phiên: claude | codex | auto."
    )
    skillopt_lookback_hours: int = Field(
        default=24, ge=1, description="Cửa sổ thu hoạch (giờ). 0 = quét toàn bộ lịch sử."
    )
    skillopt_max_sessions: int = Field(
        default=5, ge=1, le=50, description="Trần số phiên đọc mỗi đêm (giữ chi phí)."
    )
    skillopt_max_tasks: int = Field(
        default=8, ge=1, le=50, description="Trần số tác vụ đào mỗi đêm."
    )
    skillopt_auto_adopt: bool = Field(
        default=False,
        description="TỰ ÁP bản skill mới khi qua cổng kiểm định. MẶC ĐỊNH TẮT — "
        "nên để Sếp duyệt, vì skill mới ảnh hưởng MỌI phiên sau."
    )
    skillopt_interval_h: float = Field(
        default=24.0, gt=0, description="Bao lâu (giờ) chạy một đêm tiến hoá."
    )

    # --- Rèn Prompt & Tự động Cập Nhật Mã Nguồn (Auto Update / Hot-Reload) ---
    prompt_evolve_autopilot_enabled: bool = Field(
        default=True,
        description="Bật nhịp rèn prompt ngầm tự động (prompt_evolve)."
    )
    prompt_evolve_interval_h: float = Field(
        default=24.0, gt=0, description="Chu kỳ rèn prompt (giờ)."
    )
    prompt_evolve_auto_adopt: bool = Field(
        default=True,
        description="Tự động áp dụng prompt mới khi điểm chấm vượt mốc margin."
    )
    auto_update_enabled: bool = Field(
        default=True,
        description="Bật tự động kiểm tra & cập nhật mã nguồn qua git pull và hot-reload."
    )
    auto_update_interval_h: float = Field(
        default=12.0, gt=0, description="Chu kỳ quét cập nhật mã nguồn (giờ)."
    )


    # --- Autopilot ĐẨY TRUYỆN LÊN ROOKIES (chương mới -> bản thảo trên web) ---
    rookies_autopilot_enabled: bool = Field(
        default=False,
        description="Chương mới AURA viết xong thì tự đẩy lên Rookies dạng BẢN THẢO "
        "(Sếp duyệt rồi mới đăng). Cần đăng nhập 1 lần: "
        "`python -m core.rookies_bot --login`. ROOKIES_AUTOPILOT_ENABLED=true để bật."
    )
    rookies_autopilot_per_tick: int = Field(
        default=2, ge=1, le=5,
        description="Mỗi nhịp autopilot đẩy tối đa mấy chương lên Rookies (nhịp người)."
    )
    rookies_autopilot_publish: bool = Field(
        default=False,
        description="TỰ ĐĂNG CÔNG KHAI luôn thay vì lưu bản thảo. MẶC ĐỊNH TẮT — "
        "nên để Sếp duyệt qua Telegram trước."
    )

    # --- Đăng truyện qua WordPress REST API (vd huyensonquan.com) ---
    wp_site_url: str = Field(
        default="https://huyensonquan.com",
        description="Gốc site WordPress để đăng chương (REST API /wp-json/wp/v2/posts)."
    )
    wp_username: str = Field(
        default="", description="Tên đăng nhập WordPress của Sếp trên site đó."
    )
    wp_app_password: SecretStr | None = Field(
        default=None,
        description="MÃ ỨNG DỤNG (Application Password) WordPress — KHÔNG phải mật khẩu "
        "chính. Tạo ở wp-admin > Hồ sơ > Application Passwords, thu hồi được bất cứ lúc nào."
    )
    wp_default_status: str = Field(
        default="draft",
        description="Trạng thái bài khi AURA đăng: 'draft' (NHÁP — mặc định, Sếp duyệt "
                    "rồi mới công khai) hoặc 'publish'."
    )

    # --- Auto Plan: tự làm việc nội bộ, không làm phiền Chủ ---
    auto_plan_enabled: bool = Field(
        default=True,
        description=(
            "Tự lập và thực hiện tác vụ nội bộ, nghiên cứu và tạo bản nháp an toàn. "
            "Không áp dụng cho gửi đơn, đăng công khai, thanh toán hoặc thao tác phá huỷ."
        ),
    )

    # --- Desktop Autopilot: mắt + tay cục bộ, cấp quyền một lần theo phạm vi ---
    desktop_autopilot_enabled: bool = Field(
        default=True,
        description=(
            "Cho daemon theo dõi cửa sổ hiện hành và chạy hàng đợi thao tác màn hình đã được "
            "Chủ cấp phạm vi. Không tự vượt qua OTP/CAPTCHA hoặc thao tác ngân hàng."
        ),
    )
    desktop_autopilot_monitor_interval_s: float = Field(
        default=15.0, ge=3.0, le=300.0,
        description="Nhịp theo dõi tiêu đề cửa sổ và kiểm tra desktop task (giây).",
    )
    desktop_autopilot_ocr_enabled: bool = Field(
        default=True,
        description="Cho phép OCR local theo yêu cầu; không chụp/lưu ảnh màn hình định kỳ.",
    )
    desktop_autopilot_ocr_languages: str = Field(
        default="vi,en",
        description="Danh sách ngôn ngữ EasyOCR local, phân tách bằng dấu phẩy.",
    )
    desktop_autopilot_allowed_windows: str = Field(
        default=(
            "aura,codex,chatgpt,chrome,edge,brave,firefox,cốc cốc,coccoc,"
            "facebook,tiktok,payhip,upwork,youtube,"
            "file explorer,explorer,notepad,visual studio code,vscode"
        ),
        description="Từ khóa tiêu đề cửa sổ được phép tự thao tác, phân tách bằng dấu phẩy.",
    )
    desktop_autopilot_blocked_terms: str = Field(
        default=(
            "mb bank,mbbank,banking,ngân hàng,password,mật khẩu,passcode,"
            "otp,captcha,2fa,authenticator,thanh toán,payment,chuyển tiền,transfer"
        ),
        description="Từ khóa nhạy cảm luôn chặn OCR và thao tác tự động.",
    )
    desktop_autopilot_max_actions_per_task: int = Field(
        default=25, ge=1, le=100,
        description="Trần thao tác trong một desktop task để tránh vòng lặp mất kiểm soát.",
    )

    # --- Cầu Android MB qua Wi-Fi nội bộ ---
    android_mb_lan_enabled: bool = Field(
        default=False,
        description=(
            "Mở cổng RIÊNG chỉ nhận báo có MB từ Android trong Wi-Fi nội bộ. "
            "Dashboard vẫn chỉ bind localhost; cổng này luôn yêu cầu token ghép cặp."
        ),
    )
    android_mb_lan_host: str = Field(
        default="auto",
        description="IP Wi-Fi nội bộ cho cầu Android MB ('auto' = IP mạng đang dùng).",
    )
    android_mb_lan_port: int = Field(
        default=8767, ge=1024, le=65535,
        description="Cổng riêng cho cầu Android MB Wi-Fi; không phải cổng dashboard.",
    )

    # --- AURA Avatar trên điện thoại robot (TÁCH KHỎI MB Bank) ---
    aura_avatar_lan_enabled: bool = Field(
        default=False,
        description=(
            "Mở cầu AURA Avatar dành riêng cho điện thoại robot. Kênh này chỉ hội thoại, "
            "không được duyệt lệnh, chạy tool, điều khiển máy hoặc truy cập dòng tiền."
        ),
    )
    aura_avatar_lan_host: str = Field(
        default="auto",
        description=(
            "IP cho AURA Avatar ('auto' = Wi-Fi; 'dual' = đồng thời USB/localhost + Wi-Fi)."
        ),
    )
    aura_avatar_lan_port: int = Field(
        default=8768, ge=1024, le=65535,
        description="Cổng riêng cho AURA Avatar; không dùng chung dashboard hoặc cầu MB Bank.",
    )

    # --- Vận hành ---
    log_level: str = Field(default="INFO", description="DEBUG/INFO/WARNING/ERROR.")

    @field_validator("briefing_persona")
    @classmethod
    def _normalise_persona(cls, v: str) -> str:
        s = str(v).strip().lower()
        return s if s in {"alpha", "gentle"} else "alpha"

    @field_validator("cloud_provider")
    @classmethod
    def _normalise_provider(cls, v: str) -> str:
        s = str(v).strip().lower()
        return s if s in {"claude", "openai", "router"} else "claude"

    @field_validator("council_generator_tier")
    @classmethod
    def _normalise_council_tier(cls, v: str) -> str:
        s = str(v).strip().lower()
        return s if s in {"local", "cloud", "auto"} else "local"

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level phải thuộc {allowed}, nhận: {v!r}")
        return upper

    def ensure_dirs(self) -> None:
        """
        Tạo sẵn các thư mục dữ liệu nếu chưa có. Gọi một lần lúc daemon khởi động,
        để các module sau không phải tự lo mkdir.
        """
        for path in (
            self.chroma_path,
            self.downloads_dir,
            self.outputs_dir,
            self.generated_tools_dir,
            self.factory_dir,
            self.ledger_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def require_cloud_key(self) -> SecretStr:
        """
        Lấy key Anthropic khi một tác vụ bắt buộc cần System 2. Nếu thiếu key,
        báo lỗi rõ ràng ngay thay vì để request cloud chết khó hiểu về sau.
        """
        if self.anthropic_api_key is None:
            raise RuntimeError(
                "Thiếu ANTHROPIC_API_KEY trong .env — không thể gọi System 2 (Claude)."
            )
        return self.anthropic_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Trả về singleton Settings (đọc .env đúng một lần nhờ lru_cache).
    Dùng hàm thay vì biến toàn cục trần để dễ override trong test
    (có thể gọi get_settings.cache_clear() rồi nạp lại).
    """
    return Settings()


# Tiện truy cập nhanh: `from core.config import settings`
settings: Settings = get_settings()


def reload_settings() -> Settings:
    """Xoá cache và nạp lại Settings từ .env tươi."""
    get_settings.cache_clear()
    global settings
    settings = get_settings()
    return settings


__all__ = ["Settings", "get_settings", "reload_settings", "settings", "PROJECT_ROOT"]
