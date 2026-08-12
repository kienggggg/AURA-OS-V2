"""Regression tests: news about recruitment must never be presented as a job."""

from __future__ import annotations

import json
from types import SimpleNamespace

from core import messenger
from skills.scouts import job_scout


GOOGLE_NEWS_ITEM = {
    "title": "Tỉnh X: Khẩn trương xây dựng kế hoạch tuyển dụng đặc cách nhân sự",
    "url": "https://news.google.com/rss/articles/ABC123?oc=5",
    "score": 1.0,
    "category": "career",
}

REAL_TEACHER_LISTING = {
    "title": "Trường THCS Ngọc Hòa tuyển dụng giáo viên hợp đồng năm học 2026-2027",
    "url": (
        "https://tuyencongchuc.vn/thong-bao/"
        "truong-thcs-ngoc-hoa-tuyen-dung-giao-vien-hop-dong/"
    ),
    "score": 0.7,
    "category": "career",
}

REAL_REMOTE_LISTING = {
    "title": "Arize AI: Open Source Design Engineer",
    "url": "https://weworkremotely.com/remote-jobs/arize-ai-open-source-design-engineer",
    "score": 0.69,
    "category": "money",
}


def test_google_news_and_recruitment_news_are_not_jobs():
    direct_news = {
        "title": "Bảo đảm kỳ tuyển dụng viên chức giáo viên diễn ra an toàn",
        "url": "https://baohungyen.vn/bao-dam-ky-tuyen-dung-giao-vien.html",
        "category": "career",
    }
    assert job_scout._is_real_listing(GOOGLE_NEWS_ITEM) is False
    assert job_scout._is_real_listing(direct_news) is False
    assert job_scout._is_real_listing(REAL_TEACHER_LISTING) is True
    assert job_scout._is_real_listing(REAL_REMOTE_LISTING) is True


def test_last_scan_persists_only_actionable_jobs(tmp_path, monkeypatch):
    last_scan = tmp_path / "job_scout_last.json"
    monkeypatch.setattr(job_scout, "_LAST_SCAN_PATH", last_scan)

    job_scout._save_last_scan(
        [GOOGLE_NEWS_ITEM, REAL_TEACHER_LISTING, REAL_REMOTE_LISTING]
    )
    payload = json.loads(last_scan.read_text(encoding="utf-8"))

    assert [row["title"] for row in payload["items"]] == [
        REAL_TEACHER_LISTING["title"],
        REAL_REMOTE_LISTING["title"],
    ]
    assert all(row["actionable"] is True for row in payload["items"])


def test_collect_filters_news_before_scoring(tmp_path, monkeypatch):
    settings = SimpleNamespace(
        scout_keywords="Python, nhân sự Tỉnh X",
        scout_threshold=0.6,
        freelance_urls="https://source.test/freelance",
        pedagogy_urls="https://source.test/teacher",
        scout_use_jina=False,
        scout_local_only=True,
        scout_priority_min_base=0.6,
    )
    monkeypatch.setattr(job_scout, "_settings", lambda: settings)

    def fake_collect_source(url, **_kwargs):
        if "teacher" in url:
            return [dict(GOOGLE_NEWS_ITEM), dict(REAL_TEACHER_LISTING)]
        return [dict(REAL_REMOTE_LISTING)]

    scored_batches: list[list[str]] = []

    def fake_score(items, _keywords, _engine):
        scored_batches.append([item["title"] for item in items])
        return [0.9] * len(items)

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(job_scout, "_collect_source", fake_collect_source)
    monkeypatch.setattr(job_scout, "score_items", fake_score)
    monkeypatch.setattr(job_scout, "_save_last_scan", lambda _results: None)
    monkeypatch.setattr(job_scout, "_auto_apply", lambda _results: 0)
    monkeypatch.setattr("requests.Session", FakeSession)
    monkeypatch.setattr("core.embedder.get_worker", lambda: SimpleNamespace(unload=lambda: None))

    results = job_scout.collect()

    assert GOOGLE_NEWS_ITEM["title"] not in {
        title for batch in scored_batches for title in batch
    }
    assert [row["title"] for row in results] == [
        REAL_REMOTE_LISTING["title"],
        REAL_TEACHER_LISTING["title"],
    ]


def test_telegram_formatter_defensively_drops_legacy_news(monkeypatch):
    monkeypatch.setattr(
        messenger,
        "_load",
        lambda _name: {
            "items": [GOOGLE_NEWS_ITEM, REAL_TEACHER_LISTING, REAL_REMOTE_LISTING]
        },
    )

    message = messenger._fmt_jobs()

    assert "TIN VIỆC CÓ THỂ ỨNG TUYỂN" in message
    assert "Khẩn trương xây dựng kế hoạch" not in message
    assert REAL_TEACHER_LISTING["title"] in message
    assert REAL_REMOTE_LISTING["title"] in message
