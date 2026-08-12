/**
 * Pixel God Sandbox - World Simulation Matrix & Cellular Automata
 */

import { WORLD_WIDTH, WORLD_HEIGHT, TILES, TILE_DATA } from './constants.js';

export class World {
    constructor(width = WORLD_WIDTH, height = WORLD_HEIGHT) {
        this.width = width;
        this.height = height;
        this.size = width * height;
        
        // Primary tile buffer and secondary buffer for cellular updates
        this.tiles = new Uint8Array(this.size);
        this.nextTiles = new Uint8Array(this.size);
        
        // Metadata buffers (burn timers, moisture, road levels)
        this.fireLife = new Uint8Array(this.size);
        this.temperature = new Int8Array(this.size); // -50 to 100
        
        this.age = 0; // World simulation step
        this.generatePreset('continents');
    }

    getIndex(x, y) {
        if (x < 0 || x >= this.width || y < 0 || y >= this.height) return -1;
        return y * this.width + x;
    }

    getTile(x, y) {
        const idx = this.getIndex(x, y);
        if (idx === -1) return TILES.DEEP_WATER;
        return this.tiles[idx];
    }

    setTile(x, y, tileType) {
        const idx = this.getIndex(x, y);
        if (idx !== -1) {
            this.tiles[idx] = tileType;
            if (tileType === TILES.FIRE) {
                this.fireLife[idx] = 40 + Math.floor(Math.random() * 30);
            } else {
                this.fireLife[idx] = 0;
            }
        }
    }

    setBrush(cx, cy, tileType, radius = 2) {
        const r2 = radius * radius;
        for (let dy = -radius; dy <= radius; dy++) {
            for (let dx = -radius; dx <= radius; dx++) {
                if (dx * dx + dy * dy <= r2) {
                    const x = Math.floor(cx + dx);
                    const y = Math.floor(cy + dy);
                    this.setTile(x, y, tileType);
                }
            }
        }
    }

    isWalkable(x, y) {
        const t = this.getTile(x, y);
        const data = TILE_DATA[t];
        return data ? data.walkable : false;
    }

    isLiquid(x, y) {
        const t = this.getTile(x, y);
        const data = TILE_DATA[t];
        return data ? data.liquid : false;
    }

    // Cellular Automata Step
    step(particleSystem) {
        this.age++;
        this.nextTiles.set(this.tiles);

        // Process a random subset or interleaved grid for peak 60fps performance
        for (let y = 0; y < this.height; y++) {
            for (let x = 0; x < this.width; x++) {
                const idx = y * this.width + x;
                const tile = this.tiles[idx];

                // 1. FIRE PHYSICS
                if (tile === TILES.FIRE) {
                    if (this.fireLife[idx] > 0) {
                        this.fireLife[idx]--;
                        
                        // Particle FX
                        if (particleSystem && Math.random() < 0.2) {
                            particleSystem.addSmoke(x, y);
                        }

                        // Fire spread to neighbors
                        const neighbors = this.getNeighbors(x, y);
                        for (const n of neighbors) {
                            const nTile = this.tiles[n.idx];
                            if (TILE_DATA[nTile] && TILE_DATA[nTile].flammable && Math.random() < 0.12) {
                                this.nextTiles[n.idx] = TILES.FIRE;
                                this.fireLife[n.idx] = 35 + Math.floor(Math.random() * 25);
                            }
                            // Water extinguishes fire
                            if (nTile === TILES.SHALLOW_WATER || nTile === TILES.DEEP_WATER) {
                                this.nextTiles[idx] = TILES.ASH;
                                this.fireLife[idx] = 0;
                            }
                        }
                    } else {
                        // Fire burns out into Ash or Soil
                        this.nextTiles[idx] = Math.random() < 0.7 ? TILES.ASH : TILES.SOIL;
                    }
                }

                // 2. LAVA PHYSICS
                else if (tile === TILES.LAVA) {
                    const neighbors = this.getNeighbors(x, y);
                    for (const n of neighbors) {
                        const nTile = this.tiles[n.idx];
                        // Lava burns flammable things
                        if (TILE_DATA[nTile] && TILE_DATA[nTile].flammable) {
                            this.nextTiles[n.idx] = TILES.FIRE;
                            this.fireLife[n.idx] = 60;
                        }
                        // Lava + Water = Stone & Basalt (Steam)
                        else if (nTile === TILES.SHALLOW_WATER || nTile === TILES.DEEP_WATER) {
                            this.nextTiles[n.idx] = TILES.MOUNTAIN;
                            this.nextTiles[idx] = TILES.MOUNTAIN;
                            if (particleSystem) particleSystem.addSteam(x, y);
                        }
                        // Lava melts ice
                        else if (nTile === TILES.ICE || nTile === TILES.SNOW_PEAK) {
                            this.nextTiles[n.idx] = TILES.SHALLOW_WATER;
                        }
                        // Lava flow down/side slowly
                        else if (nTile === TILES.SOIL || nTile === TILES.SAND) {
                            if (Math.random() < 0.01) {
                                this.nextTiles[n.idx] = TILES.LAVA;
                            }
                        }
                    }
                }

                // 3. VEGETATION GROWTH & NATURE
                else if (tile === TILES.SOIL) {
                    // Turn soil to grass if near water/grass
                    if (Math.random() < 0.008) {
                        const neighbors = this.getNeighbors(x, y);
                        const hasGrassOrWater = neighbors.some(n => 
                            this.tiles[n.idx] === TILES.GRASS || 
                            this.tiles[n.idx] === TILES.SHALLOW_WATER || 
                            this.tiles[n.idx] === TILES.FOREST
                        );
                        if (hasGrassOrWater) {
                            this.nextTiles[idx] = TILES.GRASS;
                        }
                    }
                }
                else if (tile === TILES.GRASS) {
                    // Spread forests slowly
                    if (Math.random() < 0.001) {
                        const neighbors = this.getNeighbors(x, y);
                        const nearForest = neighbors.some(n => this.tiles[n.idx] === TILES.FOREST);
                        if (nearForest) {
                            this.nextTiles[idx] = TILES.FOREST;
                        }
                    }
                }
                else if (tile === TILES.ASH) {
                    // Ash decays to soil over time
                    if (Math.random() < 0.003) {
                        this.nextTiles[idx] = TILES.SOIL;
                    }
                }

                // 4. ACID DISSOLUTION
                else if (tile === TILES.ACID) {
                    const neighbors = this.getNeighbors(x, y);
                    for (const n of neighbors) {
                        const nTile = this.tiles[n.idx];
                        if (nTile !== TILES.ACID && nTile !== TILES.DEEP_WATER && Math.random() < 0.04) {
                            this.nextTiles[n.idx] = TILES.SHALLOW_WATER;
                            if (particleSystem) particleSystem.addAcidBubble(n.x, n.y);
                        }
                    }
                    if (Math.random() < 0.01) {
                        this.nextTiles[idx] = TILES.SHALLOW_WATER;
                    }
                }
            }
        }

        this.tiles.set(this.nextTiles);
    }

    getNeighbors(x, y) {
        const list = [];
        const offsets = [
            [-1, 0], [1, 0], [0, -1], [0, 1]
        ];
        for (const [ox, oy] of offsets) {
            const nx = x + ox;
            const ny = y + oy;
            const idx = this.getIndex(nx, ny);
            if (idx !== -1) {
                list.push({ x: nx, y: ny, idx });
            }
        }
        return list;
    }

    // Procedural Map Generators
    generatePreset(type = 'continents') {
        const noise = this.createNoiseGrid();

        for (let y = 0; y < this.height; y++) {
            for (let x = 0; x < this.width; x++) {
                const idx = y * this.width + x;
                const val = noise[idx];

                if (type === 'continents') {
                    if (val < 0.38) this.tiles[idx] = TILES.DEEP_WATER;
                    else if (val < 0.44) this.tiles[idx] = TILES.SHALLOW_WATER;
                    else if (val < 0.47) this.tiles[idx] = TILES.SAND;
                    else if (val < 0.65) this.tiles[idx] = TILES.GRASS;
                    else if (val < 0.78) this.tiles[idx] = TILES.FOREST;
                    else if (val < 0.90) this.tiles[idx] = TILES.MOUNTAIN;
                    else this.tiles[idx] = TILES.SNOW_PEAK;
                } 
                else if (type === 'archipelago') {
                    // Island cluster
                    const distFromCenter = Math.hypot(x - this.width / 2, y - this.height / 2) / (this.width / 2);
                    const islandVal = val - distFromCenter * 0.4;
                    if (islandVal < 0.28) this.tiles[idx] = TILES.DEEP_WATER;
                    else if (islandVal < 0.35) this.tiles[idx] = TILES.SHALLOW_WATER;
                    else if (islandVal < 0.39) this.tiles[idx] = TILES.SAND;
                    else if (islandVal < 0.60) this.tiles[idx] = TILES.GRASS;
                    else if (islandVal < 0.75) this.tiles[idx] = TILES.FOREST;
                    else this.tiles[idx] = TILES.MOUNTAIN;
                }
                else if (type === 'volcano') {
                    const dist = Math.hypot(x - this.width / 2, y - this.height / 2);
                    if (dist < 12) {
                        this.tiles[idx] = TILES.LAVA;
                    } else if (dist < 28) {
                        this.tiles[idx] = TILES.MOUNTAIN;
                    } else if (dist < 45) {
                        this.tiles[idx] = val > 0.5 ? TILES.FOREST : TILES.GRASS;
                    } else if (dist < 55) {
                        this.tiles[idx] = TILES.SAND;
                    } else if (dist < 70) {
                        this.tiles[idx] = TILES.SHALLOW_WATER;
                    } else {
                        this.tiles[idx] = TILES.DEEP_WATER;
                    }
                }
                else if (type === 'chaos') {
                    const r = Math.random();
                    if (r < 0.3) this.tiles[idx] = TILES.DEEP_WATER;
                    else if (r < 0.5) this.tiles[idx] = TILES.GRASS;
                    else if (r < 0.7) this.tiles[idx] = TILES.FOREST;
                    else if (r < 0.85) this.tiles[idx] = TILES.MOUNTAIN;
                    else if (r < 0.95) this.tiles[idx] = TILES.LAVA;
                    else this.tiles[idx] = TILES.ICE;
                }
            }
        }
    }

    // Fast multi-octave pseudo noise for terrain
    createNoiseGrid() {
        const grid = new Float32Array(this.size);
        const seeds = [
            { scale: 0.02, weight: 0.6, ox: Math.random() * 1000, oy: Math.random() * 1000 },
            { scale: 0.05, weight: 0.3, ox: Math.random() * 1000, oy: Math.random() * 1000 },
            { scale: 0.12, weight: 0.1, ox: Math.random() * 1000, oy: Math.random() * 1000 }
        ];

        for (let y = 0; y < this.height; y++) {
            for (let x = 0; x < this.width; x++) {
                let total = 0;
                for (const s of seeds) {
                    const sx = (x + s.ox) * s.scale;
                    const sy = (y + s.oy) * s.scale;
                    total += (Math.sin(sx) * Math.cos(sy) * 0.5 + 0.5) * s.weight;
                }
                grid[y * this.width + x] = total;
            }
        }
        return grid;
    }
}
