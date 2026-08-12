/**
 * Pixel God Sandbox - Mobile Multi-Touch & Mouse Gestures
 */

export class TouchController {
    constructor(canvas, renderer, onActionCallback, onInspectCallback) {
        this.canvas = canvas;
        this.renderer = renderer;
        this.onAction = onActionCallback;
        this.onInspect = onInspectCallback;

        this.brushSize = 2;
        this.activeTool = null;

        // Pointer states
        this.isInteracting = false;
        this.isPanning = false;
        this.lastTouchDist = 0;
        this.lastPanX = 0;
        this.lastPanY = 0;

        this.setupEvents();
    }

    setBrushSize(size) {
        this.brushSize = size;
    }

    setActiveTool(tool) {
        this.activeTool = tool;
    }

    setupEvents() {
        // --- MOUSE EVENTS ---
        this.canvas.addEventListener('mousedown', (e) => {
            if (e.button === 1 || e.button === 2) {
                // Middle or Right Click for Panning
                this.isPanning = true;
                this.lastPanX = e.clientX;
                this.lastPanY = e.clientY;
                e.preventDefault();
            } else if (e.button === 0) {
                // Left Click for Drawing / Casting
                this.isInteracting = true;
                this.handlePrimaryAction(e.clientX, e.clientY);
            }
        });

        window.addEventListener('mousemove', (e) => {
            if (this.isPanning) {
                const dx = (e.clientX - this.lastPanX) / this.renderer.zoom;
                const dy = (e.clientY - this.lastPanY) / this.renderer.zoom;
                this.renderer.targetCameraX -= dx;
                this.renderer.targetCameraY -= dy;
                this.lastPanX = e.clientX;
                this.lastPanY = e.clientY;
            } else if (this.isInteracting) {
                this.handlePrimaryAction(e.clientX, e.clientY);
            }
        });

        window.addEventListener('mouseup', () => {
            this.isInteracting = false;
            this.isPanning = false;
        });

        this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());

        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const zoomDelta = e.deltaY < 0 ? 1.15 : 0.87;
            this.renderer.targetZoom = Math.max(1.0, Math.min(10.0, this.renderer.targetZoom * zoomDelta));
        }, { passive: false });

        // --- MOBILE TOUCH EVENTS (Multi-Touch & Pinch) ---
        this.canvas.addEventListener('touchstart', (e) => {
            if (e.touches.length === 1) {
                // 1 Finger = Paint or Inspect
                this.isInteracting = true;
                const t = e.touches[0];
                this.handlePrimaryAction(t.clientX, t.clientY);
            } else if (e.touches.length === 2) {
                // 2 Fingers = Pinch Zoom & Pan
                this.isInteracting = false;
                this.isPanning = true;
                const t1 = e.touches[0];
                const t2 = e.touches[1];
                this.lastTouchDist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
                this.lastPanX = (t1.clientX + t2.clientX) / 2;
                this.lastPanY = (t1.clientY + t2.clientY) / 2;
            }
        }, { passive: false });

        this.canvas.addEventListener('touchmove', (e) => {
            e.preventDefault();
            if (e.touches.length === 1 && this.isInteracting) {
                const t = e.touches[0];
                this.handlePrimaryAction(t.clientX, t.clientY);
            } else if (e.touches.length === 2 && this.isPanning) {
                const t1 = e.touches[0];
                const t2 = e.touches[1];
                
                // Pinch to Zoom
                const dist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
                if (this.lastTouchDist > 0) {
                    const factor = dist / this.lastTouchDist;
                    this.renderer.targetZoom = Math.max(1.0, Math.min(10.0, this.renderer.targetZoom * factor));
                }
                this.lastTouchDist = dist;

                // Two Finger Pan
                const midX = (t1.clientX + t2.clientX) / 2;
                const midY = (t1.clientY + t2.clientY) / 2;
                const dx = (midX - this.lastPanX) / this.renderer.zoom;
                const dy = (midY - this.lastPanY) / this.renderer.zoom;
                this.renderer.targetCameraX -= dx;
                this.renderer.targetCameraY -= dy;
                this.lastPanX = midX;
                this.lastPanY = midY;
            }
        }, { passive: false });

        window.addEventListener('touchend', (e) => {
            if (e.touches.length === 0) {
                this.isInteracting = false;
                this.isPanning = false;
                this.lastTouchDist = 0;
            } else if (e.touches.length === 1) {
                this.isPanning = false;
                this.lastTouchDist = 0;
            }
        });
    }

    handlePrimaryAction(screenX, screenY) {
        if (!this.activeTool) return;
        const worldPos = this.renderer.screenToWorld(screenX, screenY);
        
        if (this.activeTool.action === 'inspect') {
            if (this.onInspect) this.onInspect(worldPos.x, worldPos.y);
        } else {
            if (this.onAction) this.onAction(this.activeTool, worldPos.x, worldPos.y, this.brushSize);
        }
    }
}
