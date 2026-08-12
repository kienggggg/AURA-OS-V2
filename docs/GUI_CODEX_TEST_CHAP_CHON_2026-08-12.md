# Gửi người viết `tests/test_tech_evidence.py` — một test chập chờn theo đồng hồ

Tệp `tests/test_tech_evidence.py` **chưa được git theo dõi**, nên tôi không sửa
(CLAUDE.md §7: đọc trước khi viết đè, tệp chưa theo dõi của người khác thì đừng
ghi đè). Viết ra đây để Sếp chuyển.

## Hiện tượng

`test_reports_are_json_and_markdown_and_do_not_inflate_discovery` hỏng **1 lần
trong 5 lần chạy** ngày 12/08/2026. Chạy riêng thì luôn xanh; chạy cả bộ thì
thỉnh thoảng đỏ. Bốn lần chạy lại sau đó đều xanh.

Đây **không phải** do đợt thêm 19 công nghệ vào `registry.json` cùng ngày — test
này dùng `tmp_path` và sổ riêng, không chạm sổ thật.

## Nguyên nhân

```
core/tech_evidence.py:630   "generated_at": utc_now(),
core/tech_evidence.py:642   f"Generated: `{report['generated_at']}`  ",
core/tech_evidence.py:82    datetime.now(timezone.utc).isoformat(timespec="seconds")
```

Dòng cuối của test:

```python
assert report_markdown(build_report(registry, tmp_path)) == markdown
```

`markdown` sinh ra từ `write_reports(...)` ở trên, còn vế trái dựng **báo cáo mới**.
Mỗi lần dựng lại đóng một dấu thời gian mới, **chính xác tới giây**. Hai lần gọi
nằm hai bên một tích tắc giây là hai chuỗi khác nhau — và test đỏ.

Tức là test đang so **một hiện vật có đóng dấu thời gian** bằng dấu bằng. Nó xanh
nhờ chạy đủ nhanh, không nhờ đúng.

## Ba cách sửa, chọn cách nào cũng được

1. **So phần không đổi**: bỏ dòng `Generated:` ra khỏi cả hai vế trước khi so.
2. **Đóng băng đồng hồ**: `monkeypatch` `utc_now` trả một hằng số trong test.
3. **Nhận một báo cáo, dựng hai bản**: `report = build_report(...)` một lần, rồi
   so `report_markdown(report)` với tệp đã ghi từ **chính** `report` đó.

Cách 3 gần với ý định của test nhất — kiểm "markdown dựng lại được từ JSON",
không kiểm "hai lần dựng cách nhau cho ra chuỗi giống nhau".

## Vì sao đáng sửa chứ không đáng bỏ qua

Một test đỏ ngẫu nhiên rồi tự xanh lại là thứ dạy người ta chạy lại cho đến khi
xanh. Lần sau nó đỏ vì lý do thật thì phản xạ vẫn là chạy lại.
