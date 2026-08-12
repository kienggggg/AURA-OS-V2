import os
import zipfile
import random
from html.parser import HTMLParser

class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs= True
        self.fed = []
    def handle_data(self, d):
        self.fed.append(d)
    def get_data(self):
        return ''.join(self.fed)

def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()

def get_epub_samples(epubs_dir=r"d:\AURA_OS_v2\data\reference_epubs", num_samples=2):
    """
    Đọc ngẫu nhiên các đoạn văn từ các file EPUB trong thư mục để làm mẫu Few-Shot.
    """
    if not os.path.exists(epubs_dir):
        return ""
    
    epub_files = [f for f in os.listdir(epubs_dir) if f.endswith(".epub")]
    if not epub_files:
        return ""
    
    samples = []
    for _ in range(num_samples):
        # Chọn ngẫu nhiên 1 file
        epub_path = os.path.join(epubs_dir, random.choice(epub_files))
        try:
            with zipfile.ZipFile(epub_path, 'r') as archive:
                # Lấy danh sách các file html/xhtml
                html_files = [f for f in archive.namelist() if f.endswith('.html') or f.endswith('.xhtml') or f.endswith('.htm')]
                if not html_files:
                    continue
                
                # Chọn ngẫu nhiên 1 file html
                target_file = random.choice(html_files)
                content = archive.read(target_file).decode('utf-8', errors='ignore')
                text = strip_tags(content)
                
                # Chia thành các đoạn văn
                paragraphs = [p.strip() for p in text.split('\n') if len(p.strip()) > 100] # Chỉ lấy đoạn dài
                
                if paragraphs:
                    # Lấy ngẫu nhiên 1-2 đoạn liên tiếp
                    start_idx = random.randint(0, len(paragraphs) - 1)
                    snippet = " ".join(paragraphs[start_idx:min(start_idx+2, len(paragraphs))])
                    
                    if len(snippet) > 500:
                        snippet = snippet[:500] + "..."
                        
                    samples.append(f"✅ VÍ DỤ VĂN PHONG (Trích từ {os.path.basename(epub_path)}):\n\"{snippet}\"")
        except Exception as e:
            print(f"Lỗi khi đọc {epub_path}: {e}")
            pass
            
    if not samples:
        return ""
        
    return "\n\n=== VÍ DỤ TRÍCH XUẤT TỪ EPUB BẠN CUNG CẤP ===\n" + "\n\n".join(samples)

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("Test extraction:")
    print(get_epub_samples())
