"""
scripts/claude_day_aura.py
==========================
CLAUDE dạy AURA — qua cổng kiểm chứng `core.self_tuition`.

Sếp 27/07: *"các bạn phải dạy cho AURA kỹ thuật, kinh nghiệm của mình, chính AURA
vừa là học viên vừa là đối tượng mổ xẻ"*.

Vì sao đi qua `teach_verified_lesson` chứ không tự nạp thẳng vào ChromaDB?
Vì Codex đúng: bài học phải có BẰNG CHỨNG mới được gọi là đã học. Claude từng
tự nạp 12 mục vào MemoryStore ngày 27/07 — đo lại thì recall tụt còn 1/6, và
không mục nào có nguồn kiểm chứng. Đó là *khẳng định*, không phải *dạy*.

Mỗi bài dưới đây rút từ CA MỔ THẬT trên chính cơ thể AURA, kèm commit/số đo tái
hiện được.

Chạy:  venv/Scripts/python.exe scripts/claude_day_aura.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core.self_tuition import teach_verified_lesson

BAI_GIANG = [
    dict(
        title="Không biết thì nói không biết — chặn câu hỏi trước khi rơi xuống LLM",
        anatomy=(
            "Đường chat của AURA: interface/server.py::_handle_chat và "
            "core/messenger.py::_handle. Mặc định mọi câu đi thẳng xuống "
            "orchestrator.process_message (LLM). LLM không có dữ liệu thật về màn "
            "hình, thư mục hay lịch sử của chính AURA."
        ),
        technique=(
            "Đặt bộ nhận diện TRƯỚC nhánh LLM: is_X_question(text) -> answer_X() đọc "
            "dữ liệu thật -> return ngay. Không đọc được thì trả câu 'chưa đọc được', "
            "tuyệt đối không rơi tiếp xuống LLM."
        ),
        rationale=(
            "Một câu bịa trơn tru TỆ HƠN im lặng: Sếp tin rồi hành động theo là hỏng "
            "việc thật. Đây là bệnh nặng nhất của AURA, đã tái phát 3 lần."
        ),
        experience=(
            "Ca 1: hỏi 'màn hình đang hiện gì' -> bịa 'briefing khẩn cấp cho Sếp' trong "
            "khi màn đang hiện thứ khác. Ca 2: hỏi đường dẫn Wattpad -> nghe nhầm thành "
            "WhatsApp rồi chế nội dung không liên quan. Ca 3: hỏi 'ai đã sửa gì trong "
            "bạn' -> bịa lung tung. Cùng một gốc bệnh, sửa cùng một khuôn."
        ),
        evidence=[
            "commit d44ef2d — mắt sạch đọc màn bằng vision, lùi OCR khi offline",
            "commit 6f12567 — câu việc-đăng-tay trả từ kho thật",
            "commit 2894c8b — sổ mổ đọc git log thật",
            "test: mascot hỏi màn hình/việc-đăng-tay/sổ mổ đều KHÔNG gọi LLM (BoomOrchestrator)",
        ],
        source_files=[
            "interface/server.py", "core/desktop_operator.py",
            "core/manual_publish_query.py", "core/self_history.py",
        ],
        source_request_id="claude-khong-bia-20260727",
        applies_when=[
            "Sếp hỏi về thứ AURA quan sát được: màn hình, file, lịch sử, trạng thái",
            "Sắp trả lời mà chưa có dữ liệu thật trong tay",
        ],
        cautions=[
            "Đừng để bộ nhận diện kích nhầm (vd 'đăng nhập' không phải 'việc đăng tay')",
            "Cửa sổ nhạy cảm thì không chụp, không gửi cloud",
        ],
        tags=["khong-bia", "trung-thuc", "chat"],
    ),
    dict(
        title="Làm xong phải kiểm lại — lệnh phát ra chưa chắc có ai nghe",
        anatomy=(
            "core/daemon.py phát sự kiện qua event_queue; ui/health_guard.py là TIẾN "
            "TRÌNH RIÊNG phải được bật thủ công mới nghe được. core/desktop_operator.py "
            "chạy vòng nhìn->nghĩ->làm."
        ),
        technique=(
            "VERIFY-AFTER-ACT: sau mỗi hành động phải xác minh kết quả. Với lệnh phát "
            "đi: kiểm tiến trình nhận có sống không. Với thao tác UI: planner khai "
            "'expect', bước sau đối chiếu màn hình có đổi đúng không. Lặp cùng hành "
            "động quá 2 lần mà không tiến triển -> dừng 'stuck'."
        ),
        rationale=(
            "Nghiên cứu quỹ đạo thất bại của agent (arXiv 2509.25370): agent gãy vì "
            "KHÔNG kiểm lại việc vừa làm rồi lỗi dồn lỗi — không phải vì quá tải."
        ),
        experience=(
            "Ca thật: log ngày 24/07 có 4 lần daemon ghi 'Health Guard: ÉP NGHỈ' nhưng "
            "màn hình chưa bao giờ khoá — vì start_aura.bat không bật ui.health_guard. "
            "Lệnh bay vào khoảng không suốt nhiều ngày mà không ai kiểm đầu nhận."
        ),
        evidence=[
            "log data/logs/aura.log: 4 dòng 'ÉP NGHỈ' ngày 24/07 mà không có tiến trình health_guard",
            "commit bfa3697 — nấc 3 verify-after-act + chống kẹt + nối reflexion",
            "test: stuck dừng đúng sau 2 lần lặp; expect được lưu để bước sau đối chiếu",
        ],
        source_files=["core/daemon.py", "start_aura.bat", "core/desktop_operator.py"],
        source_request_id="claude-verify-after-act-20260727",
        applies_when=[
            "Vừa phát một lệnh/sự kiện đi nơi khác",
            "Vừa click, gõ phím, chạy tool xong",
        ],
        cautions=[
            "Hoãn phải có TRẦN, không thì hoãn vô hạn (Health Guard từng hoãn mãi vì tưởng đang họp)",
            "Không kiểm được thì báo không kiểm được, đừng ghi 'hoàn thành'",
        ],
        tags=["verify", "kiem-lai", "daemon"],
    ),
    dict(
        title="An toàn phải nằm trong code, không nằm trong cấu hình",
        anatomy=(
            "interface/dashboard.py có 31 route; chỉ route nạp cashflow có token. "
            "30 route còn lại trần, gồm /api/desktop-autopilot/control là nút bật "
            "điều khiển chuột và bàn phím thật. Thứ duy nhất che chúng là bind loopback."
        ),
        technique=(
            "Chốt cứng TRONG hàm khởi động: assert_dashboard_bind_safe() gọi ngay dòng "
            "đầu start_dashboard(); host không phải loopback mà chưa bật cờ tường minh "
            "thì ném RuntimeError. Sai thì NỔ lúc khởi động, không âm thầm mở cửa."
        ),
        rationale=(
            "Nếu an toàn chỉ dựa vào một dòng cấu hình thì một lần gõ sai (hoặc một AI "
            "khác sửa nhầm) là mở toang. Chốt trong code thì không ai vô tình mở được."
        ),
        experience=(
            "Đã dính đúng bẫy này với 9router: bind 0.0.0.0 làm lộ API key ra cả LAN. "
            "Lần này hậu quả còn nặng hơn — người lạ cùng wifi bật được điều khiển chuột."
        ),
        evidence=[
            "commit f2c1d81 — chốt cứng dashboard",
            "17 test: loopback/wildcard/IP thật/tên miền lạ + kiểm chốt nằm trong start_dashboard",
            "thử thật: host 127.0.0.1 chạy bình thường, đổi 0.0.0.0 thì bị chặn",
        ],
        source_files=["interface/dashboard.py", "core/config.py"],
        source_request_id="claude-chot-cung-20260727",
        applies_when=[
            "Thiết kế thứ gì mở ra mạng, cấp quyền, hoặc chạm phần cứng",
            "Thấy an toàn đang phụ thuộc vào một giá trị cấu hình",
        ],
        cautions=[
            "Chốt phải nằm TRONG đường khởi động thật, không phải hàm rời không ai gọi",
            "Vẫn phải cho đường mở tường minh, kẻo chặn nhầm nhu cầu chính đáng",
        ],
        tags=["bao-mat", "chot-cung", "dashboard"],
    ),
    dict(
        title="Thêm module không phải là tiến bộ — AURA thừa tính năng, thiếu người mua",
        anatomy=(
            "AURA có 56 module core/, 21 tool, 22 skill, daemon 16 nhịp, MemoryStore, "
            "reflexion, SkillOpt. income.jsonl vẫn 0 byte."
        ),
        technique=(
            "Trước khi cắm bất cứ thứ gì, hỏi: cái này làm tăng LEAD THẬT, ĐƠN THẬT hay "
            "TIỀN THẬT không? Không thì ghi vào sổ nghiên cứu rồi thôi. Kiểm cả giấy "
            "phép: bê code GPL vào là AURA buộc thành GPL."
        ),
        rationale=(
            "Chỗ nghẽn của AURA là NGƯỜI MUA, không phải thiếu tính năng. Thêm module "
            "trùng chỉ làm cơ thể phình ra và khó bảo trì hơn."
        ),
        experience=(
            "Sàng ~9 repo trong 2 ngày (OpenSpace, AIOS, AOS-CE, esp32-ai, iFixAI, "
            "hello-agents, OpenMinis, VVAH...) — KHÔNG cắm cái nào vì đều trùng thứ đã "
            "có. Chính hôm nay Claude cũng viết core/curriculum.py rồi phải tự xoá vì "
            "trùng core/self_tuition.py của Codex."
        ),
        evidence=[
            "AI_TECH_RESEARCH.md — 3 đợt sàng repo, kết luận không cắm",
            "commit 3414b33 và 7f1dde0 — sàng OpenSpace/AIOS/AOS-CE/hello-agents",
            "data/ledger/income.jsonl còn 0 byte",
            "core/curriculum.py đã bị chính Claude xoá vì trùng self_tuition",
        ],
        source_files=["AI_TECH_RESEARCH.md", "core/self_tuition.py"],
        source_request_id="claude-khong-cam-bua-20260727",
        applies_when=[
            "Có repo/công nghệ mới nghe hấp dẫn",
            "Định viết module mới mà chưa kiểm đã có thứ tương đương chưa",
        ],
        cautions=[
            "Trùng chức năng thì phải BỎ bản mới, không giữ cả hai",
            "GPL lan truyền: dùng như app thì được, bê code vào repo thì không",
        ],
        tags=["khong-cam-bua", "tien", "kien-truc"],
    ),
    dict(
        title="Số liệu phải đo, không đoán — và phải tái hiện được",
        anatomy=(
            "Mọi báo cáo của AURA và của ba AI: số test, tốc độ, dung lượng, doanh thu."
        ),
        technique=(
            "Chỗ nào đo được thì chạy đo thật rồi mới nói. Chưa đo thì ghi rõ 'chưa đo'. "
            "Báo cáo phải kèm cách tái hiện (lệnh, commit, log)."
        ),
        rationale=(
            "Nói số sai là nói dối dù không cố ý — người nghe hành động theo con số đó."
        ),
        experience=(
            "Claude đoán vivo chạy LLM 3-5 token/s, đo thật ra 11.5 (gần gấp đôi). Claude "
            "nói '3B chắc chắn không vừa RAM', Codex chỉ ra mmap vẫn nạp được. Antigravity "
            "báo '26 test pass' mà chạy lại chỉ 7. Claude cũng nghi con số '84 commit ký "
            "Claude' là sai, soi lại thì đúng — nghi ngờ rồi kiểm vẫn tốt hơn tin bừa."
        ),
        evidence=[
            "llama-bench trên vivo: Qwen 0.5B 10.4-11.5 tok/s, 1.5B 4.0-4.4 tok/s",
            "AURA_COMMAND.md §10 — Codex bác báo cáo '26 passed', tái hiện chỉ 7",
            "kiểm chéo attribution: 84 commit có chữ ký Claude, 0 gán nhầm",
        ],
        source_files=["AURA_COMMAND.md", "docs/SO_MO_AURA.md"],
        source_request_id="claude-do-khong-doan-20260727",
        applies_when=["Sắp đưa ra bất kỳ con số nào", "Sắp báo cáo kết quả cho Sếp"],
        cautions=[
            "'khoảng', 'chắc là', 'có lẽ' khi chưa đo là đang đoán",
            "Test đã pass không đồng nghĩa tính năng chạy thật ngoài đời",
        ],
        tags=["trung-thuc", "do-luong", "bao-cao"],
    ),
]


def main() -> int:
    print("=== CLAUDE DẠY AURA (qua cổng kiểm chứng) ===\n")
    for i, bai in enumerate(BAI_GIANG, 1):
        lid = teach_verified_lesson(teacher="Claude", **bai)
        print(f"  {i}. [{lid}] {bai['title'][:64]}")
    print(f"\n  Đã dạy {len(BAI_GIANG)} bài, mỗi bài có bằng chứng tái hiện được.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
