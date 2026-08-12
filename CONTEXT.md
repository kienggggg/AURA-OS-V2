# CONTEXT.md — Hiến Pháp Kỹ Thuật của AURA OS v2

> **Global Context bắt buộc cho MỌI Agent** (CoderAgent, EvolutionEngine, Orchestrator,
> và bất kỳ code nào AURA tự sinh hoặc thực thi). Triết lý: **Shift-Left Security** —
> kỷ luật bảo mật từ trong trứng nước, không vá lỗi về sau. Mọi dòng code phải coi
> tài liệu này là luật tối cao; khi xung đột với yêu cầu nhất thời, **luật này thắng**.

---

## 0. Nguyên tắc tối thượng

1. **An toàn > Tính năng.** Thà từ chối/chặn còn hơn chạy một thao tác rủi ro chưa được duyệt.
2. **Không tin code tự sinh.** Mọi code do LLM sinh ra đều phải qua cổng kiểm (AST + sandbox + người duyệt) trước khi nạp.
3. **Con người là chốt chặn cuối.** Mọi tác dụng phụ (tải, ghi file, cài lib, gọi tiền) phải qua Human-in-the-loop (VIBE DIFF).
4. **Minh bạch.** Mỗi quyết định quan trọng phải ghi vết (trace/log) để soi lại được.

---

## 1. Bí mật & Khoá (Secrets)

- **TUYỆT ĐỐI KHÔNG hardcode** API key, token, mật khẩu, chuỗi kết nối trong source. Bài học: key Google từng bị lộ vì hardcode.
- Mọi bí mật đọc qua `core/config.py` (`settings`), nguồn duy nhất là `.env` / biến môi trường.
- Dùng `SecretStr`; không `print(settings)` lộ khoá; không log giá trị khoá.
- Trước khi gửi payload ra cloud/đàn anh: **redact** (che key/token/tên người dùng) qua `core/redact.py`.

## 2. Xử lý lỗi (Exception Handling)

- **Luôn** bọc logic tool trong `try/except`. Tool **không bao giờ** ném exception ra ngoài — gói vào `ToolResult.failure(...)`.
- Không `except: pass` câm lặng. Bắt lỗi phải log nguyên nhân và trả thông điệp hữu ích.
- Vành đai phụ trợ (chẩn lỗi, ghi UI, recall memory) nổ **không được làm sập** luồng chính — nuốt lỗi có chủ đích + log WARNING.
- Phân biệt lỗi người-dùng-sửa-được (thiếu tham số) vs lỗi hệ thống (mạng, thiếu lib) và báo rõ.

## 3. Hợp đồng Tool (Tool Contract)

- Mọi tool tuân thủ: `fn(**parameters) -> ToolResult` (`core/schemas.ToolResult`).
- Entrypoint đặt tên `tool_<tên>`; có docstring nêu rõ tham số + tác dụng phụ.
- Trả `ToolResult.success(...)` / `ToolResult.failure(...)`; đính `artifacts` khi sinh file.
- Skill tuân Progressive Disclosure: `SKILL.md` (Level 1-3) tách khỏi `scripts/` (Level 4, nạp trễ).

## 4. Kiểm thử trước (TDD)

- Tính năng/tool mới: **viết test/kịch bản kiểm trước hoặc song song**, không “code rồi tính sau”.
- Mỗi tool cần tối thiểu: 1 ca thành công, 1 ca tham số sai, 1 ca lỗi ngoại lệ (mạng/lib).
- Code tự sinh phải qua `evolution/gate.py` (AST + lint) và `Sandbox.smoke_test` **trước** khi báo ra UI.
- Không merge/nạp code khi test còn đỏ hoặc cú pháp còn lỗi.

## 5. Mẫu CẤM tuyệt đối (Forbidden Patterns)

Bị `ASTValidator` chặn (BLOCK) — code tự sinh **không được** chứa:

- Thực thi lệnh OS / mã động: `os.system`, `subprocess`, `popen`, `spawn*`, `eval`, `exec`, `compile`, `__import__`.
- Xoá phá: `shutil.rmtree`, `os.remove`, `unlink`, `rmdir`, `kill`.
- Thoát sandbox qua dunder: `__globals__`, `__builtins__`, `__subclasses__`, `__bases__`, `__code__`, `__class__`, `__mro__`, `__dict__`.
- Import nguy hiểm: `ctypes`, `socket`, `marshal`, `multiprocessing`, `pty`.
- Đường dẫn `..` (path traversal) hoặc trỏ thư mục hệ thống (`/etc`, `/usr`, `C:\Windows`...).

Module **cảnh báo** (cần người duyệt để ý): `os`, `sys`, `shutil`, `importlib`, `pickle`, `requests`, `urllib`, `http`.

## 6. Đặc quyền tối thiểu (Least Privilege)

- Tool chỉ xin đúng quyền cần làm việc; không mở rộng phạm vi “cho chắc”.
- Ghi file chỉ trong thư mục dữ liệu của AURA (`data/...`), không ghi ra hệ thống.
- Network: chỉ tới đích cần thiết; tôn trọng proxy/timeout/retry có giới hạn.

## 7. Kiểm tra đầu vào (Input Validation)

- Validate mọi input ngoài (URL phải `http/https` + có domain; số chương > 0; v.v.).
- Không tin tham số do LLM bóc; chuẩn hoá qua schema (pydantic) trước khi dùng.
- Chuỗi đưa vào đường dẫn file phải được làm sạch (chống path traversal).

## 8. Human-in-the-loop (VIBE DIFF)

- Trước khi chạy tool có tác dụng phụ: dịch ý định ra ngôn ngữ tự nhiên (`core/vibe_diff.py`) và **xin Sếp duyệt**.
- Giai đoạn này: **mọi** tool (kể cả read-only) đều qua cổng VIBE DIFF; không tool nào auto-run.
- Việc trả phí (đàn anh cloud) phải qua BudgetGuard + Sếp duyệt.

## 9. Mô hình hoá mối đe doạ (STRIDE) — Shift-Left

Trước khi code một tính năng mới, chạy `security.stride` để soi 6 nhóm rủi ro:

| Chữ | Mối đe doạ | Câu hỏi cốt lõi |
|-----|------------|-----------------|
| **S** | Spoofing (giả mạo) | Ai gọi? Có cần xác thực danh tính không? |
| **T** | Tampering (sửa đổi) | Dữ liệu/đường dẫn/tham số có bị chỉnh trái phép được không? |
| **R** | Repudiation (chối bỏ) | Có ghi log/audit để truy vết hành động không? |
| **I** | Information Disclosure (lộ tin) | Có rò rỉ secret/PII ra log/cloud/output không? |
| **D** | Denial of Service (từ chối dịch vụ) | Có vòng lặp/timeout/giới hạn tài nguyên không? |
| **E** | Elevation of Privilege (leo thang) | Có thực thi lệnh/leo quyền/chạy mã động không? |

## 10. Phụ thuộc (Dependencies)

- Thư viện mới phải khai báo (`# AURA-DEPS: ...`) và qua phê duyệt + allowlist của `DependencyInstaller`.
- Ghim phiên bản ở môi trường thật; không tự ý kéo gói lạ.

---

### Quy trình bắt buộc cho code AURA tự sinh

```
CoderAgent.generate
  └─► CodeGate (AST cú pháp + ASTValidator an ninh)  ──fail──► REMEDIATION LOOP (tự sửa)
  └─► Sandbox.smoke_test (cô lập)                     ──fail──► REMEDIATION LOOP (tự sửa)
  └─► (đạt cổng) ─► Installer (allowlist) ─► VIBE DIFF người duyệt ─► hot-reload registry
```

> Code chưa qua cổng **không bao giờ** được lộ ra Avatar UI để xin duyệt. Tự sửa trong
> im lặng tối đa N lần; hết lượt mà vẫn lỗi thì báo cáo thất bại trung thực, kèm lý do.
