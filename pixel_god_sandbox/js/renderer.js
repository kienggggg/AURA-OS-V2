/**
 * Pixel God Sandbox - Rich Pixel-Art Renderer & Animation System
 */

import { TILE_DATA, TILES, ENTITY_TYPES } from './constants.js';

export class ParticleSystem {
    constructor() {
        this.particles = [];
        this.floatingTexts = [];
        this.lightningBolts = [];
    }

    addSmoke(x, y) {
        this.particles.push({
            x: x + 0.5 + (Math.random() - 0.5) * 0.4,
            y: y,
            vx: (Math.random() - 0.5) * 0.05,
            vy: -0.1 - Math.random() * 0.1,
            size: 1.8 + Math.random() * 1.5,
            color: 'rgba(120, 125, 135, 0.65)',
            life: 35
        });
    }

    addFire(x, y) {
        this.particles.push({
            x: x + 0.5 + (Math.random() - 0.5) * 0.5,
            y: y + 0.5,
            vx: (Math.random() - 0.5) * 0.2,
            vy: -0.25 - Math.random() * 0.2,
            size: 1.4 + Math.random() * 1.6,
            color: Math.random() < 0.5 ? '#ff4d00' : '#ffb700',
            life: 22
        });
    }

    addSteam(x, y) {
        this.particles.push({
            x: x + 0.5,
            y: y,
            vx: (Math.random() - 0.5) * 0.1,
            vy: -0.2,
            size: 2.8,
            color: 'rgba(235, 245, 255, 0.75)',
            life: 35
        });
    }

    addRainDrop(x, y) {
        this.particles.push({
            x: x + (Math.random() - 0.5) * 1.0,
            y: y - 4,
            vx: 0.08,
            vy: 0.8,
            size: 1.0,
            color: '#7be3ff',
            life: 18
        });
    }

    addAcidBubble(x, y) {
        this.particles.push({
            x: x + Math.random(),
            y: y + Math.random(),
            vx: 0,
            vy: -0.15,
            size: 1.4,
            color: '#65e028',
            life: 25
        });
    }

    addDebris(x, y) {
        for (let i = 0; i < 8; i++) {
            this.particles.push({
                x: x + 0.5,
                y: y + 0.5,
                vx: (Math.random() - 0.5) * 0.6,
                vy: (Math.random() - 0.5) * 0.6,
                size: 1.6,
                color: '#8b5a2b',
                life: 25
            });
        }
    }

    addMeteorImpact(x, y) {
        for (let i = 0; i < 45; i++) {
            const angle = Math.random() * Math.PI * 2;
            const spd = Math.random() * 1.5 + 0.5;
            this.particles.push({
                x: x,
                y: y,
                vx: Math.cos(angle) * spd,
                vy: Math.sin(angle) * spd,
                size: 2.5 + Math.random() * 2.5,
                color: Math.random() < 0.5 ? '#ff3300' : '#ffbb00',
                life: 45
            });
        }
    }

    addLightningBolt(targetX, targetY) {
        this.lightningBolts.push({
            startX: targetX + (Math.random() - 0.5) * 10,
            startY: targetY - 40,
            targetX: targetX,
            targetY: targetY,
            life: 10
        });
    }

    addText(x, y, text, color = '#ffffff') {
        this.floatingTexts.push({
            x: x,
            y: y,
            text: text,
            color: color,
            life: 45,
            maxLife: 45
        });
    }

    update() {
        for (let i = this.particles.length - 1; i >= 0; i--) {
            const p = this.particles[i];
            p.x += p.vx;
            p.y += p.vy;
            p.life--;
            if (p.life <= 0) this.particles.splice(i, 1);
        }

        for (let i = this.floatingTexts.length - 1; i >= 0; i--) {
            const t = this.floatingTexts[i];
            t.y -= 0.035;
            t.life--;
            if (t.life <= 0) this.floatingTexts.splice(i, 1);
        }

        for (let i = this.lightningBolts.length - 1; i >= 0; i--) {
            const b = this.lightningBolts[i];
            b.life--;
            if (b.life <= 0) this.lightningBolts.splice(i, 1);
        }
    }
}

export class Renderer {
    constructor(canvas, world, entityManager) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.world = world;
        this.entityManager = entityManager;
        this.particleSystem = new ParticleSystem();

        // Viewport & Camera
        this.zoom = 4.8;
        this.targetZoom = 4.8;
        this.cameraX = world.width / 2;
        this.cameraY = world.height / 2;
        this.targetCameraX = this.cameraX;
        this.targetCameraY = this.cameraY;

        // Visual effects
        this.shakeIntensity = 0;
        this.shakeDuration = 0;
        this.flashColor = null;
        this.flashAlpha = 0;
        this.animTime = 0;

        // Fast Tile Buffer
        this.tileCanvas = document.createElement('canvas');
        this.tileCanvas.width = world.width;
        this.tileCanvas.height = world.height;
        this.tileCtx = this.tileCanvas.getContext('2d');
        this.tileImageData = this.tileCtx.createImageData(world.width, world.height);

        this.resize();
        window.addEventListener('resize', () => this.resize());
    }

    resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    shake(intensity = 10, duration = 15) {
        this.shakeIntensity = intensity;
        this.shakeDuration = duration;
    }

    flashScreen(color = '#ffffff', alpha = 0.7) {
        this.flashColor = color;
        this.flashAlpha = alpha;
    }

    screenToWorld(screenX, screenY) {
        const cx = this.canvas.width / 2;
        const cy = this.canvas.height / 2;
        const wx = (screenX - cx) / this.zoom + this.cameraX;
        const wy = (screenY - cy) / this.zoom + this.cameraY;
        return { x: wx, y: wy };
    }

    worldToScreen(worldX, worldY) {
        const cx = this.canvas.width / 2;
        const cy = this.canvas.height / 2;
        const sx = (worldX - this.cameraX) * this.zoom + cx;
        const sy = (worldY - this.cameraY) * this.zoom + cy;
        return { x: sx, y: sy };
    }

    render() {
        this.animTime += 0.05;

        // Smooth camera lerp
        this.cameraX += (this.targetCameraX - this.cameraX) * 0.15;
        this.cameraY += (this.targetCameraY - this.cameraY) * 0.15;
        this.zoom += (this.targetZoom - this.zoom) * 0.15;

        // Clear Canvas
        this.ctx.fillStyle = '#060911';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        // Screen Shake
        let shakeOffsetX = 0;
        let shakeOffsetY = 0;
        if (this.shakeDuration > 0) {
            this.shakeDuration--;
            shakeOffsetX = (Math.random() - 0.5) * this.shakeIntensity;
            shakeOffsetY = (Math.random() - 0.5) * this.shakeIntensity;
        }

        this.ctx.save();
        this.ctx.translate(
            this.canvas.width / 2 + shakeOffsetX,
            this.canvas.height / 2 + shakeOffsetY
        );
        this.ctx.scale(this.zoom, this.zoom);
        this.ctx.translate(-this.cameraX, -this.cameraY);

        this.ctx.imageSmoothingEnabled = false;

        // 1. RENDER BASE TEXTURED TILES
        this.renderTilesToOffscreen();
        this.ctx.drawImage(this.tileCanvas, 0, 0);

        // 2. RENDER FORESTS / PIXEL TREES
        this.renderPixelTrees();

        // 3. RENDER KINGDOM BORDERS & CAPITALS
        this.renderKingdomTerritory();

        // 4. RENDER BUILDINGS
        this.renderBuildings();

        // 5. RENDER DETAILED ANIMATED ENTITIES
        this.renderEntities();

        // 6. RENDER PARTICLES & SPEECH BUBBLES
        this.renderParticles();

        this.ctx.restore();

        // 7. RENDER FULLSCREEN FLASH
        if (this.flashAlpha > 0.01) {
            this.ctx.fillStyle = this.flashColor;
            this.ctx.globalAlpha = this.flashAlpha;
            this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
            this.ctx.globalAlpha = 1.0;
            this.flashAlpha *= 0.88;
        }
    }

    renderTilesToOffscreen() {
        const data = this.tileImageData.data;
        const tiles = this.world.tiles;
        const width = this.world.width;
        const height = this.world.height;
        const time = this.animTime;

        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const idx = y * width + x;
                const tileType = tiles[idx];
                let [r, g, b] = (TILE_DATA[tileType] && TILE_DATA[tileType].rgb) ? TILE_DATA[tileType].rgb : [0, 0, 0];

                // Procedural Pixel Shading & Animation
                const hash = (x * 73856093 ^ y * 19349663) % 256;

                // A. Water Waves Animation
                if (tileType === TILES.DEEP_WATER || tileType === TILES.SHALLOW_WATER) {
                    const wave = Math.sin(time * 1.5 + x * 0.4 + y * 0.3);
                    if (wave > 0.6) {
                        r += 15; g += 25; b += 35; // wave crest highlight
                    } else if (wave < -0.6) {
                        r -= 10; g -= 10; b -= 15; // wave trough
                    }
                }
                // B. Grass Texture
                else if (tileType === TILES.GRASS) {
                    if (hash < 60) {
                        r += 8; g += 15; b += 5; // bright blade
                    } else if (hash > 200) {
                        r -= 10; g -= 12; b -= 8; // dark shade
                    } else if (hash === 128) {
                        // Tiny flower dot
                        r = 255; g = 230; b = 80;
                    }
                }
                // C. Sand Dunes
                else if (tileType === TILES.SAND) {
                    if (hash < 80) { r += 10; g += 8; b += 5; }
                    else if (hash > 180) { r -= 12; g -= 10; b -= 8; }
                }
                // D. Mountain Crags
                else if (tileType === TILES.MOUNTAIN) {
                    if (hash < 90) { r += 18; g += 18; b += 20; }
                    else if (hash > 170) { r -= 20; g -= 20; b -= 22; }
                }
                // E. Magma / Lava Bubbling
                else if (tileType === TILES.LAVA) {
                    const pulse = Math.sin(time * 3 + x * 0.8 + y * 0.8);
                    if (pulse > 0.3) {
                        r = 255; g = 140; b = 20; // glowing hotspot
                    } else {
                        r = 210; g = 40; b = 10;
                    }
                }

                const p = idx * 4;
                data[p] = Math.max(0, Math.min(255, r));
                data[p + 1] = Math.max(0, Math.min(255, g));
                data[p + 2] = Math.max(0, Math.min(255, b));
                data[p + 3] = 255;
            }
        }

        this.tileCtx.putImageData(this.tileImageData, 0, 0);
    }

    renderPixelTrees() {
        const tiles = this.world.tiles;
        const width = this.world.width;
        const height = this.world.height;
        const wind = Math.sin(this.animTime * 1.8) * 0.15;

        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const idx = y * width + x;
                if (tiles[idx] === TILES.FOREST) {
                    // Tree Trunk
                    this.ctx.fillStyle = '#5c3a1e';
                    this.ctx.fillRect(x + 0.4, y + 0.4, 0.25, 0.6);

                    // Tree Leaf Canopy with wind sway
                    const sway = wind * Math.sin(x * 0.5 + y);
                    
                    // Dark leaf shadow
                    this.ctx.fillStyle = '#1c5e1b';
                    this.ctx.fillRect(x + 0.1 + sway, y - 0.3, 0.85, 0.75);

                    // Bright leaf highlight
                    this.ctx.fillStyle = '#2e8c2d';
                    this.ctx.fillRect(x + 0.2 + sway, y - 0.4, 0.65, 0.55);

                    // Top leaf tip
                    this.ctx.fillStyle = '#48b846';
                    this.ctx.fillRect(x + 0.35 + sway, y - 0.55, 0.35, 0.25);
                }
            }
        }
    }

    renderKingdomTerritory() {
        for (const k of this.entityManager.kingdoms.values()) {
            // Capital banner
            this.ctx.fillStyle = k.color;
            this.ctx.fillRect(k.capitalX - 0.5, k.capitalY - 2.2, 2.0, 1.2);
            this.ctx.font = '1.8px sans-serif';
            this.ctx.fillText(k.flag, k.capitalX - 0.3, k.capitalY - 2.4);

            // Kingdom Name
            this.ctx.fillStyle = '#ffffff';
            this.ctx.font = 'bold 1.1px sans-serif';
            this.ctx.fillText(k.name, k.capitalX - 2.5, k.capitalY - 3.0);
        }
    }

    renderBuildings() {
        for (const b of this.entityManager.buildings) {
            const kingdom = this.entityManager.kingdoms.get(b.kingdomId);
            const color = kingdom ? kingdom.color : '#8a6543';

            if (b.type === 'town_hall') {
                // Castle Tower Base
                this.ctx.fillStyle = '#475569';
                this.ctx.fillRect(b.x - 0.7, b.y - 1.4, 2.4, 2.4);
                // Doorway
                this.ctx.fillStyle = '#1e293b';
                this.ctx.fillRect(b.x + 0.1, b.y + 0.2, 0.8, 0.8);
                // Battlements
                this.ctx.fillStyle = '#64748b';
                this.ctx.fillRect(b.x - 0.8, b.y - 1.8, 0.6, 0.5);
                this.ctx.fillRect(b.x + 0.2, b.y - 1.8, 0.6, 0.5);
                this.ctx.fillRect(b.x + 1.2, b.y - 1.8, 0.6, 0.5);
                // Flag Pole & Banner
                this.ctx.fillStyle = '#cbd5e1';
                this.ctx.fillRect(b.x + 0.4, b.y - 2.6, 0.2, 0.9);
                this.ctx.fillStyle = color;
                this.ctx.fillRect(b.x + 0.6, b.y - 2.6, 0.9, 0.5);
            } else if (b.type === 'stone_house') {
                // Stone House Walls
                this.ctx.fillStyle = '#64748b';
                this.ctx.fillRect(b.x - 0.4, b.y - 0.8, 1.8, 1.8);
                // Glowing Window
                this.ctx.fillStyle = '#fde047';
                this.ctx.fillRect(b.x - 0.1, b.y - 0.3, 0.4, 0.4);
                // Slate Roof
                this.ctx.fillStyle = '#991b1b';
                this.ctx.fillRect(b.x - 0.6, b.y - 1.3, 2.2, 0.6);
                // Chimney
                this.ctx.fillStyle = '#334155';
                this.ctx.fillRect(b.x + 0.8, b.y - 1.6, 0.4, 0.6);
            } else {
                // Wooden Cottage
                this.ctx.fillStyle = '#92400e';
                this.ctx.fillRect(b.x - 0.3, b.y - 0.7, 1.6, 1.6);
                // Door
                this.ctx.fillStyle = '#451a03';
                this.ctx.fillRect(b.x + 0.2, b.y + 0.2, 0.5, 0.7);
                // Thatch Roof
                this.ctx.fillStyle = '#b45309';
                this.ctx.fillRect(b.x - 0.5, b.y - 1.1, 2.0, 0.5);
            }
        }
    }

    renderEntities() {
        for (const e of this.entityManager.entities) {
            const kingdom = this.entityManager.kingdoms.get(e.kingdomId);

            // Ground Shadow
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
            this.ctx.beginPath();
            this.ctx.ellipse(e.x, e.y + 0.4, 0.7, 0.35, 0, 0, Math.PI * 2);
            this.ctx.fill();

            // Blessed Golden Aura
            if (e.blessed) {
                const auraGlow = Math.sin(this.animTime * 4) * 0.2 + 0.5;
                this.ctx.fillStyle = `rgba(255, 230, 80, ${auraGlow})`;
                this.ctx.beginPath();
                this.ctx.arc(e.x, e.y - 0.4, 1.5, 0, Math.PI * 2);
                this.ctx.fill();
            }

            // Walking Bobbing Animation
            const walkBob = e.isMoving ? Math.abs(Math.sin(e.walkAnimTime * 2)) * 0.15 : 0;
            const legSwing = e.isMoving ? Math.sin(e.walkAnimTime * 2) * 0.25 : 0;
            const dir = e.facing; // 1 = right, -1 = left

            // --- DRAW CHARACTER SPRITES ---
            this.ctx.save();
            this.ctx.translate(e.x, e.y - walkBob);

            switch (e.type) {
                case ENTITY_TYPES.HUMAN:
                case ENTITY_TYPES.ELF:
                case ENTITY_TYPES.ORC: {
                    const isElf = e.type === ENTITY_TYPES.ELF;
                    const isOrc = e.type === ENTITY_TYPES.ORC;

                    // 1. Moving Legs
                    this.ctx.fillStyle = '#1e293b';
                    this.ctx.fillRect(-0.25 + legSwing, 0.1, 0.22, 0.4);
                    this.ctx.fillRect(0.05 - legSwing, 0.1, 0.22, 0.4);

                    // 2. Body / Armor / Tunic
                    let tunicColor = kingdom ? kingdom.color : '#3b82f6';
                    if (isOrc) tunicColor = '#15803d';
                    this.ctx.fillStyle = tunicColor;
                    this.ctx.fillRect(-0.35, -0.6, 0.7, 0.75);

                    // 3. Head & Skin
                    let skinColor = '#fed7aa'; // Human skin
                    if (isElf) skinColor = '#fef08a'; // Fair Elf
                    if (isOrc) skinColor = '#16a34a'; // Green Orc
                    this.ctx.fillStyle = skinColor;
                    this.ctx.fillRect(-0.3, -1.15, 0.6, 0.6);

                    // 4. Eyes & Facial Direction
                    this.ctx.fillStyle = '#0f172a';
                    const eyeOffset = dir > 0 ? 0.05 : -0.15;
                    this.ctx.fillRect(-0.1 + eyeOffset, -0.95, 0.12, 0.15);
                    this.ctx.fillRect(0.1 + eyeOffset, -0.95, 0.12, 0.15);

                    // 5. Hair / Ears
                    if (isElf) {
                        this.ctx.fillStyle = '#fde047'; // Blonde hair
                        this.ctx.fillRect(-0.35, -1.25, 0.7, 0.25);
                        // Pointy Elf ears
                        this.ctx.fillStyle = skinColor;
                        this.ctx.fillRect(-0.45, -1.0, 0.15, 0.2);
                        this.ctx.fillRect(0.3, -1.0, 0.15, 0.2);
                    } else if (!isOrc) {
                        this.ctx.fillStyle = '#78350f'; // Brown hair
                        this.ctx.fillRect(-0.35, -1.25, 0.7, 0.25);
                    }

                    // 6. Tools in Hand based on Action
                    if (e.actionState === 'gather_wood') {
                        // Tiny Lumber Axe
                        this.ctx.fillStyle = '#78350f';
                        this.ctx.fillRect(dir * 0.4, -0.5, 0.12, 0.6);
                        this.ctx.fillStyle = '#94a3b8';
                        this.ctx.fillRect(dir * 0.35, -0.65, dir * 0.3, 0.22);
                    } else if (e.actionState === 'gather_stone') {
                        // Pickaxe
                        this.ctx.fillStyle = '#78350f';
                        this.ctx.fillRect(dir * 0.4, -0.5, 0.12, 0.6);
                        this.ctx.fillStyle = '#64748b';
                        this.ctx.fillRect(dir * 0.3, -0.65, dir * 0.4, 0.15);
                    } else if (e.actionState === 'fight') {
                        // Sword
                        this.ctx.fillStyle = '#e2e8f0';
                        this.ctx.fillRect(dir * 0.35, -0.9, 0.15, 0.8);
                        this.ctx.fillStyle = '#d97706';
                        this.ctx.fillRect(dir * 0.3, -0.35, 0.25, 0.12);
                    }
                    break;
                }

                case ENTITY_TYPES.SHEEP: {
                    // Moving Hooves
                    this.ctx.fillStyle = '#1e293b';
                    this.ctx.fillRect(-0.4 + legSwing, 0.2, 0.15, 0.3);
                    this.ctx.fillRect(0.2 - legSwing, 0.2, 0.15, 0.3);

                    // Fluffy Wool Body
                    this.ctx.fillStyle = '#f8fafc';
                    this.ctx.fillRect(-0.55, -0.4, 1.1, 0.65);
                    this.ctx.fillStyle = '#e2e8f0';
                    this.ctx.fillRect(-0.45, -0.5, 0.9, 0.2);

                    // Black Face
                    this.ctx.fillStyle = '#1e293b';
                    this.ctx.fillRect(dir > 0 ? 0.3 : -0.65, -0.45, 0.4, 0.4);
                    break;
                }

                case ENTITY_TYPES.WOLF: {
                    // Moving Paws
                    this.ctx.fillStyle = '#334155';
                    this.ctx.fillRect(-0.5 + legSwing, 0.2, 0.18, 0.3);
                    this.ctx.fillRect(0.3 - legSwing, 0.2, 0.18, 0.3);

                    // Fur Body
                    this.ctx.fillStyle = '#475569';
                    this.ctx.fillRect(-0.6, -0.3, 1.2, 0.55);
                    // Pointy Ears & Snout
                    this.ctx.fillStyle = '#334155';
                    const snoutX = dir > 0 ? 0.4 : -0.7;
                    this.ctx.fillRect(snoutX, -0.4, 0.4, 0.4);
                    // Glowing Red Eye
                    this.ctx.fillStyle = '#ef4444';
                    this.ctx.fillRect(snoutX + (dir > 0 ? 0.2 : 0.1), -0.3, 0.12, 0.12);
                    // Wagging Tail
                    this.ctx.fillStyle = '#475569';
                    this.ctx.fillRect(dir > 0 ? -0.8 : 0.6, -0.4 + legSwing, 0.25, 0.4);
                    break;
                }

                case ENTITY_TYPES.ZOMBIE: {
                    // Shambling Legs
                    this.ctx.fillStyle = '#14532d';
                    this.ctx.fillRect(-0.2 + legSwing, 0.1, 0.2, 0.4);
                    this.ctx.fillRect(0.1 - legSwing, 0.1, 0.2, 0.4);

                    // Rotting Body
                    this.ctx.fillStyle = '#3f6212';
                    this.ctx.fillRect(-0.35, -0.6, 0.7, 0.75);

                    // Outstretched Green Arms
                    this.ctx.fillStyle = '#65a30d';
                    this.ctx.fillRect(dir > 0 ? 0.2 : -0.7, -0.5, 0.6, 0.2);

                    // Zombie Head
                    this.ctx.fillStyle = '#84cc16';
                    this.ctx.fillRect(-0.3, -1.15, 0.6, 0.6);
                    // Bloodshot Eye
                    this.ctx.fillStyle = '#dc2626';
                    this.ctx.fillRect(dir > 0 ? 0.1 : -0.2, -0.95, 0.15, 0.15);
                    break;
                }

                case ENTITY_TYPES.DRAGON: {
                    // Massive Dragon Body
                    this.ctx.fillStyle = '#b91c1c';
                    this.ctx.fillRect(-1.6, -0.8, 3.2, 1.6);
                    // Golden Belly
                    this.ctx.fillStyle = '#fbbf24';
                    this.ctx.fillRect(-1.0, -0.3, 2.0, 0.9);

                    // Animated Wings
                    const wingFlap = Math.sin(this.animTime * 6) * 1.0;
                    this.ctx.fillStyle = '#7f1d1d';
                    this.ctx.fillRect(-2.4, -2.0 + wingFlap, 1.4, 1.6);
                    this.ctx.fillRect(1.0, -2.0 + wingFlap, 1.4, 1.6);

                    // Dragon Head with Horns
                    const headX = dir > 0 ? 1.4 : -2.0;
                    this.ctx.fillStyle = '#dc2626';
                    this.ctx.fillRect(headX, -1.2, 0.9, 0.9);
                    this.ctx.fillStyle = '#fef08a';
                    this.ctx.fillRect(headX + (dir > 0 ? 0.5 : 0.1), -1.0, 0.2, 0.2);
                    break;
                }
            }

            this.ctx.restore();

            // Health Bar if Damaged
            if (e.hp < e.maxHp) {
                const barW = 1.8;
                const hpPercent = Math.max(0, e.hp / e.maxHp);
                this.ctx.fillStyle = '#0f172a';
                this.ctx.fillRect(e.x - barW / 2, e.y - 1.8, barW, 0.3);
                this.ctx.fillStyle = hpPercent > 0.5 ? '#22c55e' : '#ef4444';
                this.ctx.fillRect(e.x - barW / 2, e.y - 1.8, barW * hpPercent, 0.3);
            }

            // Speech / Thought Bubble
            if (e.speechBubble) {
                const bubbleY = e.y - 2.0 - Math.sin(this.animTime * 5) * 0.1;
                this.ctx.fillStyle = 'rgba(255, 255, 255, 0.92)';
                this.ctx.fillRect(e.x - 0.7, bubbleY - 0.7, 1.4, 1.0);
                this.ctx.font = '1.3px sans-serif';
                this.ctx.fillText(e.speechBubble, e.x - 0.5, bubbleY);
            }
        }
    }

    renderParticles() {
        for (const p of this.particleSystem.particles) {
            this.ctx.fillStyle = p.color;
            this.ctx.beginPath();
            this.ctx.arc(p.x, p.y, p.size * 0.25, 0, Math.PI * 2);
            this.ctx.fill();
        }

        for (const bolt of this.particleSystem.lightningBolts) {
            this.ctx.strokeStyle = '#ffffff';
            this.ctx.lineWidth = 0.9;
            this.ctx.beginPath();
            this.ctx.moveTo(bolt.startX, bolt.startY);
            const midX = (bolt.startX + bolt.targetX) / 2 + (Math.random() - 0.5) * 6;
            const midY = (bolt.startY + bolt.targetY) / 2;
            this.ctx.lineTo(midX, midY);
            this.ctx.lineTo(bolt.targetX, bolt.targetY);
            this.ctx.stroke();
        }

        for (const t of this.particleSystem.floatingTexts) {
            const alpha = t.life / t.maxLife;
            this.ctx.fillStyle = t.color;
            this.ctx.globalAlpha = alpha;
            this.ctx.font = 'bold 1.5px sans-serif';
            this.ctx.fillText(t.text, t.x - 1.2, t.y);
            this.ctx.globalAlpha = 1.0;
        }
    }
}
