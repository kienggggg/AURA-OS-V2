---
name: knowledge.ingest
description: "AURA tự đến thư viện đọc sách" — nuốt tài liệu (URL / file txt·md·pdf / văn bản dán thẳng), cắt mảnh, lưu vào kho tri thức ChromaDB (tag knowledge) để sau này tự tra lại khi cần. Giúp AURA "biết nhiều" hơn mà không cần train lại model.
entrypoint: scripts/ingest.py
function: tool_knowledge_ingest
version: 1.0.0
tier: local
cost: free
permissions: [file_read, network]
---

# Knowledge Ingest — "Tự đọc sách rồi nhớ"

Đây là cách AURA **thông minh hơn mà KHÔNG đụng tới trọng số model**: đọc tài liệu →
cắt thành mảnh → nhúng & lưu vào kho tri thức (ChromaDB collection `knowledge`). Khi
Sếp hỏi hoặc trước khi làm việc, Orchestrator **tự tra** kho này (RAG) để trả lời/hành
động sát hơn.

Tuân thủ `CONTEXT.md`: bọc try/except (§2), trả `ToolResult`, validate nguồn (§7),
read-only với web (§6), không secret (§1). Nặng (chromadb/pdf) nạp TRỄ.

## Khi nào DÙNG
- "Học tài liệu này", "đọc file X và ghi nhớ", "nạp kiến thức về Y vào đầu".
- Bồi đắp hiểu biết nền cho AURA theo lĩnh vực của Sếp (giáo dục, Python/AI, dựng video...).

## Nguồn nạp được
| `source` | Xử lý |
|---|---|
| URL `http(s)://...` | Cào nội dung qua `web.scrape` (lazy cross-skill); JS-heavy thì có thể chỉ định web.agent sau |
| Đường dẫn file `.txt` / `.md` | Đọc trực tiếp |
| Đường dẫn file `.pdf` | Bóc text qua `pypdf` (nếu cài) |
| Văn bản thường | Coi `source`/`text` là nội dung thô để nhớ |

## Tham số
| Tên | Kiểu | Ý nghĩa |
|---|---|---|
| `source` | str | URL / đường dẫn file / hoặc văn bản thô. |
| `text` | str | Văn bản dán thẳng (ưu tiên nếu có). |
| `title` | str | Nhãn nguồn để truy vết (mặc định suy từ source). |
| `chunk_size` | int | Độ dài mỗi mảnh (mặc định 800 ký tự). |
| `max_chunks` | int | Trần số mảnh lưu mỗi lần (mặc định 60 — giữ nhẹ). |

## Hướng dẫn thực thi (Instructions)
- Đường chính: `registry.execute_tool("knowledge.ingest", {"source": "https://..."})`.
- CLI: `python skills/knowledge-base/scripts/ingest.py --source "D:/tai-lieu.pdf" --title "Giáo trình"`.

## Đầu ra
`ToolResult.output`: số mảnh đã lưu + nhãn nguồn. Tri thức nằm ở collection `knowledge`
(ChromaDB), tag `knowledge` + `source:<nhãn>`. Orchestrator sẽ recall tự động.
