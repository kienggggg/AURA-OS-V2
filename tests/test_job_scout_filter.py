"""Job Scout không được báo trang search RỖNG ('0 việc làm') là tin việc thật."""

from __future__ import annotations

import pytest

from skills.scouts.job_scout import _is_real_listing

URL = "https://www.topcv.vn/tim-viec-lam-giao-vien-tai-thai-binh"


@pytest.mark.parametrize("title,expected", [
    ("Tuyển dụng 0 việc làm Lap Trinh Vien Tai Tinh X [Update 01/08/2026]", False),
    ("Không tìm thấy việc làm phù hợp", False),
    ("0 kết quả cho từ khoá Python", False),
    # KHÔNG được chặn nhầm khi có SỐ KHÁC đứng trước 0:
    ("10 việc làm Python tại Hà Nội", True),
    ("100 việc làm Lập trình viên tại Tỉnh X", True),
    ("Giáo viên Python - TEKY tuyển dụng", True),
    ("Python Developer (0 kinh nghiệm cũng ok)", True),  # '0 kinh nghiệm' != '0 việc'
])
def test_empty_search_page_filtered(title, expected):
    assert _is_real_listing({"title": title, "url": URL}) is expected


def test_no_url_is_not_real():
    assert _is_real_listing({"title": "10 việc làm Python", "url": ""}) is False
