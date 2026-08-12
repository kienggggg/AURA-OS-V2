/**
 * Pixel God Sandbox - God Powers, Spells & Disasters
 */

import { TILES, ENTITY_TYPES } from './constants.js';
import { sound } from './audio.js';

export class PowerManager {
    static execute(powerId, targetX, targetY, world, entityManager, particleSystem, renderer) {
        const tx = Math.floor(targetX);
        const ty = Math.floor(targetY);

        switch (powerId) {
            case 'lightning':
                this.castLightning(tx, ty, world, entityManager, particleSystem, renderer);
                break;
            case 'meteor':
                this.castMeteor(tx, ty, world, entityManager, particleSystem, renderer);
                break;
            case 'nuke':
                this.castNuke(tx, ty, world, entityManager, particleSystem, renderer);
                break;
            case 'rain':
                this.castHolyRain(tx, ty, world, entityManager, particleSystem);
                break;
            case 'blessing':
                this.castBlessing(tx, ty, world, entityManager, particleSystem);
                break;
            case 'grow':
                this.castSpeedGrowth(tx, ty, world, entityManager, particleSystem);
                break;
            case 'zombie_virus':
                this.castZombieVirus(tx, ty, entityManager, particleSystem);
                break;
            case 'eraser':
                this.erase(tx, ty, world, entityManager, particleSystem);
                break;
        }
    }

    static castLightning(x, y, world, entityManager, particleSystem, renderer) {
        sound.playThunder();
        if (renderer) renderer.shake(12, 10);
        if (particleSystem) particleSystem.addLightningBolt(x, y);

        // Explode small radius
        world.setBrush(x, y, TILES.FIRE, 2);

        // Strike entities
        for (const e of entityManager.entities) {
            if (Math.hypot(e.x - x, e.y - y) < 4) {
                e.hp -= 200;
                if (particleSystem) particleSystem.addText(e.x, e.y, '⚡-200', '#ffff55');
            }
        }
    }

    static castMeteor(x, y, world, entityManager, particleSystem, renderer) {
        sound.playExplosion();
        if (renderer) renderer.shake(25, 20);

        // Visual meteor strike
        if (particleSystem) {
            particleSystem.addMeteorImpact(x, y);
            particleSystem.addText(x, y, '☄️ BOOM!', '#ff4400');
        }

        // Lava crater
        const craterRadius = 6;
        for (let dy = -craterRadius; dy <= craterRadius; dy++) {
            for (let dx = -craterRadius; dx <= craterRadius; dx++) {
                const dist = Math.hypot(dx, dy);
                const px = x + dx;
                const py = y + dy;
                if (dist <= 3) {
                    world.setTile(px, py, TILES.LAVA);
                } else if (dist <= 5) {
                    world.setTile(px, py, TILES.FIRE);
                } else if (dist <= craterRadius) {
                    world.setTile(px, py, TILES.ASH);
                }
            }
        }

        // Kill in impact zone
        for (let i = entityManager.entities.length - 1; i >= 0; i--) {
            const e = entityManager.entities[i];
            if (Math.hypot(e.x - x, e.y - y) < craterRadius + 2) {
                e.hp -= 500;
            }
        }

        // Destroy buildings
        for (let i = entityManager.buildings.length - 1; i >= 0; i--) {
            const b = entityManager.buildings[i];
            if (Math.hypot(b.x - x, b.y - y) < craterRadius + 2) {
                entityManager.buildings.splice(i, 1);
            }
        }
    }

    static castNuke(x, y, world, entityManager, particleSystem, renderer) {
        sound.playDisaster();
        if (renderer) {
            renderer.shake(40, 30);
            renderer.flashScreen('#ffffff', 0.8);
        }

        const blastRadius = 16;
        for (let dy = -blastRadius; dy <= blastRadius; dy++) {
            for (let dx = -blastRadius; dx <= blastRadius; dx++) {
                const dist = Math.hypot(dx, dy);
                const px = x + dx;
                const py = y + dy;
                if (dist <= blastRadius) {
                    if (dist < 6) {
                        world.setTile(px, py, TILES.LAVA);
                    } else if (dist < 12) {
                        world.setTile(px, py, TILES.FIRE);
                    } else {
                        world.setTile(px, py, TILES.ASH);
                    }
                }
            }
        }

        // Wipe entities and buildings in radius
        entityManager.entities = entityManager.entities.filter(e => Math.hypot(e.x - x, e.y - y) >= blastRadius);
        entityManager.buildings = entityManager.buildings.filter(b => Math.hypot(b.x - x, b.y - y) >= blastRadius);

        if (particleSystem) {
            particleSystem.addText(x, y, '☢️ TSAR BOMBA', '#ffff00');
        }
    }

    static castHolyRain(x, y, world, entityManager, particleSystem) {
        sound.playSplash();
        const rainRadius = 14;

        for (let dy = -rainRadius; dy <= rainRadius; dy++) {
            for (let dx = -rainRadius; dx <= rainRadius; dx++) {
                const px = x + dx;
                const py = y + dy;
                const tile = world.getTile(px, py);

                if (tile === TILES.FIRE) {
                    world.setTile(px, py, TILES.ASH);
                } else if (tile === TILES.ASH) {
                    world.setTile(px, py, TILES.SOIL);
                } else if (tile === TILES.SOIL && Math.random() < 0.3) {
                    world.setTile(px, py, TILES.GRASS);
                }
                if (particleSystem && Math.random() < 0.15) {
                    particleSystem.addRainDrop(px, py);
                }
            }
        }

        // Heal entities in rain
        for (const e of entityManager.entities) {
            if (Math.hypot(e.x - x, e.y - y) < rainRadius) {
                e.hp = Math.min(e.maxHp, e.hp + 50);
            }
        }

        if (particleSystem) particleSystem.addText(x, y, '🌧️ Mưa Phước Lành', '#73d7ff');
    }

    static castBlessing(x, y, world, entityManager, particleSystem) {
        sound.playBlessing();
        const blessRadius = 10;

        for (const e of entityManager.entities) {
            if (Math.hypot(e.x - x, e.y - y) < blessRadius) {
                e.hp = e.maxHp * 2;
                e.maxHp *= 2;
                e.speed *= 1.3;
                e.blessed = true;
                if (particleSystem) particleSystem.addText(e.x, e.y, '✨ Ban Phước!', '#ffea79');
            }
        }

        for (let dy = -blessRadius; dy <= blessRadius; dy++) {
            for (let dx = -blessRadius; dx <= blessRadius; dx++) {
                const px = x + dx;
                const py = y + dy;
                const tile = world.getTile(px, py);
                if (tile === TILES.GRASS && Math.random() < 0.2) {
                    world.setTile(px, py, TILES.FOREST);
                }
            }
        }
    }

    static castSpeedGrowth(x, y, world, entityManager, particleSystem) {
        sound.playBlessing();
        const growRadius = 8;
        for (let dy = -growRadius; dy <= growRadius; dy++) {
            for (let dx = -growRadius; dx <= growRadius; dx++) {
                const px = x + dx;
                const py = y + dy;
                const tile = world.getTile(px, py);
                if (tile === TILES.SOIL) world.setTile(px, py, TILES.GRASS);
                else if (tile === TILES.GRASS) world.setTile(px, py, TILES.FOREST);
            }
        }
        if (particleSystem) particleSystem.addText(x, y, '🌿 Tăng Trưởng Thần Tốc', '#55ff77');
    }

    static castZombieVirus(x, y, entityManager, particleSystem) {
        sound.playDisaster();
        const plagueRadius = 8;
        for (const e of entityManager.entities) {
            if (Math.hypot(e.x - x, e.y - y) < plagueRadius && e.type !== ENTITY_TYPES.ZOMBIE && e.type !== ENTITY_TYPES.DRAGON) {
                e.type = ENTITY_TYPES.ZOMBIE;
                e.hp = 90;
                e.kingdomId = null;
                if (particleSystem) particleSystem.addText(e.x, e.y, '🧟 Bị Nhiễm!', '#33cc33');
            }
        }
    }

    static erase(x, y, world, entityManager, particleSystem) {
        const eraseRadius = 4;
        entityManager.entities = entityManager.entities.filter(e => Math.hypot(e.x - x, e.y - y) >= eraseRadius);
        entityManager.buildings = entityManager.buildings.filter(b => Math.hypot(b.x - x, b.y - y) >= eraseRadius);
        if (particleSystem) particleSystem.addText(x, y, '🧹 Xóa Bỏ', '#cccccc');
    }
}
