/**
 * Pixel God Sandbox - Advanced Civilization AI & Animated Entities
 */

import { ENTITY_TYPES, KINGDOM_COLORS, TILES, TILE_DATA } from './constants.js';
import { sound } from './audio.js';

let entityIdCounter = 1;
let kingdomIdCounter = 1;

export class EntityManager {
    constructor(world) {
        this.world = world;
        this.entities = [];
        this.kingdoms = new Map();
        this.buildings = [];
        this.selectedEntity = null;
    }

    clear() {
        this.entities = [];
        this.kingdoms.clear();
        this.buildings = [];
        this.selectedEntity = null;
    }

    // Spawn an Entity with rich stats & state machine
    spawn(x, y, type = ENTITY_TYPES.HUMAN, kingdomId = null) {
        if (!this.world.isWalkable(x, y) && type !== ENTITY_TYPES.DRAGON) {
            const n = this.world.getNeighbors(x, y).find(nb => this.world.isWalkable(nb.x, nb.y));
            if (n) {
                x = n.x;
                y = n.y;
            }
        }

        const entity = {
            id: entityIdCounter++,
            x: x + 0.5,
            y: y + 0.5,
            vx: 0,
            vy: 0,
            targetX: x + 0.5,
            targetY: y + 0.5,
            type: type,
            hp: this.getBaseHp(type),
            maxHp: this.getBaseHp(type),
            speed: this.getBaseSpeed(type),
            facing: Math.random() < 0.5 ? 1 : -1, // 1 = right, -1 = left
            walkAnimTime: Math.random() * 10,
            isMoving: false,
            age: 0,
            level: 1,
            kills: 0,
            wood: 0,
            stone: 0,
            kingdomId: kingdomId,
            actionState: 'wander', // 'wander', 'gather_wood', 'gather_stone', 'build', 'fight', 'hunt', 'flee', 'talk'
            actionTimer: Math.floor(Math.random() * 30),
            actionSubTimer: 0,
            speechBubble: null,
            speechTimer: 0,
            name: this.generateName(type),
            blessed: false
        };

        // Auto kingdom assignment
        if ((type === ENTITY_TYPES.HUMAN || type === ENTITY_TYPES.ELF || type === ENTITY_TYPES.ORC) && !kingdomId) {
            const nearestK = this.findNearestKingdom(x, y, 20);
            if (nearestK) {
                entity.kingdomId = nearestK.id;
            } else {
                const newK = this.createKingdom(x, y, type);
                entity.kingdomId = newK.id;
            }
        }

        this.entities.push(entity);
        sound.playSpawn();
        return entity;
    }

    getBaseHp(type) {
        switch (type) {
            case ENTITY_TYPES.HUMAN: return 100;
            case ENTITY_TYPES.ELF: return 120;
            case ENTITY_TYPES.ORC: return 160;
            case ENTITY_TYPES.SHEEP: return 40;
            case ENTITY_TYPES.WOLF: return 80;
            case ENTITY_TYPES.ZOMBIE: return 90;
            case ENTITY_TYPES.DRAGON: return 800;
            default: return 50;
        }
    }

    getBaseSpeed(type) {
        switch (type) {
            case ENTITY_TYPES.HUMAN: return 0.07;
            case ENTITY_TYPES.ELF: return 0.085;
            case ENTITY_TYPES.ORC: return 0.065;
            case ENTITY_TYPES.SHEEP: return 0.055;
            case ENTITY_TYPES.WOLF: return 0.095;
            case ENTITY_TYPES.ZOMBIE: return 0.045;
            case ENTITY_TYPES.DRAGON: return 0.12;
            default: return 0.06;
        }
    }

    generateName(type) {
        const humanNames = ['Arthur', 'Roland', 'Kael', 'Elena', 'Lyra', 'Marcus', 'Gareth', 'Freya', 'Valen', 'Thorne', 'Maya', 'Cedric'];
        const elfNames = ['Legolin', 'Aeloria', 'Silvan', 'Elrond', 'Faer', 'Thalia', 'Yvraine', 'Galen'];
        const orcNames = ['Grom', 'Morgok', 'Drak', 'Ugluk', 'Krag', 'Thokk', 'Azgash', 'Gorbag'];
        if (type === ENTITY_TYPES.HUMAN) return humanNames[Math.floor(Math.random() * humanNames.length)];
        if (type === ENTITY_TYPES.ELF) return elfNames[Math.floor(Math.random() * elfNames.length)];
        if (type === ENTITY_TYPES.ORC) return orcNames[Math.floor(Math.random() * orcNames.length)];
        return type.toUpperCase();
    }

    createKingdom(x, y, race = ENTITY_TYPES.HUMAN) {
        const colorConfig = KINGDOM_COLORS[(this.kingdoms.size) % KINGDOM_COLORS.length];
        const kingdom = {
            id: kingdomIdCounter++,
            name: colorConfig.name,
            race: race,
            color: colorConfig.primary,
            secondaryColor: colorConfig.secondary,
            flag: colorConfig.flag,
            capitalX: Math.floor(x),
            capitalY: Math.floor(y),
            wood: 25,
            stone: 15,
            level: 1,
            age: 0
        };

        this.kingdoms.set(kingdom.id, kingdom);

        // Build first Castle / Town Hall
        this.buildings.push({
            id: Date.now() + Math.random(),
            x: Math.floor(x),
            y: Math.floor(y),
            type: 'town_hall',
            kingdomId: kingdom.id,
            hp: 350,
            maxHp: 350,
            smokeTimer: 0
        });

        return kingdom;
    }

    findNearestKingdom(x, y, maxDist = 25) {
        let bestK = null;
        let minDist = maxDist;
        for (const k of this.kingdoms.values()) {
            const dist = Math.hypot(k.capitalX - x, k.capitalY - y);
            if (dist < minDist) {
                minDist = dist;
                bestK = k;
            }
        }
        return bestK;
    }

    // Main Update Loop
    update(particleSystem) {
        // 1. Update Kingdoms
        for (const kingdom of this.kingdoms.values()) {
            kingdom.age++;
            const pop = this.entities.filter(e => e.kingdomId === kingdom.id).length;
            if (pop === 0 && kingdom.age > 300) {
                this.kingdoms.delete(kingdom.id);
            }
        }

        // 2. Update Entities
        for (let i = this.entities.length - 1; i >= 0; i--) {
            const e = this.entities[i];
            e.age++;

            // Speech bubble timer
            if (e.speechTimer > 0) {
                e.speechTimer--;
                if (e.speechTimer <= 0) e.speechBubble = null;
            }

            const tileX = Math.floor(e.x);
            const tileY = Math.floor(e.y);
            const currentTile = this.world.getTile(tileX, tileY);

            // Environmental Hazards
            if (currentTile === TILES.LAVA) {
                e.hp -= 25;
                if (particleSystem) particleSystem.addFire(tileX, tileY);
            } else if (currentTile === TILES.FIRE) {
                e.hp -= 4;
            } else if (currentTile === TILES.ACID) {
                e.hp -= 12;
            } else if (currentTile === TILES.DEEP_WATER && e.type !== ENTITY_TYPES.DRAGON) {
                e.hp -= 1.5; // Drowning
            }

            // Death Check
            if (e.hp <= 0) {
                if (particleSystem) particleSystem.addText(e.x, e.y, '💀', '#ff4d4d');
                this.entities.splice(i, 1);
                continue;
            }

            // Run AI Behavior
            this.handleAI(e, particleSystem);

            // Move Towards Target / Apply Velocity
            this.moveEntity(e);
        }

        // 3. Update Buildings
        for (let i = this.buildings.length - 1; i >= 0; i--) {
            const b = this.buildings[i];
            const tile = this.world.getTile(b.x, b.y);

            // Chimney smoke
            b.smokeTimer = (b.smokeTimer || 0) + 1;
            if (b.smokeTimer > 40 && particleSystem && Math.random() < 0.6) {
                b.smokeTimer = 0;
                particleSystem.addSmoke(b.x, b.y - 1);
            }

            if (tile === TILES.FIRE || tile === TILES.LAVA) {
                b.hp -= 3;
            }
            if (b.hp <= 0) {
                this.buildings.splice(i, 1);
                if (particleSystem) particleSystem.addDebris(b.x, b.y);
            }
        }
    }

    moveEntity(e) {
        const dx = e.targetX - e.x;
        const dy = e.targetY - e.y;
        const dist = Math.hypot(dx, dy);

        if (dist > 0.15) {
            e.isMoving = true;
            e.walkAnimTime += 0.25;

            // Normalize and move
            const moveSpeed = e.speed * (e.blessed ? 1.4 : 1.0);
            const step = Math.min(dist, moveSpeed);
            const moveX = (dx / dist) * step;
            const moveY = (dy / dist) * step;

            // Facing direction
            if (Math.abs(dx) > 0.05) {
                e.facing = dx > 0 ? 1 : -1;
            }

            // Check Walkability
            let nextX = e.x + moveX;
            let nextY = e.y + moveY;

            if (e.type !== ENTITY_TYPES.DRAGON) {
                if (!this.world.isWalkable(Math.floor(nextX), Math.floor(e.y))) {
                    nextX = e.x;
                    e.targetX = e.x;
                }
                if (!this.world.isWalkable(Math.floor(e.x), Math.floor(nextY))) {
                    nextY = e.y;
                    e.targetY = e.y;
                }
            }

            e.x = Math.max(1, Math.min(this.world.width - 2, nextX));
            e.y = Math.max(1, Math.min(this.world.height - 2, nextY));
        } else {
            e.isMoving = false;
        }
    }

    handleAI(e, particleSystem) {
        e.actionTimer--;

        // DRAGON AI: Fly freely, breathe fire
        if (e.type === ENTITY_TYPES.DRAGON) {
            if (e.actionTimer <= 0 || Math.hypot(e.targetX - e.x, e.targetY - e.y) < 0.5) {
                e.actionTimer = 60 + Math.floor(Math.random() * 60);
                e.targetX = 10 + Math.random() * (this.world.width - 20);
                e.targetY = 10 + Math.random() * (this.world.height - 20);
                
                // Breathe fire occasionally
                if (Math.random() < 0.4) {
                    const tx = Math.floor(e.x);
                    const ty = Math.floor(e.y);
                    this.world.setBrush(tx, ty, TILES.FIRE, 2);
                    sound.playExplosion();
                    if (particleSystem) particleSystem.addText(e.x, e.y, '🔥 ROAR!', '#ff3300');
                }
            }
            return;
        }

        // ZOMBIE AI: Hunt living entities
        if (e.type === ENTITY_TYPES.ZOMBIE) {
            const victim = this.entities.find(other => 
                other.id !== e.id && 
                other.type !== ENTITY_TYPES.ZOMBIE && 
                other.type !== ENTITY_TYPES.DRAGON && 
                Math.hypot(other.x - e.x, other.y - e.y) < 18
            );

            if (victim) {
                e.targetX = victim.x;
                e.targetY = victim.y;
                if (Math.hypot(victim.x - e.x, victim.y - e.y) < 1.0) {
                    // Attack & Infect
                    victim.hp -= 20;
                    if (victim.hp <= 0) {
                        victim.type = ENTITY_TYPES.ZOMBIE;
                        victim.hp = 85;
                        victim.kingdomId = null;
                        if (particleSystem) particleSystem.addText(victim.x, victim.y, '🧟 Biến thành Zombie!', '#65e028');
                    }
                }
            } else {
                this.chooseWanderTarget(e);
            }
            return;
        }

        // SHEEP AI: Graze, flee from wolves
        if (e.type === ENTITY_TYPES.SHEEP) {
            const predator = this.entities.find(other => 
                (other.type === ENTITY_TYPES.WOLF || other.type === ENTITY_TYPES.ZOMBIE) && 
                Math.hypot(other.x - e.x, other.y - e.y) < 12
            );
            if (predator) {
                // Flee in opposite direction
                const angle = Math.atan2(e.y - predator.y, e.x - predator.x);
                e.targetX = Math.max(2, Math.min(this.world.width - 3, e.x + Math.cos(angle) * 8));
                e.targetY = Math.max(2, Math.min(this.world.height - 3, e.y + Math.sin(angle) * 8));
                e.actionState = 'flee';
            } else {
                this.chooseWanderTarget(e);
            }
            return;
        }

        // WOLF AI: Hunt sheep or humans
        if (e.type === ENTITY_TYPES.WOLF) {
            const prey = this.entities.find(other => 
                (other.type === ENTITY_TYPES.SHEEP || other.type === ENTITY_TYPES.HUMAN) && 
                Math.hypot(other.x - e.x, other.y - e.y) < 16
            );
            if (prey) {
                e.targetX = prey.x;
                e.targetY = prey.y;
                if (Math.hypot(prey.x - e.x, prey.y - e.y) < 1.0) {
                    prey.hp -= 18;
                    e.hp = Math.min(e.maxHp, e.hp + 12);
                    if (particleSystem) particleSystem.addText(e.x, e.y, '🥩 Cắn!', '#ef4444');
                }
            } else {
                this.chooseWanderTarget(e);
            }
            return;
        }

        // CIVILIZED BEINGS (HUMAN / ELF / ORC)
        const kingdom = this.kingdoms.get(e.kingdomId);

        // 1. COMBAT / DEFENSE
        const enemy = this.entities.find(other => 
            other.id !== e.id && 
            (other.type === ENTITY_TYPES.ZOMBIE || other.type === ENTITY_TYPES.WOLF || (other.kingdomId && other.kingdomId !== e.kingdomId)) &&
            Math.hypot(other.x - e.x, other.y - e.y) < 12
        );

        if (enemy) {
            e.targetX = enemy.x;
            e.targetY = enemy.y;
            e.actionState = 'fight';
            if (Math.hypot(enemy.x - e.x, enemy.y - e.y) < 1.3) {
                const dmg = e.type === ENTITY_TYPES.ORC ? 25 : (e.blessed ? 35 : 15);
                enemy.hp -= dmg;
                if (particleSystem) particleSystem.addText(enemy.x, enemy.y, `⚔️ -${dmg}`, '#ff3333');
            }
            return;
        }

        // 2. SOCIAL INTERACTION (GREETINGS & TALK)
        if (Math.random() < 0.02 && !e.speechBubble) {
            const friend = this.entities.find(other => 
                other.id !== e.id && 
                other.kingdomId === e.kingdomId && 
                Math.hypot(other.x - e.x, other.y - e.y) < 2.5
            );
            if (friend) {
                const emojis = ['💬', '👋', '❤️', '💡', '🌾', '🍺', '👑'];
                e.speechBubble = emojis[Math.floor(Math.random() * emojis.length)];
                e.speechTimer = 45;
            }
        }

        // 3. CIVILIZATION TASKS (LUMBERJACK, MINER, BUILDER)
        if (kingdom) {
            // Task A: Gather Wood
            if (e.wood < 5 && kingdom.wood < 100) {
                const nearestTree = this.findNearestTileType(Math.floor(e.x), Math.floor(e.y), TILES.FOREST, 20);
                if (nearestTree) {
                    e.actionState = 'gather_wood';
                    e.targetX = nearestTree.x + 0.5;
                    e.targetY = nearestTree.y + 0.5;
                    if (Math.hypot(nearestTree.x + 0.5 - e.x, nearestTree.y + 0.5 - e.y) < 1.2) {
                        this.world.setTile(nearestTree.x, nearestTree.y, TILES.GRASS);
                        e.wood += 5;
                        kingdom.wood += 5;
                        sound.playChop();
                        if (particleSystem) particleSystem.addText(e.x, e.y, '+5🪵', '#d99e52');
                    }
                    return;
                }
            }

            // Task B: Gather Stone
            if (e.stone < 5 && kingdom.stone < 60) {
                const nearestStone = this.findNearestTileType(Math.floor(e.x), Math.floor(e.y), TILES.MOUNTAIN, 20);
                if (nearestStone) {
                    e.actionState = 'gather_stone';
                    e.targetX = nearestStone.x + 0.5;
                    e.targetY = nearestStone.y + 0.5;
                    if (Math.hypot(nearestStone.x + 0.5 - e.x, nearestStone.y + 0.5 - e.y) < 1.5) {
                        e.stone += 3;
                        kingdom.stone += 3;
                        sound.playBuild();
                        if (particleSystem) particleSystem.addText(e.x, e.y, '+3🪨', '#a8b0bd');
                    }
                    return;
                }
            }

            // Task C: Build Houses
            if (kingdom.wood >= 15 && Math.random() < 0.1) {
                const bx = Math.floor(e.x);
                const by = Math.floor(e.y);
                const tile = this.world.getTile(bx, by);
                const hasBuilding = this.buildings.some(b => b.x === bx && b.y === by);

                if ((tile === TILES.GRASS || tile === TILES.SOIL) && !hasBuilding) {
                    kingdom.wood -= 15;
                    const bType = kingdom.stone >= 10 ? 'stone_house' : 'wooden_house';
                    if (bType === 'stone_house') kingdom.stone -= 10;

                    this.buildings.push({
                        id: Date.now() + Math.random(),
                        x: bx,
                        y: by,
                        type: bType,
                        kingdomId: kingdom.id,
                        hp: bType === 'stone_house' ? 220 : 130,
                        maxHp: bType === 'stone_house' ? 220 : 130,
                        smokeTimer: 0
                    });

                    sound.playBuild();
                    if (particleSystem) particleSystem.addText(bx, by, '🏠 Xây Nhà!', '#f7dda1');
                }
            }

            // Task D: Reproduction (Birth of new citizens)
            const kingdomPop = this.entities.filter(c => c.kingdomId === kingdom.id).length;
            const kingdomHouses = this.buildings.filter(b => b.kingdomId === kingdom.id).length;
            if (kingdomPop < kingdomHouses * 3 + 2 && Math.random() < 0.008) {
                this.spawn(e.x, e.y, e.type, kingdom.id);
                if (particleSystem) particleSystem.addText(e.x, e.y, '👶 Dân Số Mới', '#ffb3ba');
            }
        }

        // 4. ACTIVE WANDER
        e.actionState = 'wander';
        this.chooseWanderTarget(e);
    }

    chooseWanderTarget(e) {
        if (e.actionTimer <= 0 || Math.hypot(e.targetX - e.x, e.targetY - e.y) < 0.4) {
            e.actionTimer = 40 + Math.floor(Math.random() * 50);
            
            // Pick a walkable point 4-8 tiles away
            for (let tries = 0; tries < 8; tries++) {
                const angle = Math.random() * Math.PI * 2;
                const dist = 3 + Math.random() * 5;
                const candX = e.x + Math.cos(angle) * dist;
                const candY = e.y + Math.sin(angle) * dist;
                const tileX = Math.floor(candX);
                const tileY = Math.floor(candY);

                if (this.world.isWalkable(tileX, tileY)) {
                    e.targetX = candX;
                    e.targetY = candY;
                    break;
                }
            }
        }
    }

    findNearestTileType(startX, startY, tileType, maxRadius = 20) {
        for (let r = 1; r <= maxRadius; r += 2) {
            for (let dy = -r; dy <= r; dy += 2) {
                for (let dx = -r; dx <= r; dx += 2) {
                    const tx = startX + dx;
                    const ty = startY + dy;
                    if (this.world.getTile(tx, ty) === tileType) {
                        return { x: tx, y: ty };
                    }
                }
            }
        }
        return null;
    }
}
