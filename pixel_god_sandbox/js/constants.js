/**
 * Pixel God Sandbox - Constants & Configurations
 */

// World Grid Dimensions
export const WORLD_WIDTH = 220;
export const WORLD_HEIGHT = 150;
export const TILE_SIZE = 4; // base pixel render size

// Tile Types (Bitmask or IDs)
export const TILES = {
    DEEP_WATER: 0,
    SHALLOW_WATER: 1,
    SAND: 2,
    SOIL: 3,
    GRASS: 4,
    FOREST: 5,
    MOUNTAIN: 6,
    SNOW_PEAK: 7,
    LAVA: 8,
    FIRE: 9,
    ASH: 10,
    ICE: 11,
    ACID: 12,
    ROAD: 13,
    WALL: 14
};

// Tile Color Palette & Properties (Hex + RGB for fast canvas rendering)
export const TILE_DATA = {
    [TILES.DEEP_WATER]: {
        name: 'Đại Dương',
        color: '#1a4f8a',
        rgb: [26, 79, 138],
        solid: false,
        liquid: true,
        flammable: false,
        walkable: false
    },
    [TILES.SHALLOW_WATER]: {
        name: 'Nước Nông',
        color: '#348be8',
        rgb: [52, 139, 232],
        solid: false,
        liquid: true,
        flammable: false,
        walkable: true,
        speedMultiplier: 0.5
    },
    [TILES.SAND]: {
        name: 'Bãi Cát',
        color: '#e5c158',
        rgb: [229, 193, 88],
        solid: true,
        liquid: false,
        flammable: false,
        walkable: true,
        speedMultiplier: 0.8
    },
    [TILES.SOIL]: {
        name: 'Đất',
        color: '#734828',
        rgb: [115, 72, 40],
        solid: true,
        liquid: false,
        flammable: false,
        walkable: true,
        speedMultiplier: 0.9
    },
    [TILES.GRASS]: {
        name: 'Đồng Cỏ',
        color: '#489c29',
        rgb: [72, 156, 41],
        solid: true,
        liquid: false,
        flammable: true,
        walkable: true,
        speedMultiplier: 1.0
    },
    [TILES.FOREST]: {
        name: 'Rừng Rậm',
        color: '#286b1b',
        rgb: [40, 107, 27],
        solid: true,
        liquid: false,
        flammable: true,
        walkable: true,
        speedMultiplier: 0.7,
        woodYield: 5
    },
    [TILES.MOUNTAIN]: {
        name: 'Núi Đá',
        color: '#6e7075',
        rgb: [110, 112, 117],
        solid: true,
        liquid: false,
        flammable: false,
        walkable: false,
        stoneYield: 10
    },
    [TILES.SNOW_PEAK]: {
        name: 'Đỉnh Tuyết',
        color: '#e4ebf2',
        rgb: [228, 235, 242],
        solid: true,
        liquid: false,
        flammable: false,
        walkable: false
    },
    [TILES.LAVA]: {
        name: 'Dung Nham',
        color: '#f0431a',
        rgb: [240, 67, 26],
        solid: false,
        liquid: true,
        flammable: false,
        walkable: false,
        damage: 999
    },
    [TILES.FIRE]: {
        name: 'Ngọn Lửa',
        color: '#ff9019',
        rgb: [255, 144, 25],
        solid: false,
        liquid: false,
        flammable: false,
        walkable: true,
        damage: 25
    },
    [TILES.ASH]: {
        name: 'Tro Tàn',
        color: '#383838',
        rgb: [56, 56, 56],
        solid: true,
        liquid: false,
        flammable: false,
        walkable: true
    },
    [TILES.ICE]: {
        name: 'Băng Giá',
        color: '#93d4f0',
        rgb: [147, 212, 240],
        solid: true,
        liquid: false,
        flammable: false,
        walkable: true,
        speedMultiplier: 1.2
    },
    [TILES.ACID]: {
        name: 'Axit Ăn Mòn',
        color: '#65e028',
        rgb: [101, 224, 40],
        solid: false,
        liquid: true,
        flammable: false,
        walkable: false
    },
    [TILES.ROAD]: {
        name: 'Đường Làng',
        color: '#a3937b',
        rgb: [163, 147, 123],
        solid: true,
        liquid: false,
        flammable: false,
        walkable: true,
        speedMultiplier: 1.4
    },
    [TILES.WALL]: {
        name: 'Tường Thành',
        color: '#4a4e59',
        rgb: [74, 78, 89],
        solid: true,
        liquid: false,
        flammable: false,
        walkable: false
    }
};

// Entity Types
export const ENTITY_TYPES = {
    HUMAN: 'human',
    ELF: 'elf',
    ORC: 'orc',
    SHEEP: 'sheep',
    WOLF: 'wolf',
    ZOMBIE: 'zombie',
    DRAGON: 'dragon'
};

// Kingdom Colors for visual banners and territory
export const KINGDOM_COLORS = [
    { name: 'Hoàng Gia Lam', primary: '#2d72d9', secondary: '#94bdfa', flag: '🛡️' },
    { name: 'Đế Chế Hồng Ngọc', primary: '#d92d43', secondary: '#faa2ad', flag: '⚔️' },
    { name: 'Vương Quốc Lục Bảo', primary: '#22a849', secondary: '#93e8ab', flag: '🌲' },
    { name: 'Đế Quốc Hoàng Kim', primary: '#db9b1a', secondary: '#f7dda1', flag: '👑' },
    { name: 'Vương Triều Hắc Ám', primary: '#792dd9', secondary: '#cba2fa', flag: '🔮' }
];

// God Power / Tool Categories
export const TOOL_CATEGORIES = {
    TERRAIN: 'terrain',
    NATURE: 'nature',
    CIVILIZATION: 'civilization',
    POWERS: 'powers',
    DISASTERS: 'disasters',
    INSPECT: 'inspect'
};

// Available Tools List
export const GOD_TOOLS = [
    // Terrain
    { id: 'shallow_water', category: TOOL_CATEGORIES.TERRAIN, name: 'Nước Biển', icon: '🌊', tile: TILES.SHALLOW_WATER, desc: 'Vẽ nước nông, sông ngòi' },
    { id: 'deep_water', category: TOOL_CATEGORIES.TERRAIN, name: 'Đại Dương', icon: '🌊', tile: TILES.DEEP_WATER, desc: 'Vực nước sâu không thể đi bộ' },
    { id: 'soil', category: TOOL_CATEGORIES.TERRAIN, name: 'Đất Mẹ', icon: '🟤', tile: TILES.SOIL, desc: 'Đất nền để cây cối phát triển' },
    { id: 'grass', category: TOOL_CATEGORIES.TERRAIN, name: 'Đồng Cỏ', icon: '🌱', tile: TILES.GRASS, desc: 'Cỏ xanh tươi tốt cho muôn loài' },
    { id: 'sand', category: TOOL_CATEGORIES.TERRAIN, name: 'Bãi Cát', icon: '🏖️', tile: TILES.SAND, desc: 'Bờ biển hoặc hoang mạc khô cằn' },
    { id: 'mountain', category: TOOL_CATEGORIES.TERRAIN, name: 'Núi Đá', icon: '⛰️', tile: TILES.MOUNTAIN, desc: 'Núi cao hiểm trở, chứa quặng' },
    { id: 'ice', category: TOOL_CATEGORIES.TERRAIN, name: 'Băng Tuyết', icon: '❄️', tile: TILES.ICE, desc: 'Đóng băng vùng đất mát lạnh' },
    { id: 'lava', category: TOOL_CATEGORIES.TERRAIN, name: 'Dung Nham', icon: '🌋', tile: TILES.LAVA, desc: 'Chất lỏng rực lửa thiêu đốt tất cả' },

    // Nature
    { id: 'forest', category: TOOL_CATEGORIES.NATURE, name: 'Trồng Rừng', icon: '🌲', tile: TILES.FOREST, desc: 'Tạo cây xanh lấy gỗ' },
    { id: 'spawn_sheep', category: TOOL_CATEGORIES.NATURE, name: 'Thả Cừu', icon: '🐑', entity: ENTITY_TYPES.SHEEP, desc: 'Loài ăn cỏ hiền lành' },
    { id: 'spawn_wolf', category: TOOL_CATEGORIES.NATURE, name: 'Thả Sói Hoang', icon: '🐺', entity: ENTITY_TYPES.WOLF, desc: 'Thú săn mồi nguy hiểm' },

    // Civilization
    { id: 'spawn_human', category: TOOL_CATEGORIES.CIVILIZATION, name: 'Tạo Con Người', icon: '🧑', entity: ENTITY_TYPES.HUMAN, desc: 'Biết đốn củi, khai đá, xây làng & lập quốc' },
    { id: 'spawn_elf', category: TOOL_CATEGORIES.CIVILIZATION, name: 'Tộc Tiên Elf', icon: '🧝', entity: ENTITY_TYPES.ELF, desc: 'Yêu thiên nhiên, sống thọ và bắn cung giỏi' },
    { id: 'spawn_orc', category: TOOL_CATEGORIES.CIVILIZATION, name: 'Tộc Orc Chiến Binh', icon: '👺', entity: ENTITY_TYPES.ORC, desc: 'Hiếu chiến, sức khỏe dồi dào và thích xâm chiếm' },

    // God Powers
    { id: 'blessing', category: TOOL_CATEGORIES.POWERS, name: 'Ban Phước Lành', icon: '✨', power: 'blessing', desc: 'Hồi phục HP, buff sức mạnh cho sinh vật' },
    { id: 'holy_rain', category: TOOL_CATEGORIES.POWERS, name: 'Mưa Phước Lành', icon: '🌧️', power: 'rain', desc: 'Dập tắt lửa, làm đất tươi tốt trở lại' },
    { id: 'lightning', category: TOOL_CATEGORIES.POWERS, name: 'Sấm Sét', icon: '⚡', power: 'lightning', desc: 'Giáng sét trừng phạt, phát nổ và tạo lửa' },
    { id: 'speed_growth', category: TOOL_CATEGORIES.POWERS, name: 'Bón Phân Thần Tốc', icon: '🌿', power: 'grow', desc: 'Cây cối và làng mạc phát triển cấp số nhân' },

    // Disasters
    { id: 'meteor', category: TOOL_CATEGORIES.DISASTERS, name: 'Thiên Thạch', icon: '☄️', power: 'meteor', desc: 'Thiên thạch giáng thế tạo hố dung nham' },
    { id: 'nuke', category: TOOL_CATEGORIES.DISASTERS, name: 'Bom Hạt Nhân', icon: '💣', power: 'nuke', desc: 'Hủy diệt diện rộng, san phẳng vạn vật' },
    { id: 'fire', category: TOOL_CATEGORIES.DISASTERS, name: 'Ngọn Lửa', icon: '🔥', tile: TILES.FIRE, desc: 'Đốt cháy cây cối và công trình' },
    { id: 'zombie_virus', category: TOOL_CATEGORIES.DISASTERS, name: 'Dịch Hạch Zombie', icon: '🧟', power: 'zombie_virus', desc: 'Biến dân cư thành thây ma đói khát' },
    { id: 'dragon', category: TOOL_CATEGORIES.DISASTERS, name: 'Thả Rồng Lửa', icon: '🐉', entity: ENTITY_TYPES.DRAGON, desc: 'Quái thú khổng lồ phun lửa phá hủy thế giới' },
    { id: 'acid', category: TOOL_CATEGORIES.DISASTERS, name: 'Axit Ăn Mòn', icon: '🧪', tile: TILES.ACID, desc: 'Ăn mòn địa hình và sinh vật' },

    // Inspect / Utility
    { id: 'inspect', category: TOOL_CATEGORIES.INSPECT, name: 'Kính Soi Thần', icon: '🔍', action: 'inspect', desc: 'Xem thông tin dân cư, vương quốc và đất đai' },
    { id: 'eraser', category: TOOL_CATEGORIES.INSPECT, name: 'Tẩy Xóa', icon: '🧹', action: 'eraser', desc: 'Xóa sinh vật và công trình' }
];
