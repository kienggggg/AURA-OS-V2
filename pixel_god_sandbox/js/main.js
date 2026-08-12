/**
 * Pixel God Sandbox - Main Entry & UI Orchestrator
 */

import { World } from './world.js';
import { EntityManager } from './entities.js';
import { Renderer } from './renderer.js';
import { TouchController } from './touch_controls.js';
import { PowerManager } from './powers.js';
import { GOD_TOOLS, TOOL_CATEGORIES, TILE_DATA, TILES } from './constants.js';
import { sound } from './audio.js';

class GameApp {
    constructor() {
        this.canvas = document.getElementById('gameCanvas');
        this.world = new World();
        this.entityManager = new EntityManager(this.world);
        this.renderer = new Renderer(this.canvas, this.world, this.entityManager);

        this.touchController = new TouchController(
            this.canvas,
            this.renderer,
            (tool, wx, wy, brush) => this.handleAction(tool, wx, wy, brush),
            (wx, wy) => this.handleInspect(wx, wy)
        );

        // Simulation parameters
        this.simSpeed = 1; // 0 = pause, 1 = normal, 2 = fast, 5 = ultra
        this.lastFrameTime = performance.now();
        this.fps = 60;
        this.activeCategory = TOOL_CATEGORIES.TERRAIN;
        this.activeTool = GOD_TOOLS[0]; // Shallow water

        this.initUI();
        this.touchController.setActiveTool(this.activeTool);

        // Populate world with initial starter population
        this.spawnStarterCiv();

        // Start Game Loop
        this.loop = this.loop.bind(this);
        requestAnimationFrame(this.loop);
    }

    spawnStarterCiv() {
        // Find multiple suitable green spots for kingdoms
        let kingdomsSpawned = 0;
        for (let i = 0; i < 40 && kingdomsSpawned < 3; i++) {
            const rx = 25 + Math.floor(Math.random() * (this.world.width - 50));
            const ry = 25 + Math.floor(Math.random() * (this.world.height - 50));
            if (this.world.getTile(rx, ry) === TILES.GRASS || this.world.getTile(rx, ry) === TILES.FOREST) {
                const race = kingdomsSpawned === 0 ? 'human' : (kingdomsSpawned === 1 ? 'elf' : 'orc');
                // Spawn founder group
                const leader = this.entityManager.spawn(rx, ry, race);
                this.entityManager.spawn(rx + 1, ry, race, leader.kingdomId);
                this.entityManager.spawn(rx - 1, ry + 1, race, leader.kingdomId);
                this.entityManager.spawn(rx + 2, ry - 1, race, leader.kingdomId);
                
                // Spawn nearby sheep herd
                this.entityManager.spawn(rx + 3, ry + 2, 'sheep');
                this.entityManager.spawn(rx + 4, ry + 3, 'sheep');

                kingdomsSpawned++;
            }
        }

        // Spawn a wolf pack in the wilderness
        for (let i = 0; i < 20; i++) {
            const wx = 20 + Math.floor(Math.random() * (this.world.width - 40));
            const wy = 20 + Math.floor(Math.random() * (this.world.height - 40));
            if (this.world.isWalkable(wx, wy)) {
                this.entityManager.spawn(wx, wy, 'wolf');
                this.entityManager.spawn(wx + 1, wy + 1, 'wolf');
                break;
            }
        }
    }

    handleAction(tool, wx, wy, brushRadius) {
        if (!tool) return;
        const tx = Math.floor(wx);
        const ty = Math.floor(wy);

        if (tool.tile !== undefined) {
            // Draw Terrain / Fire / Acid
            this.world.setBrush(tx, ty, tool.tile, brushRadius);
        } else if (tool.entity) {
            // Spawn Entity
            this.entityManager.spawn(tx, ty, tool.entity);
        } else if (tool.power) {
            // Cast God Power / Disaster
            PowerManager.execute(
                tool.power, 
                wx, 
                wy, 
                this.world, 
                this.entityManager, 
                this.renderer.particleSystem, 
                this.renderer
            );
        } else if (tool.action === 'eraser') {
            PowerManager.execute(
                'eraser', 
                wx, 
                wy, 
                this.world, 
                this.entityManager, 
                this.renderer.particleSystem, 
                this.renderer
            );
        }
    }

    handleInspect(wx, wy) {
        const tx = Math.floor(wx);
        const ty = Math.floor(wy);
        const tileType = this.world.getTile(tx, ty);
        const tdata = TILE_DATA[tileType] || { name: 'Vô định' };

        // Look for entity near click
        const entity = this.entityManager.entities.find(e => Math.hypot(e.x - wx, e.y - wy) < 2.5);
        const building = this.entityManager.buildings.find(b => Math.hypot(b.x - tx, b.y - ty) < 2.0);

        const inspectPanel = document.getElementById('inspectPanel');
        const inspectBody = document.getElementById('inspectBody');

        let html = `<div class="inspect-row"><span>Địa hình:</span> <strong>${tdata.name}</strong> (${tx}, ${ty})</div>`;

        if (entity) {
            const kingdom = this.entityManager.kingdoms.get(entity.kingdomId);
            html += `
                <div class="inspect-section">
                    <div class="inspect-title">👤 ${entity.name} (${entity.type.toUpperCase()})</div>
                    <div class="inspect-row"><span>Sinh lực:</span> <strong>${Math.floor(entity.hp)} / ${entity.maxHp}</strong></div>
                    <div class="inspect-row"><span>Trạng thái:</span> <strong>${entity.blessed ? '✨ Được Ban Phước' : 'Bình thường'}</strong></div>
                    <div class="inspect-row"><span>Gỗ / Đá mang theo:</span> <strong>🪵 ${entity.wood} | 🪨 ${entity.stone}</strong></div>
                    <div class="inspect-row"><span>Vương quốc:</span> <strong>${kingdom ? kingdom.flag + ' ' + kingdom.name : 'Vô gia cư'}</strong></div>
                </div>
            `;
        }

        if (building) {
            const kingdom = this.entityManager.kingdoms.get(building.kingdomId);
            html += `
                <div class="inspect-section">
                    <div class="inspect-title">🏛️ ${building.type.replace('_', ' ').toUpperCase()}</div>
                    <div class="inspect-row"><span>Độ bền:</span> <strong>${building.hp} / ${building.maxHp}</strong></div>
                    <div class="inspect-row"><span>Thuộc:</span> <strong>${kingdom ? kingdom.name : 'Hoang tàn'}</strong></div>
                </div>
            `;
        }

        inspectBody.innerHTML = html;
        inspectPanel.classList.remove('hidden');
    }

    initUI() {
        // 1. Render Category Buttons
        const catBar = document.getElementById('categoryBar');
        catBar.innerHTML = `
            <button class="cat-btn active" data-cat="${TOOL_CATEGORIES.TERRAIN}">🌍 Địa Hình</button>
            <button class="cat-btn" data-cat="${TOOL_CATEGORIES.NATURE}">🌿 Thiên Nhiên</button>
            <button class="cat-btn" data-cat="${TOOL_CATEGORIES.CIVILIZATION}">👑 Văn Minh</button>
            <button class="cat-btn" data-cat="${TOOL_CATEGORIES.POWERS}">✨ Quyền Năng</button>
            <button class="cat-btn" data-cat="${TOOL_CATEGORIES.DISASTERS}">💣 Thảm Họa</button>
            <button class="cat-btn" data-cat="${TOOL_CATEGORIES.INSPECT}">🔍 Soi & Xóa</button>
        `;

        catBar.addEventListener('click', (e) => {
            const btn = e.target.closest('.cat-btn');
            if (!btn) return;
            document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            this.activeCategory = btn.dataset.cat;
            this.renderToolDrawer();
        });

        // 2. Initial Tool Drawer
        this.renderToolDrawer();

        // 3. Brush Size Selector
        document.querySelectorAll('.brush-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.brush-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const size = parseInt(btn.dataset.size, 10);
                this.touchController.setBrushSize(size);
            });
        });

        // 4. Speed & Controls
        document.getElementById('pauseBtn').addEventListener('click', () => {
            this.simSpeed = this.simSpeed === 0 ? 1 : 0;
            document.getElementById('pauseBtn').innerText = this.simSpeed === 0 ? '▶️ Tiếp tục' : '⏸️ Tạm dừng';
        });

        document.getElementById('speedBtn').addEventListener('click', () => {
            if (this.simSpeed === 1) this.simSpeed = 2;
            else if (this.simSpeed === 2) this.simSpeed = 4;
            else this.simSpeed = 1;
            document.getElementById('speedBtn').innerText = `⚡ ${this.simSpeed}x`;
        });

        document.getElementById('audioBtn').addEventListener('click', () => {
            const isMuted = sound.toggleMute();
            document.getElementById('audioBtn').innerText = isMuted ? '🔇' : '🔊';
        });

        // 5. Preset Map Dropdown
        document.getElementById('mapPresetSelect').addEventListener('change', (e) => {
            const preset = e.target.value;
            this.entityManager.clear();
            this.world.generatePreset(preset);
            this.spawnStarterCiv();
        });

        // Close Inspect Panel
        document.getElementById('closeInspectBtn').addEventListener('click', () => {
            document.getElementById('inspectPanel').classList.add('hidden');
        });
    }

    renderToolDrawer() {
        const drawer = document.getElementById('toolDrawer');
        const tools = GOD_TOOLS.filter(t => t.category === this.activeCategory);

        drawer.innerHTML = tools.map(t => `
            <button class="tool-btn ${this.activeTool && this.activeTool.id === t.id ? 'active' : ''}" data-id="${t.id}">
                <span class="tool-icon">${t.icon}</span>
                <span class="tool-name">${t.name}</span>
            </button>
        `).join('');

        drawer.querySelectorAll('.tool-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                drawer.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const toolId = btn.dataset.id;
                this.activeTool = GOD_TOOLS.find(t => t.id === toolId);
                this.touchController.setActiveTool(this.activeTool);
                
                // Show tooltip description briefly
                document.getElementById('toolDesc').innerText = this.activeTool.desc;
            });
        });

        if (tools.length > 0) {
            const currentInCat = tools.find(t => this.activeTool && t.id === this.activeTool.id);
            if (!currentInCat) {
                this.activeTool = tools[0];
                this.touchController.setActiveTool(this.activeTool);
                const firstBtn = drawer.querySelector('.tool-btn');
                if (firstBtn) firstBtn.classList.add('active');
            }
            document.getElementById('toolDesc').innerText = this.activeTool.desc;
        }
    }

    loop(currentTime) {
        requestAnimationFrame(this.loop);

        // FPS Calculation
        const delta = currentTime - this.lastFrameTime;
        this.lastFrameTime = currentTime;
        this.fps = Math.round(1000 / (delta || 1));

        // Simulation Update
        if (this.simSpeed > 0) {
            for (let step = 0; step < this.simSpeed; step++) {
                this.world.step(this.renderer.particleSystem);
                this.entityManager.update(this.renderer.particleSystem);
            }
        }

        // Particle System Update
        this.renderer.particleSystem.update();

        // Render Canvas
        this.renderer.render();

        // Update Status Bar
        document.getElementById('statPop').innerText = this.entityManager.entities.length;
        document.getElementById('statKingdoms').innerText = this.entityManager.kingdoms.size;
        document.getElementById('statAge').innerText = Math.floor(this.world.age / 10);
        document.getElementById('statFps').innerText = this.fps;
    }
}

// Boot the Sandbox when DOM is ready
window.addEventListener('DOMContentLoaded', () => {
    window.game = new GameApp();
});
