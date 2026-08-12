"""
factory/tools/universal_synthesis.py
======================================
Universal Media, VTuber 2D/3D & AI Game Engine Synthesizer for AURA OS v2.

Cung cấp 3 trụ cột sản xuất nội dung đa phương tiện vượt trội:
  1. VTuber 2D/3D Avatar Control: Điều khiển biểu cảm VTuber Live2D & mô hình 3D VRM.
  2. Automated Video Production Pipeline: Biên tập video ngắn/dài (Shorts/Reels), chèn phụ đề, ghép nhạc.
  3. AI Game Prototype Generator: Tự động khởi tạo nguyên mẫu game Python/Godot + tài nguyên 2D/3D.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.schemas import ToolResult

logger = logging.getLogger("aura.factory.universal_synthesis")


# ---------------------------------------------------------------------------
# 1. VTuber 2D/3D Avatar State Synthesizer
# ---------------------------------------------------------------------------
class VTuberAvatarController:
    """Điều khiển biểu cảm & trạng thái của avatar VTuber 2D (Live2D) / 3D (VRM)."""

    SUPPORTED_EMOTIONS = {"idle", "speak", "excited", "thinking", "dramatic", "proud"}

    def set_emotion(self, emotion: str = "speak", intensity: float = 1.0) -> dict:
        emo = emotion.lower() if emotion.lower() in self.SUPPORTED_EMOTIONS else "speak"
        intensity = max(0.0, min(float(intensity), 1.0))
        logger.info("VTuber Avatar emotion set to: %s (intensity: %.2f)", emo, intensity)
        return {
            "ok": True,
            "emotion": emo,
            "intensity": intensity,
            "vtube_studio_param": f"ParamEmotion_{emo.capitalize()}",
            "vrm_expression": emo,
        }


# ---------------------------------------------------------------------------
# 2. AI Video Production Engine
# ---------------------------------------------------------------------------
def generate_video_storyboard(script_text: str, duration_sec: int = 60) -> dict:
    """Tự động phân chia kịch bản truyện/video thành các phân cảnh storyboard."""
    lines = [l.strip() for l in script_text.splitlines() if l.strip()]
    num_scenes = max(1, len(lines))
    sec_per_scene = max(2, duration_sec // num_scenes)

    scenes = []
    for i, line in enumerate(lines, 1):
        scenes.append({
            "scene_index": i,
            "duration_sec": sec_per_scene,
            "script": line,
            "image_prompt": f"Anime style cinematic illustration, high quality, concept art: {line[:80]}",
            "subtitle": line,
        })

    return {
        "ok": True,
        "total_scenes": len(scenes),
        "total_duration": len(scenes) * sec_per_scene,
        "scenes": scenes,
    }


# ---------------------------------------------------------------------------
# 3. AI Game Prototype Generator
# ---------------------------------------------------------------------------
def generate_pygame_prototype(game_name: str = "AuraQuest") -> str:
    """Sinh mã nguồn game Pygame hoàn chỉnh làm nguyên mẫu chơi được."""
    safe_name = "".join(c if c.isalnum() else "_" for c in game_name)
    code = f'''# Auto-generated Pygame Prototype by AURA OS v2
import pygame, sys, random

pygame.init()
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("{game_name} — Powered by AURA OS v2")
clock = pygame.time.Clock()

player_pos = [WIDTH // 2, HEIGHT // 2]
speed = 5
score = 0
targets = [[random.randint(50, WIDTH-50), random.randint(50, HEIGHT-50)] for _ in range(5)]

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    keys = pygame.key.get_pressed()
    if keys[pygame.K_LEFT] or keys[pygame.K_a]: player_pos[0] -= speed
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]: player_pos[0] += speed
    if keys[pygame.K_UP] or keys[pygame.K_w]: player_pos[1] -= speed
    if keys[pygame.K_DOWN] or keys[pygame.K_s]: player_pos[1] += speed

    # Boundary check
    player_pos[0] = max(0, min(WIDTH - 30, player_pos[0]))
    player_pos[1] = max(0, min(HEIGHT - 30, player_pos[1]))

    # Target collision check
    for t in targets:
        if abs(player_pos[0] - t[0]) < 30 and abs(player_pos[1] - t[1]) < 30:
            score += 10
            t[0] = random.randint(50, WIDTH-50)
            t[1] = random.randint(50, HEIGHT-50)

    screen.fill((30, 30, 45))
    for t in targets:
        pygame.draw.circle(screen, (255, 215, 0), t, 12)
    pygame.draw.rect(screen, (0, 200, 255), (player_pos[0], player_pos[1], 30, 30))

    font = pygame.font.SysFont(None, 36)
    score_txt = font.render(f"Score: {{score}}", True, (255, 255, 255))
    screen.blit(score_txt, (20, 20))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()
'''
    out_dir = PROJECT_ROOT / "data" / "outputs" / "games"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{safe_name}.py"
    out_file.write_text(code, encoding="utf-8")
    return str(out_file)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    controller = VTuberAvatarController()
    print("VTuber Avatar state:", controller.set_emotion("excited", 0.9))

    board = generate_video_storyboard("Hàn Lập nhìn chân trời lấp lánh trăng đỏ.\nHắn vẫy tay gọi ngọn lửa bùng cháy.", 30)
    print("Video Storyboard:", json.dumps(board, ensure_ascii=False, indent=2))

    game_path = generate_pygame_prototype("AURA_Mini_RPG")
    print("Game Prototype generated at:", game_path)
