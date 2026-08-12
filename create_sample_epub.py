import zipfile
import os

def create_epub(filename, title, content_paragraphs):
    os.makedirs(r"d:\AURA_OS_v2\data\reference_epubs", exist_ok=True)
    filepath = os.path.join(r"d:\AURA_OS_v2\data\reference_epubs", filename)
    
    html_content = f"<html><head><title>{title}</title></head><body>\n"
    for p in content_paragraphs:
        html_content += f"<p>{p}</p>\n"
    html_content += "</body></html>"
    
    with zipfile.ZipFile(filepath, 'w') as archive:
        archive.writestr('chapter1.html', html_content.encode('utf-8'))
        
    print(f"Created {filepath}")

# Sample 1: Quỷ Bí Chi Chủ (Atmosphere, Show-don't-tell)
quibi = [
    "Cơn đau xé rách màng nhĩ, mang theo tiếng nỉ non thì thầm không rõ âm tiết vọng lại từ khoảng không vô định.",
    "Klein tỉnh dậy, cảm giác dính nhớp ở trán khiến hắn nhíu mày. Đưa tay lên sờ, một mảnh dính ngáp, đỏ sậm. Máu.",
    "Căn phòng nồng nặc mùi thuốc súng và rỉ sét. Trên bàn gỗ mục nát, một cuốn sổ đen ngòm đang mở dở, những dòng chữ xiêu vẹo như được viết bằng máu vẫn còn chưa khô: 'Chúng ta sẽ chết, tất cả đều phải chết...'",
    "Hắn loạng choạng đứng dậy, cơn đau buốt từ thái dương nhắc nhở hắn một sự thật tàn khốc: Cỗ thân thể này vừa tự sát, và hắn, Chu Minh Thụy, vừa xuyên không nhập vào nó.",
    "Bên ngoài cửa sổ, ánh trăng đỏ như máu lơ lửng giữa bầu trời sương mù dày đặc của vương quốc Ruen. Một tiếng cào xé nhè nhẹ vang lên từ phía sau cánh cửa gỗ đang đóng kín."
]

# Sample 2: Phàm Nhân Tu Tiên (Thực dụng, logic sinh tồn)
phamnhan = [
    "Hàn Lập thu thập xong đồ vật trên thi thể, nét mặt không chút thay đổi, tiện tay búng ra một ngọn Hỏa Cầu Thuật.",
    "Ngọn lửa bùng lên, nhanh chóng thiêu rụi cái xác thành tro bụi. Chỉ khi gió thổi bay đi tàn tro cuối cùng, hắn mới thở hắt ra một hơi, ánh mắt lộ vẻ mệt mỏi.",
    "Tu tiên giới là vậy, không giết người thì người giết mình. Lão giả kia nếu không vì tham lam viên Trúc Cơ Đan trong tay hắn, cũng sẽ không rơi vào kết cục hồn phi phách tán này.",
    "Hắn không vội vã rời đi mà cẩn thận rải một lớp phấn xóa dấu vết xung quanh, sau đó mới bấm pháp quyết, hóa thành một đạo thanh quang bay vút về phía chân trời.",
    "Tư chất hắn bình thường, chỉ có thể cẩn trọng từng bước, mượn nhờ cái bình nhỏ bí ẩn kia để từ từ tích lũy tài nguyên. Bất kỳ sự kiêu ngạo hay bất cẩn nào ở thế giới này đều phải trả giá bằng mạng sống."
]

create_epub("Quy_Bi_Chi_Chu_Sample.epub", "Quỷ Bí Chi Chủ", quibi)
create_epub("Pham_Nhan_Tu_Tien_Sample.epub", "Phàm Nhân Tu Tiên", phamnhan)
