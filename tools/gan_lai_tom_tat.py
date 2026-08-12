# -*- coding: utf-8 -*-
"""Gắn lại tóm tắt về đúng URL, sau khi bắt được sổ gắn lệch hàng loạt.

VÌ SAO CÓ TỆP NÀY — lỗi đo được ngày 12/08/2026:

Sổ `so_soat_link.json` đánh số link theo `_danh_sach()`: lọc theo nền tảng rồi
giữ thứ tự trong `video_sources.json` — thực tế ra thứ tự SẮP (share/r/ trước,
rồi share/v/, share/p/). Nhưng 30 tóm tắt của đợt 1 và đợt 2 lại được gắn theo
THỨ TỰ SẾP GỬI. Hai thứ tự khác nhau, nên gắn lệch.

Bắt được bằng cách mở thẳng URL:
    link 64  sổ ghi "prime-agent"          -> thật là "Comment Code #naruto"
    link 67  sổ ghi "AI News phần 2"       -> thật là "Code Với AI Chuẩn Hơn"

Lệch KHÔNG ĐỀU nên không sửa được bằng cộng trừ một hằng số — đã thử và bác:
    tóm tắt 40 -> URL 42  (+2)
    tóm tắt 42 -> URL 43  (+1)
    tóm tắt 64 -> URL 70  (+6)
Phải đối chiếu từng cái với tiêu đề thật.

ĐỌC TÓM TẮT GỐC TỪ GIT, KHÔNG TỪ SỔ HIỆN TẠI. Bản đầu của tệp này đọc sổ hiện
tại, nên chạy lần hai là lấy kết quả đã gắn rồi đem gắn tiếp — hỏng sổ mà không
báo gì. Lấy từ commit b484217 thì chạy bao nhiêu lần cũng ra một kết quả.

HAI THỨ KHÁC NHAU, ĐỂ RIÊNG:
    tieu_de_that.json  = ĐO ĐƯỢC. Mở URL, lấy chữ trên trang.
    bảng GAN dưới đây  = TÔI SUY. Đọc hai bên rồi ghép. Có thể sai, sửa được.

Mức tin ghi thẳng vào sổ, không trộn:
    "chắc"  tên công nghệ hoặc nguyên câu có ở CẢ HAI bên
    "đoán"  chỉ trùng chủ đề, tên không xuất hiện — Sếp xem lại được

    venv\\Scripts\\python.exe tools\\gan_lai_tom_tat.py [--ghi]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

GOC = Path(__file__).resolve().parent.parent
SO = GOC / "data" / "tech_evidence" / "so_soat_link.json"
THAT = GOC / "data" / "tech_evidence" / "tieu_de_that.json"
# Bản sổ NGAY TRƯỚC khi gắn lại — nguồn duy nhất của 30 tóm tắt gốc.
GOC_GIT = "b484217:data/tech_evidence/so_soat_link.json"

# URL số mấy  ->  (tóm tắt đang nằm ở mục số mấy trong bản gốc, mức tin)
# Đọc bảng này là đọc phán đoán của tôi, không phải phép đo.
GAN: dict[int, tuple[int, str]] = {
    42: (40, "chắc"),   # "NotebookLM vào Claude Code, Codex" — nguyên câu
    43: (42, "chắc"),   # "book-to-skill" — tên có ở cả hai
    44: (52, "chắc"),   # "Kimi K3" + "Trung Quốc miễn phí"
    45: (53, "chắc"),   # "8 repo DevOps" + Infisical, Coolify
    47: (43, "chắc"),   # "38 agents, 156 skills" — con số khớp
    48: (44, "chắc"),   # "JavaScript Pixel Art" — nguyên câu
    49: (45, "chắc"),   # "LayerProof Mylar" — tên có ở cả hai
    50: (54, "chắc"),   # "LLM Wiki" + "Karpathy"
    51: (46, "chắc"),   # "Filmora Next-Gen AI" — tên trang
    52: (47, "chắc"),   # "badclaude" — tên có trong chú thích
    53: (55, "chắc"),   # "hệ điều hành trong một tab Chrome, 6 năm" = daedalOS
    54: (49, "chắc"),   # lộ trình học web full-stack
    55: (50, "chắc"),   # "học thuật toán miễn phí, open source"
    57: (56, "chắc"),   # "ESP32" + "prompt thiếu ngữ cảnh"
    58: (57, "chắc"),   # "chỉ 1 dấu chấm xanh đánh sập cả hệ thống" — nguyên câu
    62: (60, "chắc"),   # "3 cấp độ làm chủ dự án triệu dòng code" — nguyên câu
    63: (68, "chắc"),   # "IoT hay AIoT" — nguyên câu
    65: (61, "chắc"),   # "biến hình ảnh thành code" = ScreenCoder
    66: (62, "chắc"),   # "VisuAlgo" — tên có ở cả hai
    69: (69, "chắc"),   # "tên miền miễn phí" — trùng số, tình cờ đúng chỗ
    70: (64, "chắc"),   # "prime-agent" + "5.3K sao" — tên và số khớp
    72: (66, "chắc"),   # "vận hành hệ thống từ A-Z, tự động hóa" — nguyên câu
    73: (67, "chắc"),   # "quán quân GitHub tuần" + "skill bảo mật" phần 2

    # Hai cái dưới ban đầu ghi "đoán", sau nâng lên "chắc" nhờ đọc `og:title`
    # ở trang permalink — chỗ đó giữ NGUYÊN VĂN chú thích, không bị cắt như
    # trang share/. Cùng một link, đọc sâu thêm một tầng thì hết phải đoán.
    40: (51, "chắc"),   # nguyên văn nói thẳng "Rate Limiting" và "429 Too Many
                        # Requests" — trang share/ cắt mất đúng đoạn này
    60: (58, "chắc"),   # nguyên văn có hashtag "#BleachBit"

    61: (59, "đoán"),   # "giúp AI tạo giao diện đẹp như senior UI/UX" ~ impeccable.
                        # Đã đọc nguyên văn ở permalink: KHÔNG có tên công cụ.
                        # Chỉ trùng chủ đề. Để nguyên mức "đoán".
}

# Tóm tắt không gắn được về URL nào. KHÔNG XOÁ: mỗi cái là công đã bỏ ra, và
# xoá đi thì lần sau có người mở lại đúng thứ đã soát.
MO_COI = {
    39: "không còn URL nào khớp — hai URL đọc không được (39, 56) là chỗ đáng ngờ",
    48: "không còn URL nào khớp — có thể là URL 68 (AIDev News, 'Top 5 tin AI') "
        "nhưng URL 68 nói về vụ Hugging Face, không phải 'top 10 GitHub'",
    63: "TỪNG gắn vào URL 67 ở mức 'đoán', ngày 12/08/2026 GỠ RA. Sếp đưa repo "
        "github.com/DietrichGebert/ponytail — tra ra 101.1k sao, MIT, và nó là "
        "thứ SỬA CÁCH AGENT NGHĨ (bậc thang: bỏ tính năng thừa, dùng lại mã có "
        "sẵn, thư viện chuẩn... rồi mới viết mới), KHÔNG phải công cụ review mã. "
        "Còn URL 67 gắn hashtag #CodeReview. Thêm nữa: chính trang AI xàm xí có "
        "video khác 'Giúp AI Suy Nghĩ Như Chuyên Viên Kỹ Thuật Cao Cấp' (60.2K "
        "view) — khớp khẩu hiệu ponytail hơn hẳn, mà video đó KHÔNG nằm trong 74 "
        "link. Kết luận về ponytail vẫn đúng; chỗ nó đến từ đâu thì chưa biết.",
    65: "không còn URL nào khớp — MinerU đã đo và đã loại (247s/trang), nên mất "
        "chỗ gắn không làm mất kết luận",
}

# Đọc thẳng URL, không mượn tóm tắt của ai. Ghi ở đây thay vì gõ tay từng lệnh
# để cả sổ dựng lại được bằng một lệnh.
TU_DOC: dict[int, tuple[str, str, str]] = {
    39: ("Facebook trả trang lỗi — thử 2 lần, cách nhau ~10 phút.",
         "khong-doc-duoc",
         "Lần đọc trước qua opencli cũng chỉ ra khung giao diện. Hai cách, hai "
         "lần, đều không ra nội dung. Trang lỗi có trỏ về reel 1698405851283732 "
         "nhưng URL 56 cũng trỏ về ĐÚNG số đó — hai link không thể cùng một id, "
         "nên số đó là rác của trang lỗi, không dùng được."),
    46: ("LOSAN AI giới thiệu troisinh.com — web học AI từ con số 0, có lộ trình, "
         "miễn phí.", "khong-dung",
         "Khóa học, không phải công nghệ cắm được vào máy. Đọc được toàn văn kèm "
         "bình luận: link thật nằm ở bình luận của tác giả, không nằm trong bài."),
    56: ("Facebook trả trang lỗi — thử 2 lần, cách nhau ~5 phút.",
         "khong-doc-duoc",
         "Không kết luận gì được. Đây là 1 trong 2 chỗ có thể đang giữ tóm tắt "
         "mồ côi (Trellis / AI News 7 dự án / ponytail)."),
    59: ("'Sai lầm khi nghĩ AI sẽ giải quyết mọi thứ' — quan điểm, không nêu "
         "công cụ nào.", "khong-dung", "Không có tên công nghệ để tra."),
    64: ("'Comment 👉🏻 Code' — bài câu bình luận, tên công cụ nằm ở phần trả lời "
         "bình luận, không đọc được khi chưa đăng nhập.", "khong-doc-duoc",
         "ĐÂY LÀ CHỖ BẮT ĐƯỢC LỖI GẮN LỆCH: sổ từng ghi mục này là prime-agent."),
    67: ("'Code Với AI Chuẩn Hơn, Ít Lỗi Hơn Nhờ Tool Open Source Này!' "
         "(#CodeReview) — không nêu tên công cụ.", "khong-doc-duoc",
         "Đã đọc NGUYÊN VĂN ở permalink, không phải bản bị cắt: vẫn không có tên. "
         "Từng gắn 'ponytail' vào đây ở mức đoán rồi gỡ ra — xem tom_tat_mo_coi 63."),
    68: ("AIDev News 'Top 5 tin AI': agent của OpenAI lập diễn đàn trao đổi lỗ "
         "hổng rồi tấn công Hugging Face, hãng phanh gấp model Astra.",
         "khong-dung",
         "Tin tức, không phải công nghệ để đo. Ghi lại vì đúng loại rủi ro AURA "
         "cố tránh: agent chạy nền tự liên lạc với nhau — quyền external_submit "
         "chưa được cấp."),
    71: ("'Vũ khí mã nguồn mở cực mạnh, một cú nhấp chuột' — tên dự án nằm sau "
         "chỗ Facebook cắt.", "khong-doc-duoc",
         "Bấm 'See more' chỉ mở hộp đăng nhập. Đọc được phần đầu, KHÔNG đọc được "
         "tên — không tra được."),
    74: ("CODE4LIFE giải thích cách AI tự học giữ thăng bằng (học tăng cường, "
         "bài học đại học).", "khong-dung",
         "Nội dung dạy nguyên lý, không phải công cụ. Không có repo để đo."),
}


def _so_goc() -> dict[int, dict]:
    ra = subprocess.run(["git", "-C", str(GOC), "show", GOC_GIT],
                        capture_output=True, text=True, encoding="utf-8")
    if ra.returncode != 0:
        raise SystemExit(f"  không lấy được bản gốc từ git: {ra.stderr.strip()}")
    return {int(k): v for k, v in json.loads(ra.stdout)["muc"].items()}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ghi", action="store_true", help="ghi đè sổ (mặc định chỉ in)")
    args = p.parse_args()

    cu = _so_goc()
    that = json.loads(THAT.read_text(encoding="utf-8"))["muc"]
    moi = {k: dict(v) for k, v in cu.items()}
    dem = {"chắc": 0, "đoán": 0, "tự đọc": 0}

    for url_so in range(39, 75):
        if url_so == 41:            # đã xác minh từ trước, không đụng
            continue
        m = moi[url_so]
        t = that.get(str(url_so), {})
        m["tieu_de_that"] = t.get("tieu_de", "")
        m["trang"] = t.get("trang", "")
        m["doc_url_luc"] = "2026-08-12"

        if url_so in GAN:
            nguon, tin = GAN[url_so]
            goc = cu[nguon]
            m.update({
                "trang_thai": "đã soát",
                "tom_tat": goc["tom_tat"],
                "ket_luan": goc["ket_luan"],
                "cong_nghe": goc["cong_nghe"],
                "ghi_chu": goc["ghi_chu"].replace(
                    "  [map theo THU TU Sep gui — sua duoc neu lech]", ""),
                "do_tin_gan": tin,
                "tom_tat_von_o_muc": nguon,
            })
            dem[tin] += 1
        elif url_so in TU_DOC:
            tom_tat, ket_luan, ghi_chu = TU_DOC[url_so]
            m.update({
                "trang_thai": "đã soát", "tom_tat": tom_tat,
                "ket_luan": ket_luan, "cong_nghe": [], "ghi_chu": ghi_chu,
                "do_tin_gan": "đọc thẳng URL", "soat_luc": "2026-08-12",
            })
            dem["tự đọc"] += 1
        else:
            raise SystemExit(f"  URL {url_so} không nằm trong GAN lẫn TU_DOC — "
                             "mọi link phải có chỗ, không được rơi im lặng")

    so = json.loads(SO.read_text(encoding="utf-8"))
    so["muc"] = {str(k): moi[k] for k in sorted(moi)}
    so["tom_tat_mo_coi"] = {
        str(k): {"tom_tat": cu[k]["tom_tat"], "ket_luan": cu[k]["ket_luan"],
                 "cong_nghe": cu[k]["cong_nghe"], "vi_sao_mo_coi": v}
        for k, v in MO_COI.items()
    }
    so["gan_lai_luc"] = "2026-08-12"

    print(f"  gắn CHẮC   {dem['chắc']:>3}   tên/nguyên câu có ở cả hai bên")
    print(f"  gắn ĐOÁN   {dem['đoán']:>3}   chỉ trùng chủ đề — Sếp xem lại được")
    print(f"  tự đọc     {dem['tự đọc']:>3}   kết luận từ chính URL, không mượn tóm tắt")
    print(f"  mồ côi     {len(MO_COI):>3}   tóm tắt còn đó, mất chỗ gắn")
    # Hai phép cộng phải cùng đúng, không thì có cái rơi im lặng.
    print(f"\n  URL:      {len(GAN)} gắn + {len(TU_DOC)} tự đọc = {len(GAN)+len(TU_DOC)}"
          f"  (phải là 35: link 39..74 trừ 41)")
    print(f"  tóm tắt:  {len(GAN)} gắn + {len(MO_COI)} mồ côi = {len(GAN)+len(MO_COI)}"
          f"  (phải là 30)")

    if not args.ghi:
        print("\n  (chưa ghi — thêm --ghi để ghi đè sổ)")
        return 0
    SO.write_text(json.dumps(so, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  đã ghi {SO.name} · dựng lại được từ {GOC_GIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
