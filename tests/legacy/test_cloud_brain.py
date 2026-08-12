"""Test cắm não cloud free (OpenAI-compatible) — offline, mock requests.post."""
import os, sys, json
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
# Bật provider openai TRƯỚC khi import settings (pydantic đọc env lúc khởi tạo).
os.environ["CLOUD_PROVIDER"] = "openai"
os.environ["OPENAI_API_KEY"] = "gsk_test_KEY"
os.environ["OPENAI_BASE_URL"] = "https://api.groq.com/openai/v1"
os.environ["OPENAI_MODEL"] = "llama-3.3-70b-versatile"
os.environ["COUNCIL_GENERATOR_TIER"] = "cloud"
sys.path.insert(0, r"D:\AURA_OS_v2")

ok = 0
def check(name, cond):
    global ok
    print(("[PASS] " if cond else "[FAIL] ") + name)
    ok += 0 if cond else 1

from core.config import settings
check("provider=openai", settings.cloud_provider == "openai")
check("council tier=cloud", settings.council_generator_tier == "cloud")

# CloudEngine phải chọn OpenAICompatBackend
from core.llm import CloudEngine
import brains.cloud_openai_compat as oc
eng = CloudEngine()
check("CloudEngine.name dùng openai_model", "llama-3.3-70b-versatile" in eng.name)
check("is_online True khi có OPENAI_API_KEY", eng.is_online() is True)
backend = eng._ensure()
check("_ensure -> OpenAICompatBackend", backend.__class__.__name__ == "OpenAICompatBackend")

# Mock requests.post để soi body/headers, trả JSON kiểu OpenAI
captured = {}
class FakeResp:
    status_code = 200
    text = "ok"
    def json(self):
        return {"choices": [{"message": {"content": '{"task_id": 7, "code_payload": "ok"}'}}]}

def fake_post(url, json=None, headers=None, timeout=None):
    captured["url"] = url; captured["body"] = json; captured["headers"] = headers
    return FakeResp()

oc.requests.post = fake_post

# Gọi qua complete() như Council: có system_prompt + response_format JSON mode
res = eng.complete(
    [{"role": "user", "content": "viết tool"}],
    system_prompt="HIẾN PHÁP",
    temperature=0.0, max_tokens=1500,
    response_format={"type": "json_object"},
)
check("complete ok=True", res.get("ok") is True)
text = res.get("text", "")
check("trả đúng nội dung model", json.loads(text).get("task_id") == 7)

# Soi request đã dựng
check("URL = base_url + /chat/completions",
      captured["url"] == "https://api.groq.com/openai/v1/chat/completions")
check("Authorization Bearer key", captured["headers"]["Authorization"] == "Bearer gsk_test_KEY")
msgs = captured["body"]["messages"]
check("system thành message role=system ở đầu",
      msgs[0]["role"] == "system" and msgs[0]["content"] == "HIẾN PHÁP")
check("user message theo sau", msgs[1]["role"] == "user")
check("response_format JSON mode chuyển tiếp",
      captured["body"].get("response_format") == {"type": "json_object"})
check("model đúng", captured["body"]["model"] == "llama-3.3-70b-versatile")

# Thiếu key -> BrainOfflineError (qua complete -> ok=False)
settings.openai_api_key = None
res2 = eng2 = CloudEngine().complete([{"role": "user", "content": "x"}])
check("thiếu key -> ok=False, báo rõ", res2.get("ok") is False and "OPENAI_API_KEY" in res2.get("error", ""))

print()
print("KẾT QUẢ:", "TẤT CẢ PASS" if ok == 0 else f"{ok} FAIL")
sys.exit(ok)
