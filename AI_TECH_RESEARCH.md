# Tổng hợp Công nghệ AI Mới (Research Notes)

*Được ghi nhận từ quá trình tìm hiểu của người dùng để ứng dụng cho AURA_OS_v2 trong tương lai.*

## I. Nhóm Công cụ Sản xuất & Prompting

1. **Primfilm (AI Comic & Short Drama Studio):** 
   - Mã nguồn mở tự động hóa quy trình làm phim ngắn, motion comic từ kịch bản. 
   - **Ứng dụng cho AURA:** Rất tiềm năng! AURA đang tự động viết truyện, nếu kết hợp Primfilm (tư duy Keyframe-driven), AURA có thể tiến xa hơn bằng cách tự động minh họa hoặc dựng video ngắn cho các câu chuyện của mình thay vì chỉ là Text.

2. **Cấu trúc 6 Phần Cốt lõi của Master Prompt:**
   - (1) Vai trò, (2) Mục tiêu, (3) Bối cảnh, (4) Đối tượng, (5) Định dạng, (6) Yêu cầu hỏi lại.
   - **Ứng dụng cho AURA:** Có thể áp dụng ngay để cải tiến các AI Prompts trong `factory/tools/story_factory.py` và `factory/reflexion.py`. Kết hợp với nguyên tắc **Few-Shot Learning**, cấu trúc này sẽ giúp AURA viết truyện sắc sảo, đúng tâm lý nhân vật và kiểm soát nhịp độ tốt hơn.

3. **GPT-Red & Phòng chống Prompt Injection:**
   - **Ứng dụng cho AURA:** Trong bối cảnh AURA tự động sinh prompt và nhận input, việc áp dụng cơ chế xác nhận trước các hành động nguy hiểm (sandbox) là rất quan trọng để tránh AI bị "tiêm lệnh" phá hỏng cốt truyện hoặc hệ thống.

4. **Claude AI + NotebookLM:**
   - **Ứng dụng cho AURA:** Có thể dùng để quản lý "Lore" (thế giới quan, tuyến nhân vật đồ sộ) của các bộ truyện dài kỳ mà AURA đang sáng tác.

## II. Nhóm Kiến trúc & Agent Framework

1. **OpenClaw & Open Interpreter:**
   - Hệ sinh thái tự động hóa máy tính, quản lý Multi-Agent. Open Interpreter cho phép thực thi lệnh an toàn trong Sandbox.
   - **Ứng dụng cho AURA:** AURA là một hệ điều hành Agentic (`AURA_OS_v2`). Các mô hình Multi-Agent (Researcher, Writer, Reviewer...) phối hợp có thể giúp AURA tự động hóa toàn bộ quy trình: từ nghiên cứu thị hiếu độc giả -> lên plot -> viết truyện -> kiểm duyệt.

2. **Awesome LLM Apps & Các Repo GitHub:**
   - Kho lưu trữ >100 ứng dụng LLM, RAG.
   - **Ứng dụng cho AURA:** Là kho tham khảo kiến trúc tuyệt vời để xây dựng các agent chuyên biệt (ví dụ: Agent kiểm tra tính logic của cốt truyện, Agent tự động thiết kế bìa truyện).

3. **Lưu ý Kiến trúc (Bẫy LocalStorage & Iroh P2P):**
   - **Ứng dụng cho AURA:** Nhắc nhở về việc lưu trữ State/Lịch sử của AURA phải dùng cơ sở dữ liệu vững chắc thay vì các bộ nhớ tạm, đảm bảo AURA có thể nhớ được toàn bộ diễn biến các chương truyện trước đó một cách chính xác.

## III. Bổ sung (ghi bởi Claude — mẻ 2026-07-21)

### A. TRÚNG dòng tiền AURA (ưu tiên cắm)

1. **OpenMontage** (repo THẬT: `github.com/calesthio/OpenMontage` — ⚠️ né fork giả Open-Montage/, thecoldblooded…):
   - Xưởng video **agentic** mã nguồn mở: 12 pipeline, 52 tool, 500+ skill. Do AI coding assistant (Claude Code/Cursor) ĐIỀU KHIỂN — agent tự đọc skill, gọi tool, tự review, checkpoint, hỏi người ở điểm quyết định sáng tạo. Footage free CLIP-index (Pexels/Archive.org/NASA/Wikimedia/Unsplash). Chạy local (Python+Node+FFmpeg — AURA đã có đủ).
   - **Ứng dụng cho AURA:** NÂNG CẤP LỚN so với MoneyPrinterTurbo (hiện là `video.shorts`). Hợp cách AURA vận hành (agent điều phối). Ứng viên số 1 cho dòng video kiếm tiền + explainer US-market.

2. **career-ops** (repo THẬT: `github.com/santifer/career-ops` — 60k sao; ⚠️ fork giả ymys/AKCodez/BobbyWang…):
   - AI job search chạy local trong CLI: quét portal, chấm điểm A-F, may CV theo từng JD (ATS-optimized PDF), track ứng tuyển, xử lý batch.
   - **Ứng dụng cho AURA:** TRÙNG & nâng cấp trực tiếp `skills/scouts/job_scout.py` + `factory/tools/freelance_apply.py` + dự án JobRadar. Tham khảo cách chấm A-F + may CV per-JD để nâng khâu freelance của AURA.

### B. Tham khảo (học/ý tưởng — không phải tool ra tiền)

3. **system_prompts_leaks** (GitHub 52k sao, CC0): tổng hợp 150+ system prompt rò rỉ của ChatGPT/Claude/Gemini/Cursor…
   - **Ứng dụng cho AURA:** học cách hãng lớn viết prompt để nâng prompt trong `story_factory.py`/`reflexion.py`. KÈM BÀI HỌC BẢO MẬT: "AI giữ bí mật rất kém — TUYỆT ĐỐI không giấu API key/JWT secret trong prompt hay source" (đúng lúc — Antigravity vừa hard-code JWT secret trong web lqmeta, tôi đang vá).

4. **aitmpl.com** (AI Templates): kho mẫu Skills/Agents/Commands/Settings/MCPs/Plugins cho Claude.
   - **Ứng dụng cho AURA:** mẫu tham khảo khi viết agent/skill mới cho AURA hoặc web lqmeta.

5. **MACE Framework** (nghiên cứu Wisconsin-Madison/UCSB): "Multi-Agent LLMs Fail to Explore Each Other" — LLM làm nhóm hay bám chặt 1 đồng đội đầu, ngừng khám phá. MACE dùng LinUCB (contextual bandit) ép hệ thống thử agent ít dùng.
   - **Ứng dụng cho AURA:** hợp với TỔ CREW 4 công nhân (`core/crew.py`) — ý tưởng luân phiên/khám phá công nhân thay vì luôn gọi 1. Còn research, chưa cắm.

6. **AI-For-Beginners** (Microsoft, 51k sao, có tiếng Việt) + **Neuro-Symbolic reasoning** (Georgia Tech) + **Tensor/PyTorch tutorial**: kiến thức nền cho user học, không phải tool.

7. **BỎ:** Codex Dream Skin (chỉ đổi theme Codex — không ra tiền).

### C. Bổ sung mẻ 2 (Claude, 2026-07-21) — chỉ món MỚI, phần còn lại đã có ở Mục I-II & III-A/B

> Lưu ý: mẻ 12 video lần này ĐA SỐ TRÙNG với đồ đã ghi (Primfilm, GPT-Red, Claude+NotebookLM, Master Prompt 6-phần, OpenClaw, Open Interpreter, Awesome LLM Apps, Iroh). Chỉ liệt kê cái chưa có:

8. **OpenCut** (top-1 GitHub tuần): trình chỉnh sửa video mã nguồn mở đa nền tảng (Web/Desktop/Mobile), thay CapCut.
   - **Ứng dụng cho AURA:** bổ trợ dòng video (`video.shorts`/explainer) — khâu chỉnh sửa/ghép hậu kỳ free, không watermark. Kết hợp OpenMontage (dựng) + OpenCut (chỉnh) là bộ đôi mạnh.

9. **Hallmark** (Nutlope): skill thiết kế UI CHỐNG kiểu "web chuẩn khuôn AI" cho Claude Code/Cursor/Codex.
   - **Ứng dụng cho web lqmeta:** đúng lúc — user vừa than nav "lộn xộn". Tham khảo Hallmark để web Liên Quân trông chuyên nghiệp, khác biệt thay vì generic. (Cho tôi/Antigravity khi làm giao diện.)

10. **Harness Engineering** (repo top GitHub): nâng chất AI Agent bằng tối ưu NGỮ CẢNH + CÔNG CỤ (không cần đổi model).
    - **Ứng dụng cho AURA:** đúng triết lý AURA (chạy model free/nhỏ nhưng khôn nhờ context tốt) — tham khảo cho `brains/` + tổ crew.

11. **Cảnh báo đáng ghi (nghiên cứu phụ thuộc AI):** càng tin AI tuyệt đối, người dùng càng dễ TRẢ LỜI SAI nhưng độ TỰ TIN lại tăng. Bài học: AURA/web luôn giữ khâu người-duyệt ở quyết định quan trọng (đăng bài, đăng video, deploy).

12. **BỎ khỏi dòng tiền AURA:** Vibe-Trading (agent trading — rủi ro tài chính, không hợp), DeepTutor (gia sư AI — giáo dục, không ra tiền), tin thị trường (Qwen 3.8, Claude Code viết lại bằng Rust, NVIDIA-Nhật) — chỉ là tin, không phải tool cắm được.

### D. Bổ sung mẻ 3 (Claude, 2026-07-22) — 9 video, lọc theo hợp-máy-no-GPU + ra-tiền

> Kết luận nhanh: chỉ **1 món thật sự "đổi AURA"** (last30days-skill), còn lại là tiện-ích-phụ hoặc perk-cá-nhân cho việc code, không phải nâng cấp lõi. Đừng để "744B", "1-bit", "Fable 5 free" làm lóa mắt — chấm theo: có chạy được nhịp thật của AURA không.

**★ TIER 1 — cắm được, nâng dòng tiền:**

1. **last30days-skill** (`npx skills add mvanhorn/last30days-skill`): quét đồng thời Reddit/X/YouTube/TikTok/HackerNews/GitHub/Polymarket → 1 file `brief.html` offline, xếp theo TƯƠNG TÁC THẬT (upvote/like/tiền cược), có trích nguồn.
   - **Ứng dụng:** đây chính là **trend.radar bản xịn** (công nhân thứ 4 đang có). Hiện trend.radar tự quét + lọc bằng từ khóa+embedding; skill này gom đa-nền-tảng + xếp hạng bằng engagement thật → nguồn ý tưởng truyện/video **chuẩn thị hiếu** hơn nhiều. Đáng để tôi cắm/nhái cơ chế vào trend.radar. **← món "đổi AURA" của mẻ này.**

**◆ TIER 2 — tiện ích phụ / kênh mới (nice-to-have):**

2. **OpenClaw + Zalo Bot API** (Cloudflare Tunnel → webhook): cho gateway AI nhắn/nhận qua Zalo.
   - **Ứng dụng:** kênh **điều khiển AURA từ xa qua Zalo** (nhận báo cáo ca, ra lệnh cho mascot khi không ngồi máy). Trùng ý #7 Hermes (điều khiển qua Telegram). Là "remote control", không phải lõi kiếm tiền → làm sau.
   - **KIỂM CHỨNG 2026-08-11 — thay kết luận cũ:** provider Ollama và hai kênh
     Zalo là có thật, nhưng `zalo`/`zalouser` đều experimental; `zalouser` không
     chính thức và có nguy cơ khóa tài khoản. Full-agent trên `qwen3.5:4b` đã
     thất bại ở raw session và tái lập độc lập. **Không dùng làm bộ não AURA**;
     chỉ đọc kiến trúc adapter/context guard. Không có hard minimum 16K toàn cục.

3. **free-claude-code** (proxy Claude Code CLI → NVIDIA NIM 40req/ph, OpenRouter, DeepSeek, LM Studio local): chạy Claude Code free không cần API key Anthropic.
   - **Ứng dụng:** phần lớn TRÙNG litellm-router AURA đã có. Giá trị thật là **cho CHÍNH anh dùng khi code** (tôi/Antigravity chạy free) + có thể bơm thêm quota model free cho AURA. Tham khảo danh sách provider của nó.

4. **Hermes Agent** (`github.com/NousResearch/hermes-agent`, MIT, ra 2/2026) — **ĐÃ MỔ KỸ 2026-07-22, nâng từ "tham khảo" lên "ứng viên động cơ".**
   - **Là gì:** gần như "AURA phiên bản đội Nous Research". Python 3.11 + Node (cài 1 dòng), **model-agnostic** (OpenRouter/OpenAI/**your own endpoint**/Nous Portal 300+ — y hệt tư duy litellm-router AURA), **KHÔNG cần GPU** (chạy VPS $5, serverless idle ~$0). Trí nhớ = markdown `~/.hermes/` (**SOUL.md / MEMORY.md / USER.md** — rất giống MemoryStore AURA + kiểu memory của tôi). Sandbox: command-approval + container isolation + 6 backend (local/Docker/SSH/Singularity/Modal/Daytona).
   - **3 thứ Hermes CÓ mà AURA THIẾU (đều là phần khó tự xây):** ① **tự-SINH skill từ kinh nghiệm** sau task phức tạp, theo chuẩn mở **agentskills.io** (AURA đang registry cố định); ② **messaging gateway 1 process** (Telegram/Discord/WhatsApp/Signal/Slack/Email) = chính là "điều khiển AURA từ xa" — xịn hơn hack OpenClaw+Zalo (#2); ③ sandbox/isolation chuẩn.
   - **Điểm mấu chốt:** Hermes GIẪM nhiều lên phần LÕI-AGENT của AURA, NHƯNG không có xưởng-kiếm-tiền (story/video/job/coloringbook), mascot Miku, tính năng ép-nghỉ/khoá-ĐT. Tín hiệu đẹp: Hermes + last30days + nhiều skill khác **cùng chuẩn agentskills.io** → skill viết đúng chuẩn cắm được cả hai.
   - **QUYẾT ĐỊNH (Chỉ huy + Sếp 2026-07-22):** KHÔNG rewrite AURA trên Hermes (mất xưởng tiền + mascot), KHÔNG bỏ qua. Coi là "động cơ nâng cấp" cho 2 lớp AURA yếu: (a) điều khiển xa qua gateway, (b) tự-sinh-skill. **→ GIAO ANTIGRAVITY**: chạy thử Hermes SONG SONG (thư mục riêng, trỏ model về router/Ollama AURA), test gateway Telegram + vòng tự-sinh-skill, rồi báo có đáng nhận làm lõi không. Giữ nguyên AURA trong lúc thử.
   - **KIỂM CHỨNG 2026-08-11 — SUPERSEDED:** raw run local còn nguyên: 698 giây
     nội bộ/701,09 giây wall-clock và không trả “Hà Nội”. Hermes có hỗ trợ
     Ollama local qua `custom` (không phải chỉ `ollama-cloud`), nhưng hard floor
     64.000 token là thật. **Đóng hồ sơ vai trò ứng viên động cơ trên máy này**; chỉ
     tham khảo sandbox, gateway và vòng đời skill. Không tuyên bố cần đúng 16 GB
     VRAM vì phép đo không chứng minh con số đó.

5. **Awesome LLM Apps** (118k sao, 100+ template agent/RAG): — đã ghi ở Mục II-2 & III-B. Vẫn là kho mẫu để bốc pattern agent lẻ, không cắm nguyên khối.

**✕ TIER 3 — BỎ / lóa mắt, không hợp nhịp AURA:**

6. **GLM-5.2 744B trên laptop no-GPU (Colibri)**: chạy được nhưng **~0.1 token/s** (stream từ SSD) — chỉ hợp "chạy qua đêm 1 nhiệm vụ". AURA cần nhịp nhanh + đã có router cloud free (nhanh hơn nhiều) → **bỏ**, chỉ là màn trình diễn kỹ thuật.
7. **Bonsai 27B (1-bit, 3.8GB)**: nén khủng, chạy trình duyệt/điện thoại NHƯNG hay bịa (kém Q4). AURA lấy chất lượng từ cloud free → **bỏ**.
8. **Claude Fable 5 free qua GitLab Duo Trial**: perk dùng-thử 30 ngày, cap 24 credit + 400 phút/tháng — **không phải runtime AURA**. Ghi lại cho anh dùng riêng khi cần model 1M-context, hết trial là thôi.
9. **OpenCut**: đã ghi ở mẻ 2 (Mục C-8) — vẫn Tier 1 cho khâu chỉnh video, nhưng không mới.

### E. BÙ TỪ TRANSCRIPT (Claude, 2026-07-22) — mẻ "Top-10 GitHub Tuần 23" (MSG 117) bị sót trước đây

> Sếp nghi ngờ đúng: quét lại transcript phiên này thấy mẻ này ghi thiếu. Lúc đó chỉ **markitdown** + **headroom** được cắm thật (→ `core/ingest.py`, `brains/compress_ctx.py`, xem [[aura-ingest-compress]]); các món dưới KHÔNG được ghi. Nay bù + triage.

**◆ Đáng — lưu để cân nhắc:**
- **ECC** (agent-code OS, +10k sao/tuần): trí nhớ + kỹ năng LIÊN TỤC qua session, quét bảo mật trước khi code, đóng gói 64 agent/261 skill/84 lệnh, cắm vào Codex/Claude Code/Cursor. **CÙNG HỌ với Hermes** (mục D-4) — khi thử "động cơ agent" thì so ECC vs Hermes. Ghi để Antigravity xem chung.
- **LLM-as-a-Tutor** (nghiên cứu KAIST + NVIDIA + CMU): sửa "đề bão hoà" khi LLM-judge chấm bài viết — khi các rollout đều tốt ngang nhau, judge chuyển vai thành **Gia sư ra thêm ràng buộc nhỏ (atomic constraint)** để tăng độ khó dần. **Ứng dụng AURA:** đúng bài toán QC truyện của `factory/reflexion.py` (chấm viết lách không có đúng/sai máy) — ý hay để nâng khâu tự-chấm story.factory. Còn nghiên cứu, chưa cắm.
- **Google DeepMind — Routing research** (HSE/Hierarchic Social Entropy): router chọn model nên đo **khác biệt hành vi + độ ổn định**, không chỉ chính xác+chi phí; phát hiện: nhóm <10 model chọn kỹ là đủ phủ; **prompted-router bền với nhiễu diễn đạt hơn KNN-router**. **Ứng dụng:** tinh chỉnh [[aura-litellm-router]] (chọn pool model đa dạng, ưu tiên định tuyến theo ngữ nghĩa). Tham khảo.
- **OfficeCLI** (+15k sao): cho AI coding (Claude Code/Cursor) đọc/sửa/tự động hoá Word/Excel/PPT, có **Visual Feedback Loop** (AI "nhìn" ảnh chụp tài liệu → tự sửa tràn chữ/lệch bảng), kèm GUI AionUI. **Ứng dụng:** nếu AURA cần xuất báo cáo/tài liệu bán được (vd sách bài tập, giáo án) thì đây là khâu văn phòng. Để sau.
- **voxCPM** (openbmb): mô hình TTS — ứng viên thay/bổ sung edge-tts cho dòng video kể chuyện (cần verify hợp máy no-GPU trước). Để sau.
- **UI UX Pro Max** (skill 161 quy luật thiết kế + 99 hướng dẫn UX, cắm Cursor/Claude Code — từ MSG 18): chống UI "AI thô xấu". **Cùng vai Hallmark** (mục C-9) cho web lqmeta — cho Antigravity chọn 1 khi làm giao diện.

**✕ Bỏ / minor (ghi cho đủ, không theo đuổi):**
- **AIRI** (+42k, AI-waifu self-host Live2D/VRM/WebGPU, 25+ brain): **TRÙNG hướng VTuber/pet đã GỠ SẠCH** — xem [[aura-vtuber]]. Sếp đã chốt quay về bong bóng chat mascot Miku → KHÔNG làm lại.
- **JoyAI-VL-Interaction** (8B multimodal video real-time): đòi GPU + real-time video — không hợp máy. Bỏ.
- **ai-website-cloner-template** (clone UI web→code): xuất **Tailwind v4/shadcn** — mà lqmeta luật CẤM Tailwind (Vanilla CSS). Không hợp. Bỏ.
- **GitReverse** (github.com→gitreverse.com ra prompt repo), **Codebuff** (AI code free chèn quảng cáo), **Build-Your-Own-X**, **Toonflow-app**, **Trellis/TRELLIS.2** (đã BỎ ở triage — GPU 2D→3D game): tiện ích cá nhân / sai domain / đòi GPU. Bỏ.
- **Cơ chế "Skill Library" / Voyager** (Minecraft, nhanh 15.3×): là KHÁI NIỆM tự-sinh-skill (Agent tự viết code giải task mới → chạy thử PASS mới cất kho) — chính là thứ Hermes/ECC hiện thực. Không phải repo cắm; gộp vào quyết định "động cơ agent" (mục D-4).

### F. Mẻ 4 (Claude, 2026-07-23) — 23 món Sếp gửi

> 7 món ĐÃ có ở các mục trên (hallmark C-9 · vibe-trading C-12 BỎ · moneyprinterturbo ĐÃ CẮM thành `video.shorts` · ecc E · officecli E · career-ops III-A · perplexity — nguồn của last30days D-1). Dưới đây là phần MỚI.

**★ TIER 1 — trúng đúng nỗi đau hiện tại của AURA:**

1. **9router** (22.7k★, `decolua`) — nối Claude Code / Codex / Cursor / Cline / Copilot / **Antigravity** tới **Claude/GPT/Gemini MIỄN PHÍ qua 40+ nhà cung cấp**, có **auto-fallback** + giảm token (RTK).
   - **Ứng dụng:** đúng lúc Sếp đang tính mua gói. Vừa hạ chi phí cho CHÍNH việc code (tôi + Antigravity), vừa có thể bơm thêm nguồn free cho [[aura-litellm-router]]. Ứng viên số 1 mẻ này. (Kiểm ToS từng provider trước khi lạm dụng — bài học 6 Gmail Groq bị khoá.)

2. **Graphify** (76.3k★, `safishamsi/graphify`) — biến TOÀN BỘ dự án (code + docs + SQL schema + config + PDF) thành **đồ thị tri thức TRUY VẤN ĐƯỢC**; parse bằng **tree-sitter AST tất định, KHÔNG cần LLM, KHÔNG vector store**, chạy local free. Có sẵn dạng skill cho Claude Code/Cursor/Codex/Gemini CLI.
   - **Ứng dụng:** trị đúng bệnh Sếp than — *"AURA chắp vá đủ thứ"*. Map cả repo AURA thành graph để tôi/Antigravity tra quan hệ thay vì grep mò. Local + no-GPU + free = hợp máy.

3. **prompt-optimizer** (`linshenkx/prompt-optimizer`) — tối ưu **system prompt + user prompt**, có vòng lặp `iterate-prompt`; hỗ trợ OpenAI/Gemini/DeepSeek/Grok/Zhipu/SiliconFlow + endpoint tự chọn.
   - **Ứng dụng:** Sếp từng chê AURA viết truyện kém (ChatGPT cũng nhận xét vậy). Đây là cách nâng chất **không cần đổi model** — đúng mạch Harness Engineering (C-10) + LLM-as-a-Tutor (E). Cắm vào prompt của `story_factory.py` / `reflexion.py`.

**◆ TIER 2 — tham khảo:**

4. **OpenHands** (tiền thân OpenDevin) — nền agent kỹ sư phần mềm tự hành: tự viết code, chạy lệnh, duyệt web, gọi API, mở PR; có Software Agent SDK; chạy Claude/GPT-4o/Gemini/Llama/Qwen.
   - **Ứng dụng:** TRÙNG vai Claude Code + Antigravity mà Sếp đang dùng. Tham khảo SDK nếu muốn AURA tự sửa code chính mình; chưa cần cắm.
5. **aisuite** (Andrew Ng) — giao diện hợp nhất nhiều nhà cung cấp LLM. **TRÙNG** litellm-router AURA đã có → chỉ tham khảo cách trừu tượng hoá.
6. **Astryx** (`facebook/astryx`, Meta) — design system mã nguồn mở (13.000+ app), có **JSON manifest + MCP** giúp agent sinh UI không bịa prop.
   - **Ứng dụng:** hấp dẫn cho web nhưng là **hệ React**, mà lqmeta luật CẤM Tailwind/đi Vanilla CSS → **không hợp** trừ khi đổi kiến trúc. Ưu tiên thấp.

**★★ TIER 0 — món QUAN TRỌNG NHẤT mẻ này (Sếp gửi link 2026-07-23):**

7. **SkillOpt** (`microsoft/SkillOpt`, `pip install skillopt`) — *"Huấn luyện KỸ NĂNG của agent như huấn luyện mạng nơ-ron — có epoch, batch size, learning rate, cổng validation — **NHƯNG KHÔNG ĐỤNG TRỌNG SỐ MODEL**"*. Vòng lặp: rollout → reflect → aggregate → select → update → evaluate. Đa backend (OpenAI/Azure/Claude/Qwen/MiniMax), 6 benchmark, WebUI. **SkillOpt-Sleep**: máy tự tiến hoá **ban đêm** (harvest → mine → replay → consolidate, qua cổng validation held-out), có CLI `skillopt-sleep`. Có sẵn tích hợp Claude Code / Codex / Copilot / Devin / OpenClaw.
   - **Ứng dụng:** đây CHÍNH LÀ thứ Sếp trực giác hỏi hôm 22/07 — *"công nghệ làm AI thông minh hơn mà không cần nâng trọng số"* — và cũng là **kho skill tự tiến hoá** (pattern ECC/Hermes/Voyager) mà ta định làm. Của **Microsoft**, có paper + benchmark, không phải đồ vibe. **Ứng viên số 1 để nâng lõi AURA**: cho `reflexion.py` + kho skill của AURA tự học qua đêm thay vì chờ tôi cắm tay. ⭐

**◆ TIER 2 — dùng được:**

8. **paseo** (`getpaseo/paseo`) — MỘT giao diện chung cho Claude Code, Codex, Copilot, OpenCode, Pi. Sếp đang chạy Claude Code + Antigravity song song → gom về một cửa. (Tác giả solo, hỗ trợ qua Discord.)
9. **mattpocock/skills** — bộ skill *"cho kỹ sư thật, không phải vibe coding"*: nhỏ, dễ sửa, ghép được, chạy với mọi model; cố tình KHÔNG ôm quy trình như GSD/BMAD/Spec-Kit. **Mẫu tốt để viết skill cho AURA.**
10. **loop-engineering** (`cobusgreyling`, `npx @cobusgreyling/loop-init`) — *"Ngừng prompt. Thiết kế VÒNG LẶP. Lấy điểm."* Dựng khung skill/state/budget + chấm điểm "Loop Ready". Đúng triết lý AURA (pipeline cố định + LLM ở điểm mờ).
11. **optimizerDuck** (`itsfatduck`, có README tiếng Việt) — tool tối ưu Windows (hiệu năng/riêng tư), free. **Hợp máy yếu của Sếp** — giải phóng RAM/CPU cho AURA. ⚠️ Loại "tối ưu Windows" luôn có rủi ro tắt nhầm dịch vụ — chỉ dùng phần dọn dẹp, đừng bật hết.

**✕ TIER 3 — không hợp:**
12. **start-ui-web** (`bearstudio`, = "ui start") — starter React/TanStack/**Tailwind**/shadcn/Prisma. lqmeta luật **CẤM Tailwind** (Vanilla CSS) → không hợp trừ khi đổi kiến trúc.
13. **easy-vibe** (`datawhalechina`) — GIÁO TRÌNH vibe-coding tương tác, 10 thứ tiếng **có tiếng Việt**. Tài liệu học, không phải tool. Cho Sếp đọc thì tốt.
14. **RuView** (`ruvnet`) — cảm biến WiFi "nhìn xuyên tường": dùng CSI từ ESP32 phát hiện người/nhịp thở/nhịp tim, nối Home Assistant/Apple Home/Alexa. **Sai domain hoàn toàn** (nhà thông minh, cần mua phần cứng ESP32) — không liên quan xưởng tiền. Ghi lại vì lạ: nó có trạng thái "đang ngủ / bất động bất thường / nguy cơ ngã", về lý thuyết có thể nuôi Health Guard, nhưng phải mua thiết bị.

**❓ VẪN CHƯA TRA ĐƯỢC:** `ai to learn` · `subsvid` · `opencodex` (thiếu link/tên đầy đủ).

---
*Ghi chú: Tài liệu này được tạo ra để lưu trữ các ý tưởng công nghệ tiềm năng. Khi có nhu cầu nâng cấp AURA, có thể tham khảo lại các từ khóa này.*

---

## Đợt 26/07/2026 — esp32-ai · iFixAI · OpenSpace (Claude sàng)

### 1. OpenSpace — HKUDS/OpenSpace 🎯 kỹ thuật hợp nhất, NHƯNG TRÙNG
"Skill Management Layer for AI Agents". MIT, ~7k sao, Python 3.12+ (AURA 3.14 ✅),
chạy qua LiteLLM (AURA đã dùng ✅), local-first, nhúng làm thư viện được.
Làm gì: theo dõi kỹ năng nào THẬT SỰ chạy được qua kết quả task thật, rồi tiến hoá
(FIX sửa kỹ năng hỏng / DERIVED tạo bản chuyên biệt / CAPTURED lưu quy trình thành công).
**Vấn đề: TRÙNG với thứ AURA ĐÃ CÓ** — `core/skillopt_hand.py` + `.skillopt-sleep`
(tiến hoá kỹ năng ban đêm, đã cắm vào daemon) và `factory/reflexion.py` (học từ lỗi).
=> Cắm vào = hệ học-kỹ-năng THỨ BA trong khi doanh thu vẫn 0. Đúng cái AURA_COMMAND
cấm: "CẤM đắp thêm module mới nằm im". **KHÔNG cắm bây giờ.** Để dành khi nào
SkillOpt chứng minh không đủ.

### 2. esp32-ai (nhiều repo cùng tên) 🟡 tham khảo, KHÔNG thay kế hoạch robot
tomik395/ESP32-AI, Ingeimaks/ESP32-AI-Voice-Assistant, AvantMaker/ESP32_AI_Connect...
Đa số là **loa thông minh**: ESP32 + mic + loa → WiFi → cloud AI (STT/LLM/TTS).
**Kiến trúc KHÁC hẳn robot của Sếp:**
- Chúng KHÔNG có camera/thị giác (ESP32 RAM quá nhỏ).
- Chúng BẮT BUỘC online — mất wifi là câm. Đúng cái Sếp muốn tránh.
- Robot của Sếp: điện thoại làm não (có camera + AI local offline), ESP32 chỉ là tuỷ vận động.
=> Giữ nguyên kế hoạch điện-thoại-làm-não. Điện thoại làm giọng nói TỐT HƠN ESP32
(sẵn mic/loa/TTS). `ESP32_AI_Connect` có thể hữu ích nếu sau này muốn ESP32 tự gọi API.

### 3. iFixAI — ifixai-ai/iFixAi 🟡 đúng bệnh, sai thuốc
Bộ chẩn đoán "AI misalignment": 45 bài kiểm (bịa đặt/thao túng/lừa dối/mờ ám),
chấm điểm chữ cái <5 phút, chạy được với OpenAI/Anthropic/Gemini/Bedrock.
Liên quan thật: AURA CÓ bệnh bịa (hỏi Wattpad → bịa WhatsApp; hỏi màn hình → bịa briefing).
**Nhưng:** nó chấm mức độ lệch chuẩn của MODEL, không sửa bug định tuyến của AURA.
Cách chữa đúng đã làm rồi: bắt câu hỏi đi vào DỮ LIỆU THẬT (mắt OCR/vision,
manual_publish_query) thay vì để LLM đoán. Chạy 45 bài kiểm còn tốn API.
=> Ý tưởng hay để tham khảo, **không cắm**.

**Kết luận đợt này: KHÔNG cắm cái nào.** Cả ba đều là hàng thật, nhưng 2 cái trùng
với thứ AURA đã có, 1 cái sai kiến trúc. Chỗ nghẽn vẫn là NGƯỜI MUA, không phải thiếu module.

## Đợt 26/07/2026 (b) — AOS-CE · hello-agents (Sếp tìm qua TikTok)

### `unicity-aos/aos-ce` — 🟡 hàng thật, nhưng là NHÀ phải dọn vào ở
7.4k sao (video TikTok quay lúc 6.5k). Viết bằng **Rust**, cài bằng curl script từ
`aos.unicity.ai/install.sh`, bundle sẵn runtime nên không cần cài Rust.
Làm gì: CLI `aos` + HTTP API + "capsules" (khối chức năng lắp ghép) + tích hợp MCP.
**Vì sao KHÔNG cắm vào AURA:** nó là **MÔI TRƯỜNG cho agent sống trong đó**, không
phải thư viện cắm thêm. AURA đã là một hệ đang chạy (daemon 16 nhịp, MemoryStore,
TOOL_REGISTRY, hàng đợi factory). Dùng AOS = **dọn cả AURA sang nhà mới**, không phải
thêm tính năng. Chưa xác minh được LICENSE. Cài bằng `curl | sh` từ domain lạ ->
thận trọng.

### `datawhalechina/hello-agents` — 🟢 KHÁC LOẠI: đây là SÁCH, không phải framework
"从零开始构建智能体" = *Xây agent từ số 0*. Giáo trình mở của cộng đồng Datawhale,
**miễn phí, có bản tiếng Anh**, dạy nguyên lý + kiến trúc + tự viết framework agent.
**Không cắm vào AURA** (không phải thư viện), nhưng **đáng cho Sếp ĐỌC** — sinh viên
IT năm cuối, hiểu gốc agent có giá trị đi xin việc hơn là cắm thêm một repo nữa.
Link: github.com/datawhalechina/hello-agents

**Kết luận đợt này:** không cắm cái nào vào AURA. hello-agents là thứ duy nhất đáng
lấy — nhưng lấy để HỌC, không phải để lắp.

## 27/07/2026 — OpenMinis (Sếp tìm qua TikTok)

`OpenMinis/OpenMinis` — 2.1k sao, **GPLv3**, iOS + Android. Mã mở thật.

### ⚠️ Hiểu nhầm cần chỉnh: nó KHÔNG chạy AI trên điện thoại
Trang chủ ghi *"private, on-device AI agent"* rất dễ gây nhầm. Đọc kỹ repo:
> *"It's a client application — **not local inference**"*
> *"Offline functionality: **No.** Cloud API access is required."*

Nó gọi Claude/GPT/Gemini **trên mây** bằng API key của người dùng — y hệt phân thân
AURA. Chữ "on-device" là nói về **CÔNG CỤ**, không phải **BỘ NÃO**.
=> **Không giải được** bài toán "điện thoại tự chạy AI". Bài toán đó nằm ở chip
Cortex-A53 thiếu lệnh `sdot` — phần mềm không sửa được silicon. Số đo vẫn nguyên:
Qwen 1.5B = 4 token/s (xem mục đo LLM ngày 26/07).

### 🟢 NHƯNG có thứ thật sự đáng giá — khác thứ tưởng ban đầu
- **Alpine Linux sandbox chạy ngay trên máy** — shell thật trên điện thoại.
- **Browser automation** — điện thoại tự lướt web, thao tác.
- Nối Health / Calendar / Contacts / HomeKit.

Đây là **TAY CHÂN cho điện thoại** — mảng phân thân AURA (`vn.aura.avatar`) hiện
chưa có. Phân thân mạnh phần *não có ký ức* (nối AURA laptop, còn chạy khi mất
mạng nếu cùng LAN); OpenMinis mạnh phần *tay* nhưng mất mạng là chết hẳn.
**Bổ sung nhau, không thay thế nhau.**

### Cảnh báo trước khi thử
1. **GPLv3 = giấy phép lan truyền.** Chép code OpenMinis vào AURA thì AURA buộc
   phải thành GPL. => Dùng như một APP thì được; **đừng bê code vào repo**.
2. Vivo chỉ còn **1.29GB RAM trống** — Alpine sandbox + browser automation sẽ rất
   chật. Muốn xem nó làm được gì thật thì **thử trên Poco X3 trước**.

**Kết luận:** repo đầu tiên trong ~9 cái đợt này có giá trị RIÊNG (không trùng thứ
AURA đã có) — nhưng là thứ để **CÀI THỬ như app**, không phải để cắm vào mã nguồn.

---

## Đợt 29/07/2026 — 20 repo Sếp gửi (Claude sàng, tra GitHub API thật)

Trước đợt này sổ đã có: **openspace** (AOS-CE, đã kết luận không cắm).

### 🟢 ĐÁNG CÀI — 2 cái (lần đầu trong ~30 repo có kết luận "nên dùng")

**`rtk-ai/rtk`** ⭐73.7k · Apache-2.0 · Rust binary
Proxy CLI **cắt 60-90% output bash** mà agent phải đọc. Chặn lệnh shell, nén output
(lọc nhiễu, gộp, khử trùng lặp) trước khi LLM đọc.
- **Cắm 0 dòng code**: `rtk init -g` gắn hook, `git status` tự thành `rtk git status`.
- Hỗ trợ 100+ lệnh (git, pytest, docker, ls/cat/grep), **15 công cụ AI gồm Claude Code**.
- Windows chạy binary gốc, không cần Unix shell. **Không cần cài Rust.**
- Telemetry **TẮT mặc định**, không thu code/đường dẫn/bí mật.
- 👉 **Vì sao đáng:** giảm token = giảm TIỀN THẬT Sếp trả, không phải thêm tính năng.
  Đây là repo đầu tiên qua được cửa "có làm ra tiền / giảm chi phí không".

**`virgiliojr94/book-to-skill`** ⭐11.7k · MIT
Biến PDF/EPUB thành **skill cho Claude Code**: sinh SKILL.md (~4K token) + file từng
chương (~1K, nạp khi cần) + glossary + cheatsheet.
- Chi phí **một lần**: sách 371 trang ≈ $0.96 (Sonnet). Sách 501 trang → 229K token OK.
- Cần `pdftotext` (poppler) hoặc `docling`.
- Hạn chế: sách phải có tiêu đề "Chapter N" rõ ràng mới tự cắt chương được.
- 👉 **Vì sao đáng:** Sếp vừa tải **Hello-Agents 806 trang** về Desktop. Cái này biến
  nó thành thứ tra cứu được thay vì PDF nằm im.

### 🟡 CÓ THỂ XEM — trùng hoặc chưa cấp thiết
- **`diegosouzapw/OmniRoute`** ⭐33.3k MIT — cổng AI 290+ nhà cung cấp (90+ free), 500+
  model, một endpoint. **TRÙNG** LiteLLM router AURA đang dùng. Chỉ đổi nếu router hiện
  tại hỏng.
- **`ayghri/i-have-adhd`** ⭐12.9k MIT — skill ép agent **trả lời thẳng, không chôn đáp
  án**. Hợp với Sếp (hay bị rối khi nhận quá nhiều chữ) hơn là hợp AURA.
- **`KKKKhazix/khazix-skills`** ⭐18.6k MIT — bộ skill tiếng Trung (leader/neat-freak/
  hv-analysis...). Cần đọc kỹ từng skill mới biết hợp không.
- **`anysearch-ai/anysearch-skill`** ⭐4.9k Apache-2.0 — skill tìm kiếm thời gian thực.
  Trùng một phần với scout (job/news/trend) AURA đã có.
- **`braedonsaunders/codeflow`** ⭐4.8k — dán URL GitHub → bản đồ kiến trúc tương tác.
  Hợp để AURA/Sếp nhìn ra cơ thể AURA. **Giấy phép chưa rõ — phải kiểm trước khi dùng.**

### 🔴 KHÔNG HỢP
- **`rustdesk/rustdesk`** ⭐119k — remote desktop. **AGPL-3.0 lan truyền**, và AURA
  không cần điều khiển máy từ xa.
- **`Eugeny/tabby`** ⭐73.6k — **trình giả lập terminal**, không phải TabbyML. Không liên quan.
- **`chenglou/pretext`** ⭐49.5k — thư viện đo/dàn chữ. Việc của UI, không phải agent.
- **`macos-laguna-s2.1`** ⭐150 — benchmark cho model Poolside Laguna. Không áp dụng được.
- **`automanus-io/mcp-server`** ⭐13 — MCP bán hàng WhatsApp. **13 sao = quá non.**
- **`0x0funky/agent-sprite-forge`** ⭐3.5k MIT — sinh sprite 2D/GIF. Vui cho mascot Miku,
  nhưng không ra tiền.

### ❓ KHÔNG TRA ĐƯỢC — cần Sếp gửi link
`egolite` · `img2threejs` · `claude-video` · `video-use` · `palmier-pro` ·
`videofy_minimal` · `cadskills`
GitHub API không tìm ra tên nào khớp. **Không đoán** — có link thì tra tiếp.

**Kết luận đợt:** 2 đáng cài (rtk, book-to-skill), 5 có thể xem, 6 loại, 7 chưa xác minh.
Vẫn giữ nguyên tắc: **chưa cắm gì vào mã nguồn AURA.**

### Bổ sung 29/07 — 7 repo Sếp gửi link (đã tra được)

| Repo | Sao | Giấy phép | Kết luận |
|---|---|---|---|
| `browser-use/video-use` | 18.1k | MIT | 🟡 hay nhưng vướng |
| `earthtojake/text-to-cad` | 11.9k | MIT | 🟢 để dành cho robot |
| `bradautomates/claude-video` | 12.7k | MIT | 🟢 đáng thử |
| `palmier-io/palmier-pro` | 12.8k | **GPL-3.0** | 🔴 loại |
| `img2threejs/img2threejs` | 8.1k | Apache-2.0 | 🟡 ngách |
| `citrolabs/ego-lite` | 6.0k | MIT | 🔴 **loại — có rủi ro** |
| `schibsted/videofy_minimal` | 645 | Apache-2.0 | 🔴 loại |

**🟢 `bradautomates/claude-video`** — cho Claude **XEM được video**: tải, tách khung
hình, chép lời thoại rồi đưa hết cho Claude. Python → chạy Windows được.
👉 Dùng để **soi video đối thủ trên TikTok** và **tự chấm video AURA làm ra** — thứ
AURA đang mù hoàn toàn (đẻ video mà không ai biết nó hay hay dở).

**🟢 `earthtojake/text-to-cad`** — bộ skill cho **CAD, robotics, thiết kế phần cứng**.
Chưa dùng ngay, nhưng **để dành cho dự án robot** (thiết kế khung, giá đỡ in 3D).

**🟡 `browser-use/video-use`** — dựng video bằng agent: cắt từ transcript, bỏ từ đệm
"ừm/à", chèn phụ đề, đổi màu, tự chấm lại chỗ cắt. Đọc transcript (~12KB) thay vì
quét từng khung → tốn ít token.
⚠️ **Vướng 2 chỗ:** cần **ElevenLabs API key (trả tiền)** để chép lời; tài liệu cài
đặt viết cho **macOS**, chưa nói gì về Windows.

**🟡 `img2threejs`** — ảnh → mô hình Three.js procedural. Ngách, chưa thấy đường ra tiền.

**🔴 `citrolabs/ego-lite` — LOẠI, và cần cảnh báo:**
- **macOS-only**, Windows còn nằm trong lộ trình → máy Sếp **không chạy được**.
- Cơ chế của nó: *"agent kế thừa toàn bộ login, cookie, extension, bookmark của bạn"*.
  Tức là **giao thẳng phiên đăng nhập thật cho AI**.
- README **không hề nói** gì về ToS hay chống phát hiện bot.
- 👉 Đây đúng thứ AURA đã cố tình TRÁNH: Payhip/Wattpad/TikTok đều khoá tài khoản khi
  phát hiện bot dùng phiên đăng nhập. Có chạy được cũng **không nên dùng để đăng bài**.

**🔴 `palmier-io/palmier-pro`** — trình dựng video macOS viết bằng **Swift**, lại
**GPL-3.0**. Máy Sếp là Windows → loại thẳng.

**🔴 `schibsted/videofy_minimal`** — 645 sao, **không có mô tả**, cập nhật cuối 13/03.
Tín hiệu quá yếu.

**Tổng 2 đợt (27 repo):** 2 đáng cài (**rtk đã cài**, book-to-skill), 2 đáng thử
(claude-video, text-to-cad để dành robot), còn lại loại hoặc trùng.

---

## 🔧 ĐÃ CÀI 29/07/2026 — `rtk` v0.44.1

Binary Windows từ release chính chủ `rtk-ai/rtk`, để ở `.rtk/` (đã gitignore).

**ĐO THẬT trên chính repo này** (không tin con số quảng cáo 60-90%):

| Lệnh | Thô | Qua rtk | Giảm |
|---|---|---|---|
| `pytest` (153 test) | 1.645 ký tự | **90** | **94%** ✅ |
| `git status` | 1.024 | 622 | 39% |
| `git log -20` | 1.986 | 1.954 | 1% |
| `git ls-files` | 14.538 | 14.538 | 0% |

**Kết luận thật:** nén mạnh ở **output dài + nhiều nhiễu** (log test). Output ngắn,
sạch thì gần như không giảm. Con số 60-90% quảng cáo là **trường hợp tốt nhất**,
không phải mọi lệnh.

⚠️ **BẪY ĐÃ VẤP:** gõ `rtk pytest ...` là lệnh SAI (rtk dùng `rtk test ...`). Lệnh sai
thì rtk **im lặng trả rỗng** — đo ra "giảm 99%" trông rất đẹp nhưng thực chất là
**lệnh hỏng, không chạy gì cả**. Suýt báo cáo nhầm. Luôn xem output thật, đừng chỉ
đếm ký tự.

---

# 📡 ĐỢT SÀNG 06/08/2026 — 66 link (TikTok 42 + Facebook 23 + 1 video tải sẵn)

**Đọc được 51/66** (TikTok 32/42, FB 18/23, local 1/1). Phần còn lại bị TikTok/FB
chặn tốc độ hoặc bài đã gỡ. Cách lấy: `yt-dlp --dump-json --sleep-requests` (KHÔNG
tải video — chỉ tiêu đề + mô tả là đủ phân loại; dùng `--dump-json` chứ đừng `--print`
vì `--print` ghi ra file bằng bảng mã cũ làm **mất dấu tiếng Việt**).

Bộ lọc giữ nguyên như các đợt trước: **hợp máy (i5, 12GB RAM, KHÔNG GPU rời)** +
**ra tiền thật** + **không trùng thứ AURA đã có**.

## ✅ DÙNG NGAY

| Tool | Vì sao |
|---|---|
| **Moonshine** (STT offline) | ⭐ Lấp lỗ hổng CÓ THẬT: 05/08 Sếp gửi file ghi âm tập phỏng vấn mà Claude **không nghe được** vì thiếu khoá Whisper API. Moonshine chạy offline, không GPU, **có tiếng Việt**, nhanh hơn Whisper nhiều lần. Dùng được cả cho phụ đề `story.video`. |
| **HyDE** (kỹ thuật RAG) | ⭐ Thuần prompt, KHÔNG cài gì: bắt LLM bịa một tài liệu giả rồi đem đi tìm → khớp embedding tốt hơn hỏi trực tiếp. Cải thiện độ chính xác khi AURA lục trí nhớ. Rẻ nhất đợt này. |
| **LLM Wiki** (pattern Karpathy) | ⭐ Để AI **tự viết / tự nối / tự dọn** một wiki cá nhân thay vì mỗi lần lại RAG từ đầu. **AURA ĐÃ đi đúng hướng này** (MEMORY.md + file trí nhớ có `[[liên kết]]`) — video xác nhận hướng đúng, và gợi ý phần còn thiếu: **tự DỌN/gộp định kỳ**. |
| **Prompt ESP32 5 phần** | Kỹ thuật viết prompt cho code nhúng: vai trò · ngữ cảnh · nhiệm vụ · ràng buộc · định dạng. Với ESP32 phải nêu rõ board/framework, chân GPIO cụ thể, ràng buộc non-blocking (millis thay delay), giới hạn RAM. Dùng ngay cho việc rover. |

## 🟡 ĐỂ SAU / cần kiểm chứng

- **Chatwoot** — hộp chat góc web, gom Facebook/Instagram/WhatsApp về một chỗ, mã nguồn mở.
  👉 **Đây là món DUY NHẤT trong đợt có đường ra tiền rõ**: dựng + quản lý cho shop = dịch vụ freelance.
  ⚠️ Chính video cảnh báo "đọc kỹ giấy phép rồi hẵng mừng" — phải xem license trước khi nhận tiền.
- **page-agent** (alibaba, 24.7K sao, MIT) — agent GUI chạy **trong chính trang web**, khỏi extension/browser ảo.
  Nhắm đúng nút thắt của AURA: **đăng bài tay** (Wattpad chặn bot bằng debugger-trap, Payhip có Cloudflare).
  ⚠️ Chưa rõ có né được không, và vẫn là **rủi ro ToS** — kiểm chứng trước, đừng cắm vội.
- **PrintFilm** (2.8K sao) — kịch bản → video + truyện tranh động. Trùng mảng `story.video`/`comic.create`. Đáng so sánh xem có hơn không.
- **HuggingFace speech-to-speech** — trợ lý giọng nói chạy cục bộ. Kết hợp được với Moonshine.
- **Chrome DevTools MCP** (Google, 48.2K) — 52 tool DevTools cho coding agent. Hợp Claude Code hơn là AURA.
- **LightOnOCR-2-1B** — OCR 1 tỉ tham số, Apache-2.0, chạy offline. Benchmark đo trên H100 nhưng model 1B có thể chạy CPU (chậm). Cài **khi nào có việc cần**, đừng nạp sẵn.
- **Strix** — AI đóng vai hacker dò lỗ hổng. Chỉ dùng trên hệ thống của chính mình.

## ❌ BỎ

- **Kimi K3 in C** — GPU: không cần ✅, RAM 8,24GB ✅ (máy có 12GB). **NHƯNG hết chỗ ổ cứng**:
  2,78 nghìn tỉ tham số cần hàng trăm GB, máy chỉ còn **104GB trống** (C: 40 + D: 64). Loại vì DUNG LƯỢNG, không phải vì GPU.
  ⚠️ Bài học: lần đầu đọc bản mất dấu, Claude gạt luôn "chắc cần GPU" — **SAI**. Phải đọc kỹ rồi mới kết luận.
- **Three.js / website 3D / làm game** — sai hướng, không ra tiền cho Sếp lúc này.
- **GoProxy · n8n · bitchat · automation testing** — không có bài toán tương ứng (AURA tự động hoá bằng code rồi).
- **Quảng cáo trá hình**: Google Drive 5TB, "AI Storage Scan", Filmora, LayerProof.
- **Tin tức**: Grok/Elon Musk, case study Klarna, "AI suy luận vô hình" — đọc cho biết, không phải công cụ.

### ⚠️ Mẫu cần cảnh giác: video GIẤU TÊN TOOL
Khoảng **5 bài Facebook** (kênh "AI xàm xí" và tương tự) giật tít kiểu *"Tool Open Source
Này!"*, *"Công Cụ Miễn Phí Giúp AI..."* mà **cố tình không nói tên** để ép người xem
bình luận. Không có tên thì không thẩm định được → coi như **không có thông tin**, bỏ qua.

## 📚 HỌC — cho SỰ NGHIỆP của Sếp (không phải cho AURA)

- **System Design Primer** (361K sao) — lộ trình thiết kế hệ thống lớn + thẻ Anki. Hay bị hỏi khi **phỏng vấn lập trình viên**.
- **Khoá AI của Microsoft** — miễn phí, **có tiếng Việt**, lộ trình 12 tuần.
- **"Hiểu sâu về AI Agent"** (27K sao) — sách tiếng Việt + 93 bài code chạy thật, kỹ thuật "Harness".
- **VisuAlgo** — trực quan hoá thuật toán. **Full-stack roadmap** — lộ trình nghề.

## 🧭 NHẬN XÉT CHUNG ĐỢT NÀY

Khác hẳn đợt 11/07 (nghiêng về **sản phẩm bán được** → ra coloringbook.factory). Đợt này
**90% là hạ tầng agent / trí nhớ / trình duyệt** — hay về kỹ thuật nhưng **ít đường ra tiền**.

Nhắc lại nguyên tắc đã chốt từ trước: **AURA thừa tính năng, thiếu người mua.** Nút thắt
là ĐẦU RA + PHÂN PHỐI, không phải thiếu tool. Nên đề xuất chỉ lấy **3 món**, tất cả đều
rẻ và lấp lỗ hổng có thật, không mở mặt trận mới:

1. **Moonshine** — vá đúng chỗ hôm qua đã gãy (không nghe được file ghi âm).
2. **HyDE + tự dọn trí nhớ** — thuần kỹ thuật, không cài gì, làm AURA nhớ chính xác hơn.
3. **Chatwoot** — món duy nhất có đường ra tiền; nhưng phải đọc license trước.

## 🔄 BỔ SUNG sau lượt vét cuối (TikTok 38/42, tổng đọc được **57/66**)

Vét thêm 6 video, trong đó **2 cái làm đổi trọng số kết luận**:

- ⭐ **Self-RAG** (paper ICLR 2024, Akari Asai — UW/Meta FAIR): 4 "reflection token"
  `[Retrieve]` · `[IsREL]` · `[IsSUP]` · `[IsUSE]` — dạy model **tự quyết CÓ NÊN tra cứu
  không**, rồi **tự chấm** đoạn vừa lấy có liên quan / có được chứng minh / có hữu ích.
  → Ghép rất hợp với **HyDE**: HyDE lo *hỏi cho trúng*, Self-RAG lo *có nên hỏi + tin được không*.
- ⭐ **ZeroMem** — "bộ nhớ AI tốn 0 token vẫn đánh bại tất cả".
- **CLAUDE.md có thật sự giúp AI code giỏi hơn?** — nghiên cứu về hiệu quả file hướng dẫn (AURA có CLAUDE.md + MEMORY.md).
- **Ruflo** — framework AI Agent mã nguồn mở. 🟡 nghi trùng `core/crew.py`.
- **Autoresearch** — AI tự tối ưu model lúc mình ngủ. 🟡 trùng ý **SkillOpt** đã cắm.
- Web tạo giọng đọc miễn phí — 🟡 AURA đã có edge-tts.

### 🎯 KẾT LUẬN CẬP NHẬT

Mạch **TRÍ NHỚ** giờ có **4 video độc lập** cùng chỉ một chỗ: HyDE · LLM Wiki (Karpathy) ·
ZeroMem · Self-RAG. Khi 4 nguồn khác nhau cùng nói một hướng thì đó không còn là trend
vặt — **đây là hướng đáng làm nhất của đợt này**, và nó **không tốn tiền, không cần GPU,
không cài framework** (toàn kỹ thuật + prompt).

Đề xuất chốt lại còn **3 việc**, xếp theo thứ tự nên làm:
1. **Moonshine** — vá lỗ hổng có thật (không nghe được file ghi âm của Sếp).
2. **Nâng trí nhớ AURA** = HyDE (hỏi trúng) + Self-RAG (biết khi nào cần tra + tự chấm)
   + tự dọn wiki. Ba kỹ thuật, một mặt trận, chi phí ~0.
3. **Chatwoot** — món duy nhất có đường ra tiền (dịch vụ cho shop), nhưng đọc license trước.

## 📥 9 LINK SẾP ĐỌC HỘ (bổ sung 06/08) — đủ 66/66

**TikTok:** `ai-agent-book` (Lý Bác Kiệt, 27K sao, tiếng Việt, 93 bài code chạy thật,
kỹ thuật **"Harness"**) · **ffmpeg** · `awesome-llm-apps` + **deeptutor** + **officeCLI**
· `awesome-python`.
**Facebook:** `badclaude` · **Trellis** · **8 repo DevOps** (Infisical, Coolify, Buildah,
Ctrlplane, Coroot, Dozzle, Groundcover, Dockprom) · web `troisinh.com` · repo `affaan-m/ECC`.

Đánh giá:
- **ai-agent-book** ⭐ — miễn phí, TIẾNG VIỆT, 93 bài thực hành. Kỹ thuật "Harness" đúng
  thứ Claude/AURA đang làm. Học được cho cả Sếp lẫn Claude.
- **officeCLI** 🟡 — AURA đang sinh .docx/.pptx (giáo án TEKY); có CLI thao tác Office thì tiện.
- **deeptutor** 🟡 — AI gia sư; nối được với hướng dạy học TEKY tháng 9.
- **ffmpeg** — AURA **đã dùng nặng** rồi (video_dub, story.video, phụ đề). Xem để lấy mẹo, không phải cái mới.
- **awesome-llm-apps / awesome-python** 📚 — danh mục tham khảo, tra khi cần.
- **8 repo DevOps** ❌ — TOÀN BỘ dành cho **server/Docker/Kubernetes nhiều máy**. AURA chạy
  **một laptop**, không cluster → không có bài toán tương ứng. Riêng **Infisical** (quản lý
  secret) chạm đúng nỗi đau thật của AURA (~20 API key lọt git history, token trong .env),
  **nhưng giải pháp quá nặng** cho 1 máy — cách đúng vẫn là thu hồi key cũ + giữ .gitignore
  chuẩn, không phải dựng thêm hạ tầng.
- **Trellis** ❌ — sinh tài sản 3D, cần GPU rời (đợt 11/07 đã loại TRELLIS.2 vì lý do này).
- **badclaude / troisinh.com / affaan-m/ECC** ❓ — chưa đủ thông tin để thẩm định.
  ⚠️ Riêng `badclaude`: nếu là công cụ **bẻ khoá/vượt rào an toàn của Claude** thì Claude
  không hỗ trợ cắm; cần biết nó thật sự là gì trước.

---

# 🎯 BẢNG CHỐT — tiêu chí đã nới thành "HỮU DỤNG VỚI AURA LÀ DUYỆT"

## Ưu tiên 1 — vá lỗ hổng CÓ THẬT
| # | Việc | Vì sao gấp |
|---|---|---|
| 1 | **Moonshine** (STT offline, tiếng Việt) | 05/08 Claude **không nghe được** file ghi âm tập phỏng vấn của Sếp vì thiếu khoá Whisper. Vá đúng chỗ đã gãy |
| 2 | **Nâng trí nhớ**: HyDE + Self-RAG + tự dọn wiki | 4 video độc lập cùng chỉ hướng này. Thuần kỹ thuật, chi phí ~0 |

## Ưu tiên 2 — hợp AURA, rẻ
| # | Việc | Vì sao |
|---|---|---|
| 3 | **Strix** dò lỗ hổng CHÍNH AURA | Giáo trình AURA ghi: dashboard 8766 có **30 route không xác thực** = chỗ dễ vỡ nhất. Chưa ai soi kỹ |
| 4 | **page-agent** | Nhắm nút thắt đăng tay (Wattpad/Payhip chặn bot). ⚠️ kiểm ToS trước |
| 5 | **Chatwoot** | Đường ra tiền rõ nhất đợt này (dịch vụ cho shop). ⚠️ đọc license |

## Ưu tiên 3 — giúp CLAUDE làm việc tốt hơn
| # | Việc |
|---|---|
| 6 | **Chrome DevTools MCP** (Google, 48.2K) — 52 tool DevTools cắm vào Claude Code |
| 7 | **ai-agent-book** — kỹ thuật "Harness", tiếng Việt, miễn phí |
| 8 | **superpowers · CLAUDE.md research · QM · OpenWork** — điểm danh, xem khi rảnh |

## Ưu tiên 4 — cài KHI CẦN (đừng nạp sẵn thành rác)
**LightOnOCR** (OCR) · **PrintFilm** (so với story.video) · **HF speech-to-speech** ·
**officeCLI** · **deeptutor** · **Ruflo/Autoresearch** (so với crew.py/SkillOpt) ·
**awesome-llm-apps / awesome-python** (tra cứu).

## ❌ BỎ HẲN
**Kimi K3 in C** (ổ đĩa: cần ~347GB ở 1-bit, máy chỉ còn **186,5GB** — C 39,9 + D 63,7 +
F 82,9; **không có ổ E**) · **Trellis** (GPU) · **8 repo DevOps** (không có cluster) ·
**Three.js · n8n · GoProxy · bitchat · automation testing** (không có bài toán) ·
quảng cáo trá hình (Drive 5TB, AI Storage Scan, Filmora, LayerProof) · tin tức
(Grok/Elon, Klarna) · **~5 bài giấu tên tool** để câu bình luận.

---

## IV. Bổ sung từ 28 Tài liệu / Video Facebook (Nghiên cứu ngày 10/08/2026)

> **Mục đích:** Bóc tách toàn bộ công nghệ, công cụ AI, repo mã nguồn mở và kỹ thuật tự động hóa thực chiến từ 28 liên kết do người dùng cung cấp, phân loại theo nhóm ứng dụng trực tiếp cho `AURA_OS_v2` và hệ sinh thái liên quan.

> **ĐÍNH CHÍNH KIỂM CHỨNG 11/08/2026:** Phần IV là **sổ tuyên bố rút ra từ
> video**, không phải kết quả thử nghiệm. URL gốc đã được khôi phục vào
> `data/tech_evidence/video_sources.json`; 28 nguồn thuộc lô chính và 6 URL dư
> được tách riêng để không gán nhầm. Việc lấy được tiêu đề/metadata chỉ chứng
> minh URL còn truy cập được, không chứng minh công nghệ hoạt động. Một công
> nghệ chỉ được gọi là đã thử khi có lệnh chạy, mã thoát và artifact có SHA-256
> trong `data/tech_evidence/registry.json`.

### 1. Nhóm Lập trình AI, Dựng Web & Tự động hóa Code (AI Coding & Web Gen)

- **AI Website Cloner (`ai-website-cloner-template` / JCodesMore) [Link 01]:**
  - *Cơ chế:* Bộ khung 5 giai đoạn (Reconnaissance -> Foundation -> Component Specs -> Parallel Build trong git worktree -> Assembly & QA so sánh visual diff).
  - *Công nghệ:* Next.js 16 (React 19, TypeScript strict), shadcn/ui, Tailwind CSS v4 oklch design tokens. Hỗ trợ Claude Code (Opus), Codex, Cursor, Gemini CLI.
  - *Ứng dụng AURA:* Áp dụng pipeline Reconnaissance & Design Token extraction cho các dự án Web Frontend (như portal Liên Quân) để tự động hóa clone UI pixel-perfect.

- **Gesso (AI Sketch-to-UI / Rough ideas to Polished UI) [Link 04]:**
  - *Cơ chế:* Biến nét vẽ phác thảo tay hoặc mockup thô sơ thành giao diện UI hoàn chỉnh, tự động đồng bộ theo Design System sẵn có của dự án.
  - *Ứng dụng AURA:* Rút ngắn thời gian từ ý tưởng giao diện sơ bộ thành code component UI chuẩn.

- **Claude Code & Bí kíp Lập trình Agentic [Link 06, Link 15, Link 21]:**
  - *Cơ chế:* Công cụ CLI agentic mới nhất của Anthropic, tương tác trực tiếp terminal, chạy test, sửa lỗi, tích hợp kiểm thử tự động.
  - *Ứng dụng AURA:* Mô hình mẫu cho cơ chế tự chữa lỗi (Self-healing) và pair-programming đa tác nhân trong AURA.

- **AI Tạo Website & Sàn TMĐT Tự động [Link 16, Link 17, Link 18, Link 23]:**
  - *Cơ chế:* Tự động dựng Fullstack Web / E-commerce trong 5 phút từ prompt, tích hợp database, thanh toán và giỏ hàng.
  - *Ứng dụng AURA:* Tích hợp vào module tạo Landing Page tự động bán sản phẩm số / Ebook / Truyện tranh do AURA tự viết.

- **Figma to React Code & Top 10 VS Code AI Extensions [Link 20, Link 26]:**
  - *Cơ chế:* Chuyển đổi trực tiếp wireframe Figma thành JSX/CSS sạch, các tiện ích AI tối ưu snippet và refactor code.

### 2. Nhóm Tối ưu Token, Phá bỏ Giới hạn & Hạ tầng Agent (Agent Infrastructure)

- **OmniRoute & 9router (Tối ưu hóa Token & Phá vỡ Rate Limit) [Link 03]:**
  - *Cơ chế:* Load-balancing thông minh qua nhiều provider, tự động chuyển đổi mô hình (fallback routing), nén prompt và bypass rate limit.
  - *Ứng dụng AURA:* Giải quyết triệt để bài toán nghẽn API Key và chi phí token khi AURA chạy các tác vụ truyện dài kỳ hoặc crawl dữ liệu lớn.

- **N8N & Tự động hóa Workflow Không Giới Hạn [Link 11, Link 12, Link 17, Link 22]:**
  - *Cơ chế:* N8N self-hosted kết hợp AI Agent node: Webhook -> Trích xuất dữ liệu -> AI xử lý -> Đẩy kết quả đa kênh (Telegram, Discord, Database, Google Sheets).
  - *Ứng dụng AURA:* Làm xương sống cho quy trình tự động phân phối nội dung, báo cáo tiến độ và cào dữ liệu định kỳ.

- **Thao tác Tự động với Trình duyệt (Browser Automation Agent) [Link 13, Link 19]:**
  - *Cơ chế:* AI tự mở trình duyệt, đăng nhập, cào dữ liệu, điền form và tương tác như người thật (tương tự Chrome DevTools / Puppeteer MCP).
  - *Ứng dụng AURA:* Nâng cấp khả năng tự động cào tin tức giải đấu, thông số meta game hoặc đăng bài tự động lên mạng xã hội.

- **Cài đặt DeepSeek Chạy Local Offline [Link 28]:**
  - *Cơ chế:* Chạy mô hình ngôn ngữ lớn (LLM) mã nguồn mở qua Ollama / vLLM ngay trên phần cứng cục bộ, không tốn tiền API và bảo mật 100%.
  - *Ứng dụng AURA:* Dùng làm não bộ phụ trợ cục bộ (Local Brain) cho các tác vụ phân loại, tóm tắt nhanh mà không tốn credit đám mây.

### 3. Nhóm Sản xuất Video, Âm thanh & Hoạt hình 3D (AI Media & Animation)

- **Tự động Dịch Video Đa Ngôn Ngữ & Lồng Tiếng [Link 16, Link 22, Link 24]:**
  - *Cơ chế:* Bóc tách giọng nói (Whisper/ASR), dịch thuật giữ nguyên ngữ cảnh, nhân bản giọng đọc (Voice Cloning) và khớp khẩu hình (Lip-sync).
  - *Ứng dụng AURA:* Mở rộng module `video_dub` của AURA để tự động chuyển ngữ các video truyện ngắn / recap sang tiếng Anh/quốc tế để kiếm tiền đa quốc gia.

- **Tạo Video Hoạt hình 3D & Biến Text Thành Video [Link 19, Link 23, Link 25]:**
  - *Cơ chế:* Tạo chuyển động hoạt hình 3D, phối cảnh camera, biến cốt truyện thành chuỗi phân cảnh video sinh động.
  - *Ứng dụng AURA:* Chuyển thể các tác phẩm truyện chữ của AURA thành Video Shorts / TikTok hoạt hình tự động.

- **Tải Video 4K & Tối ưu Xuất Video CapCut Không Bị Mờ [Link 09]:**
  - *Cơ chế:* Kỹ thuật cấu hình bitrate, khung hình và upscale trước khi dựng video ngắn.

### 4. Nhóm Đồ họa, Thiết kế & Phần cứng 3D (Hardware & Design)

- **Công nghệ In 3D Đa Màu & Trong Suốt Toàn Phần (Sailner Full-Color 3D) [Link 02]:**
  - *Cơ chế:* Máy in 3D công nghiệp kết hợp dải màu trong suốt và texture mapping trong 1 lần in đơn.

- **Tự động Viết Bài SEO Chuẩn 100% Điểm Human-Score [Link 27]:**
  - *Cơ chế:* Quy trình prompt chống phát hiện AI (AI Detection Bypass), tối ưu từ khóa LSI, cấu trúc H1-H6 chuẩn On-page.
  - *Ứng dụng AURA:* Áp dụng ngay cho module viết bài phân tích meta game và bài viết kiến thức tự động trên web LQMeta.

- **Kho Tài liệu AI & Nhóm Cổ Máy Lỗ [Link 07, Link 10]:**
  - *Tài nguyên:* Tổng hợp các kho prompt, workflow n8n chia sẻ từ cộng đồng.


---

## V. Bổ sung từ 5 Video TikTok — tuyên bố cần kiểm chứng (Nghiên cứu ngày 10/08/2026)

> **Mục đích:** Bóc tách 5 công nghệ và kiến trúc AI đột phá từ kênh TikTok chuyên sâu (`@cunghocainha`, `@agi.2027`, `@beeknoeeai`, `@aidev.repo`, `@ainius.net`), tập trung vào phân quyền Agent, điều khiển bằng giọng nói và thuật toán giữ chân người xem.

### Trạng thái kiểm chứng lại ngày 11/08/2026

| Video gốc | Điều video nói tới | Kết quả hiện tại |
|---|---|---|
| `@agi.2027/7670858051963931911` | AVD, APV và retention | **ĐÃ ĐỌC NGUỒN YOUTUBE CHÍNH THỨC.** `A.B.D` là thuật ngữ sai; đúng là AVD/APV. CTR vẫn là chỉ số chính thức, còn Shorts Feed dùng thêm chose-to-view, AVD, APV và tín hiệu hài lòng. Không có bằng chứng cho câu “APV luôn có trọng số cao nhất”. |
| `@aidev.repo/7669836232339377429` | Comp AI CRM (`trycompai/crm`) | **ĐÃ XÁC ĐỊNH REPO + CODE SMOKE GIỚI HẠN.** Repo MIT có agent, hàng đợi và tool thật; test thuần hàng đợi đạt 7/7. Chưa chạy Postgres, UI, model hay E2E nên không được gọi là “vận hành hoàn toàn bởi AI”. |
| `@ainius.net/7671522624765283602` | Cloudflare OS / sandbox agent | **ĐÃ XÁC MINH REPO + SOURCE TEST.** 40/40 test mã nguồn đạt sau khi loại sai khác CRLF; cài phụ thuộc chưa hoàn tất trong 5 phút và chưa chạy toàn stack. Dự án tự ghi early access/heavy development. |
| `@beeknoeeai/7671851855860731144` | `qwen-audio-agent` | **ĐÃ CÀI CÔ LẬP + SMOKE CLI/SETUP.** CLI 1.8.1 và adapter Codex sẵn sàng ở chế độ đọc; chưa thử microphone → Codex. Dịch vụ nền Gateway chưa hỗ trợ Windows và audio environment mặc định còn thiếu cấu hình. |
| `@cunghocainha/7671557342277946645` | ContinualSkillBench | **ĐÃ XÁC ĐỊNH PAPER + REPO, CHƯA TÁI LẬP BENCHMARK.** Đây là benchmark đánh giá học liên tục, không phải engine tự tiến hóa. Kết quả paper còn cho thấy context-only 0,605 xấp xỉ explicit skill 0,602. |

### 1. `qwen-audio-agent` (Điều khiển Claude Code & AI Agent bằng GIỌNG NÓI) [TikTok #4]
- **Repo:** `github.com/QwenAudio/qwen-audio-agent` (⭐ 1.7k+ sao, Apache-2.0, Qwen Team).
- **Cơ chế:**
  - Runtime giọng nói (Voice Runtime) cắm trực tiếp ngay trước con Agent đang chạy.
  - Có các adapter ACP cho agent ngoài; adapter Codex được CLI 1.8.1 nhận diện
    ở chế độ cấu hình chỉ đọc. Phép thử này chưa chứng minh luồng âm thanh.
  - Cài đặt cực nhanh: `npm i -g qwen-audio-agent`.
- **Ứng dụng cho AURA:**
  - **TRÚNG ĐÍCH:** Cho phép người dùng ra lệnh trực tiếp cho AURA hoặc Claude Code bằng giọng nói (Voice-to-Command) khi đang bận tay, biến AURA thành trợ lý ảo đúng nghĩa "Jarvis".
- **Giới hạn đã đo:** bản `1.8.1` mở được CLI, `tui --help`, `webui --help` và
  cấu hình backend Codex trong môi trường cô lập. Chưa mở microphone, chưa nối
  realtime frontend và chưa giao một việc thật cho Codex bằng giọng nói. Trên
  Windows, lệnh trạng thái báo background Gateway service chưa được hỗ trợ;
  audio bridge mặc định cũng chưa có môi trường Python phù hợp. Vì vậy đây mới
  là `SMOKE_TESTED` cho CLI/setup, không phải `ADOPTED` hay voice E2E.

### 2. Cloudflare OS — Workspace AI & Gatekeeper [TikTok #3]
- **Kiến trúc:** Workspace năng suất AI chạy trên Workers/workerd; không phải
  hệ điều hành máy tính. Repo thuộc Cloudflare và dùng Apache-2.0.
- **Cơ chế:**
  - Gadgets chạy trong sandbox; Gatekeepers cấp quyền theo capability và có thể
    yêu cầu người dùng phê duyệt hành động nhạy cảm.
- **Ứng dụng cho AURA:**
  - **BÀI HỌC KIẾN TRÚC:** Học mô hình capability/Gatekeeper cho các công cụ
    AURA; không bê nguyên stack Workers/TypeScript vào hệ Python hiện tại.
- **Giới hạn đã đo:** test mã nguồn `40/40` đạt sau khi sửa riêng checkout audit
  để không đổi LF thành CRLF. Cài `pnpm` tải 639 package nhưng chưa hoàn tất
  bước link trong 5 phút; chưa build, chưa chạy local hay deploy. Dự án tự ghi
  early access/heavy development, nên giữ `READ`, chưa nâng runtime.

### 3. ContinualSkillBench — Benchmark học kỹ năng liên tục [TikTok #5]
- **Danh tính:** Paper `arXiv:2608.03874` và repo tác giả
  `gtynnn060110-hash/continual-skill-bench-final` (Apache-2.0).
- **Cơ chế:**
  - So sánh agent làm task độc lập với agent làm chuỗi task có context hoặc
    kho skill được duy trì rõ ràng; bản paper dùng 5 miền × 100 subtasks.
- **Ứng dụng cho AURA:**
  - Dùng thiết kế Independent vs Sequential và baseline context-only để kiểm
    tra AURA có thật sự học skill hay chỉ được lợi vì còn lịch sử trong context.
- **Giới hạn đã đo:** paper báo tăng ở 14/15 tổ hợp và +16,9% tổng hợp, nhưng
  context-only `0,605` gần như ngang explicit skill `0,602`; chính kết quả này
  bác bỏ việc coi “tự ghi SKILL.md” là tiến hóa đã được chứng minh. Máy chỉ
  compile syntax repo thành công; thiếu Docker/model/API nên chưa tái lập
  benchmark. Giữ `READ`, không coi đây là engine đã nạp.

### 4. Comp AI CRM — CRM thiết kế cho Agent [TikTok #2]
- **Danh tính:** `github.com/trycompai/crm`, MIT, bản kiểm tra `v1.9.0`.
- **Cơ chế đã thấy trong mã:**
  - Next.js + NestJS/tRPC + Prisma/Postgres; agent riêng có hàng đợi lease,
    retry/budget, ghi bằng chứng, cập nhật field và lên lịch kiểm tra lại.
- **Ứng dụng cho AURA:**
  - Nâng cấp module Freelance Scout & Digital Product Sales: Tự động chăm sóc độc giả mua Ebook / gói dịch vụ truyện của AURA.
- **Giới hạn đã đo:** test thuần hàng đợi `7/7` đạt; kiểm tra tĩnh các file agent
  cốt lõi đạt. Cài phụ thuộc quá 185 giây nên đã dừng; máy không có Docker và
  generated Prisma client, vì vậy chưa chạy DB, migrations, UI, agent/model hay
  E2E. Repo mới tạo cuối 07/2026 nên độ trưởng thành chưa được chứng minh. Nâng
  từ `BLOCKED` lên `READ` + limited code smoke, không phải `ADOPTED`.

### 5. YouTube: AVD, APV, CTR và Retention [TikTok #1]
- **Cơ chế:**
  - `A.B.D` không phải thuật ngữ YouTube; đúng là **Average View Duration
    (AVD)** và **Average Percentage Viewed (APV)**. Shorts Feed còn dùng tỷ lệ
    chọn xem thay vì bỏ qua, likes/dislikes và khảo sát hài lòng. CTR vẫn là
    chỉ số chính thức cho thumbnail impressions; CTR cao nhưng AVD thấp có thể
    là clickbait và ít được đề xuất hơn.
- **Ứng dụng cho AURA:**
  - Dùng retention graph, AVD và APV để tìm điểm rơi rồi A/B test hook, nhịp kể
    và độ dài. Không đặt mục tiêu “>80%” như chân lý và không coi tối ưu một chỉ
    số là công thức bảo đảm phân phối.
