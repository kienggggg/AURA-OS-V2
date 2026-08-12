"""
core/lead_collector.py
======================
BỘ THU THẬP & THẨM ĐỊNH LEAD LIVE (§10 - CODEX REVIEW VÒNG 3)
============================================================
- KHÓA NGÁCH DUY NHẤT: ACTIVE_NICHE = "python_automation".
- Thẩm định 100% bản ghi batch live. Trả STALE nếu thiếu batch_id, quá 24h, chứa 'xxx' hoặc không qua validator.
- Yêu cầu bắt buộc: url, source, niche, title, requirement, contact_channel, budget_signal, source_posted_at.
- Nếu nguồn thiếu ngày đăng, gán source_posted_at = None (CẤM tự giả mạo timestamp hiện tại).
"""

from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
from core.config import settings, PROJECT_ROOT

logger = logging.getLogger("aura.lead_collector")
_LEADS_FILE = PROJECT_ROOT / "data" / "leads" / "verified_leads.json"

ACTIVE_NICHE = "python_automation"
_PYTHON_AUTOMATION_KEYWORDS = (
    "python",
    "automation",
    "automate",
    "scripting",
    "script",
    "web scraping",
    "scraper",
    "crawl data",
    "data pipeline",
    "api integration",
)

LIVE_FEED_SOURCES = [
    {
        "name": "Remotive Remote Jobs",
        "url": "https://remotive.com/api/remote-jobs?category=software-dev",
        "type": "json_api",
        "niche": "python_automation",
    },
    {
        "name": "We Work Remotely Backend",
        "url": "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
        "type": "rss",
        "niche": "python_automation",
    },
    {
        "name": "Upwork Python RSS",
        "url": "https://www.upwork.com/ab/feed/jobs/rss?q=python+automation",
        "type": "rss",
        "niche": "python_automation",
    },
]


def normalize_url(url: str) -> str:
    """Chuẩn hóa URL: Bỏ tracking query parameters & fragment, lowercase scheme/netloc."""
    url = url.strip()
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip('/')

    query_params = parse_qs(parsed.query)
    clean_params = {
        k: v for k, v in query_params.items()
        if not k.lower().startswith(("utm_", "fbclid", "gclid", "ref", "source"))
    }
    clean_query = urlencode(clean_params, doseq=True)

    return urlunparse((scheme, netloc, path, parsed.params, clean_query, ""))


def stable_lead_id(url: str) -> str:
    """ID bền theo URL chuẩn để cùng một cơ hội không bị nhân đôi qua các batch."""
    normalized = normalize_url(url)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
    return f"LEAD-{digest}"


def validate_lead(lead: dict[str, Any], required_niche: str = ACTIVE_NICHE) -> tuple[bool, str]:
    """Kiểm tra tính hợp lệ của 1 lead theo quy chuẩn Codex Review §10."""
    # 1. Kiểm tra Niche nghiêm ngặt
    lead_niche = str(lead.get("niche") or "").strip()
    if lead_niche != required_niche:
        return False, f"Sai ngách thử nghiệm ({lead_niche} != {required_niche})"

    # 2. Kiểm tra Nguồn
    source = str(lead.get("source") or "").strip()
    if not source:
        return False, "Thiếu nguồn (source)"

    # 3. Kiểm tra URL
    url = str(lead.get("url") or "").strip()
    if not url or not url.lower().startswith(("http://", "https://")):
        return False, "Thiếu URL hoặc URL không hợp lệ"

    url_lower = url.lower()
    if any(p in url_lower for p in ["xxx", "example.com", "domain.com", "fake", "placeholder", "localhost"]):
        return False, "URL chứa placeholder / dữ liệu giả"

    # 4. Kiểm tra Kênh liên hệ
    contact = str(lead.get("contact_channel") or "").strip().lower()
    if not contact or "xxx" in contact or "example" in contact:
        return False, "Kênh liên hệ thiếu hoặc chứa placeholder 'xxx'"

    # 5. Kiểm tra Dấu hiệu Ngân sách
    budget = str(lead.get("budget_signal") or "").strip()
    if not budget:
        return False, "Thiếu dấu hiệu ngân sách (budget_signal)"

    # 6. Kiểm tra Tiêu đề & Mô tả
    title = str(lead.get("title") or "").strip()
    if not title or len(title) < 5 or "xxx" in title.lower():
        return False, "Tiêu đề rỗng hoặc chứa placeholder 'xxx'"

    req = str(lead.get("requirement") or "").strip()
    if not req or len(req) < 10 or "xxx" in req.lower():
        return False, "Mô tả rỗng hoặc chứa placeholder 'xxx'"

    if required_niche == ACTIVE_NICHE:
        searchable = f"{title} {req}".casefold()
        if not any(keyword in searchable for keyword in _PYTHON_AUTOMATION_KEYWORDS):
            return False, "Nội dung không chứng minh thuộc ngách Python automation"

    # 7. Kiểm tra sự tồn tại của khóa source_posted_at
    if "source_posted_at" not in lead:
        return False, "Thiếu khóa source_posted_at"

    # 8. Kiểm tra verified_at không ở tương lai
    verified_at = int(lead.get("verified_at") or 0)
    if verified_at > 0 and verified_at > (int(time.time()) + 300):
        return False, "Thời gian verified_at ở tương lai"

    return True, "Hợp lệ"


def check_url_live(url: str, timeout: float = 5.0) -> bool:
    """Kiểm tra HTTP GET status 200 OK & không phải trang 404 mềm / login."""
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (AURA Scout)"}, timeout=timeout, stream=True)
        if resp.status_code != 200:
            return False

        header_text = resp.text[:2000].lower() if hasattr(resp, 'text') else ""
        if any(keyword in header_text for keyword in ["job closed", "job expired", "404 not found", "page not found", "login required"]):
            return False

        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Kiểm tra HTTP live URL %s thất bại: %s", url, exc)
        return False


def fetch_live_leads_from_rss(feed_info: dict[str, Any], timeout: float = 8.0) -> list[dict[str, Any]]:
    """Cào lead live từ RSS/API công khai (sửa lỗi parse ElementTree XML leaf nodes)."""
    leads: list[dict[str, Any]] = []
    feed_url = feed_info["url"]
    feed_type = feed_info["type"]
    feed_niche = feed_info.get("niche", ACTIVE_NICHE)

    try:
        resp = requests.get(feed_url, headers={"User-Agent": "Mozilla/5.0 (AURA Lead Scout)"}, timeout=timeout)
        if resp.status_code != 200:
            return []

        if feed_type == "json_api":
            data = resp.json()
            jobs = data.get("jobs", [])
            for job in jobs[:15]:
                link = str(job.get("url") or "").strip()
                title = str(job.get("title") or "").strip()
                desc = str(job.get("description") or "").strip()
                desc_clean = re.sub(r"<[^>]+>", " ", desc).strip()
                posted_at = str(job.get("publication_date") or "") or None

                if link and title:
                    leads.append({
                        "title": title,
                        "url": link,
                        "source": feed_info["name"],
                        "niche": feed_niche,
                        "requirement": desc_clean[:400] or title,
                        "contact_channel": f"Ứng tuyển trực tiếp tại: {link}",
                        "budget_signal": str(job.get("salary") or "unknown"),
                        "source_posted_at": posted_at,
                        "deadline": None,
                    })

        elif feed_type == "rss":
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.content)
            items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")

            for item in items[:15]:
                title_el = item.find("title")
                if title_el is None:
                    title_el = item.find("{http://www.w3.org/2005/Atom}title")
                title = title_el.text.strip() if title_el is not None and title_el.text else ""

                link_el = item.find("link")
                if link_el is None:
                    link_el = item.find("{http://www.w3.org/2005/Atom}link")
                link = ""
                if link_el is not None:
                    link = link_el.text.strip() if link_el.text else link_el.attrib.get("href", "")

                desc_el = item.find("description")
                if desc_el is None:
                    desc_el = item.find("{http://www.w3.org/2005/Atom}summary")
                desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
                desc_clean = re.sub(r"<[^>]+>", " ", desc).strip()

                pub_el = item.find("pubDate")
                if pub_el is None:
                    pub_el = item.find("{http://www.w3.org/2005/Atom}published")
                posted_at = pub_el.text.strip() if pub_el is not None and pub_el.text else None

                if title and link.startswith(("http://", "https://")):
                    leads.append({
                        "title": title,
                        "url": link,
                        "source": feed_info["name"],
                        "niche": feed_niche,
                        "requirement": desc_clean[:400] or title,
                        "contact_channel": f"Ứng tuyển qua link gốc: {link}",
                        "budget_signal": "unknown",
                        "source_posted_at": posted_at,
                        "deadline": None,
                    })

    except Exception as exc:  # noqa: BLE001
        logger.warning("Cào feed %s thất bại: %s", feed_url, exc)

    return leads


def _atomic_write_json(file_path: Path, data: Any) -> None:
    """Ghi file theo kiểu thay thế nguyên tử (atomic write)."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = file_path.parent
    with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tf:
        tf.write(json.dumps(data, ensure_ascii=False, indent=2))
        temp_name = tf.name
    os.replace(temp_name, file_path)


def collect_verified_leads(
    niche: str = ACTIVE_NICHE,
    target_count: int = 20,
    verify_http: bool = True,
    experiment_id: str = "",
    file_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Thu thập live lead theo batch ID duy nhất, ghi file an toàn nguyên tử."""
    experiment_id = str(experiment_id or "").strip()
    if not experiment_id:
        raise ValueError("Thu thập lead bắt buộc có experiment_id hiện hành.")
    batch_id = f"BATCH-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    logger.info("Bắt đầu thu thập live lead [Batch: %s] cho ngách: %s", batch_id, niche)

    seen_urls: set[str] = set()
    verified_leads: list[dict[str, Any]] = []

    for feed_info in LIVE_FEED_SOURCES:
        if len(verified_leads) >= target_count:
            break

        if feed_info.get("niche") != niche:
            continue

        raw_items = fetch_live_leads_from_rss(feed_info)
        for item in raw_items:
            if len(verified_leads) >= target_count:
                break

            item["verified_at"] = int(time.time())
            item["collected_at"] = int(time.time())

            valid, msg = validate_lead(item, required_niche=niche)
            if not valid:
                logger.debug("Lead bị từ chối [%s]: %s", item.get("url"), msg)
                continue

            norm_url = normalize_url(item["url"])
            if norm_url in seen_urls:
                continue
            seen_urls.add(norm_url)

            if verify_http:
                if not check_url_live(item["url"]):
                    logger.debug("Lead HTTP check 200 thất bại: %s", item["url"])
                    continue

            item["id"] = stable_lead_id(item["url"])
            item["collection_batch_id"] = batch_id
            item["experiment_id"] = experiment_id
            verified_leads.append(item)

    output_path = file_path or _LEADS_FILE
    _atomic_write_json(output_path, verified_leads)
    logger.info("LeadCollector: Batch %s hoàn tất với %d lead verified", batch_id, len(verified_leads))

    return verified_leads


def get_current_verified_leads(
    max_age_seconds: float = 86400.0,
    expected_experiment_id: str | None = None,
    file_path: Path | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Thẩm định 100% bản ghi trong file verified_leads.json (§10).
    Trả về (leads, batch_id). Nếu rỗng/stale/quá hạn/chứa dữ liệu không qua validator -> ([], "STALE").
    """
    input_path = file_path or _LEADS_FILE
    if not input_path.is_file():
        return [], "STALE"

    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(data, list) or not data:
            return [], "STALE"

        batch_id = str(data[0].get("collection_batch_id") or "")
        if not batch_id or batch_id == "UNKNOWN":
            return [], "STALE"
        batch_experiment_id = str(data[0].get("experiment_id") or "").strip()
        if not batch_experiment_id:
            return [], "STALE"
        if expected_experiment_id and batch_experiment_id != str(expected_experiment_id):
            return [], "STALE"

        now = int(time.time())
        valid_items: list[dict[str, Any]] = []

        for item in data:
            if not isinstance(item, dict):
                return [], "STALE"

            # Kiểm tra batch_id đồng nhất
            if str(item.get("collection_batch_id") or "") != batch_id:
                return [], "STALE"
            if str(item.get("experiment_id") or "").strip() != batch_experiment_id:
                return [], "STALE"

            # Kiểm tra verified_at quá hạn
            verified_at = int(item.get("verified_at") or 0)
            if verified_at == 0 or (now - verified_at) > max_age_seconds:
                return [], "STALE"

            # Thẩm định validator
            ok, _ = validate_lead(item, required_niche=ACTIVE_NICHE)
            if not ok:
                return [], "STALE"

            valid_items.append(item)

        if not valid_items:
            return [], "STALE"

        return valid_items, batch_id
    except Exception as exc:  # noqa: BLE001
        logger.warning("Đọc verified leads audit thất bại: %s", exc)
        return [], "STALE"
