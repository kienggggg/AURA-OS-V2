/**
 * Pixel God Sandbox - Web Audio API Sound Synthesizer
 * Generates retro 8-bit sound effects procedurally.
 */

class SoundEngine {
    constructor() {
        this.ctx = null;
        this.enabled = true;
        this.muted = false;
    }

    init() {
        if (!this.ctx) {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {
                this.ctx = new AudioContext();
            }
        }
        if (this.ctx && this.ctx.state === 'suspended') {
            this.ctx.resume();
        }
    }

    toggleMute() {
        this.muted = !this.muted;
        return this.muted;
    }

    playTone(freq, type = 'sine', duration = 0.1, gainVal = 0.1) {
        if (this.muted || !this.enabled) return;
        this.init();
        if (!this.ctx) return;

        try {
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();

            osc.type = type;
            osc.frequency.setValueAtTime(freq, this.ctx.currentTime);

            gain.gain.setValueAtTime(gainVal, this.ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + duration);

            osc.connect(gain);
            gain.connect(this.ctx.destination);

            osc.start();
            osc.stop(this.ctx.currentTime + duration);
        } catch (e) {
            // Audio context error handling
        }
    }

    playNoise(duration = 0.2, gainVal = 0.2, filterFreq = 1000) {
        if (this.muted || !this.enabled) return;
        this.init();
        if (!this.ctx) return;

        try {
            const bufferSize = this.ctx.sampleRate * duration;
            const buffer = this.ctx.createBuffer(1, bufferSize, this.ctx.sampleRate);
            const data = buffer.getChannelData(0);
            for (let i = 0; i < bufferSize; i++) {
                data[i] = Math.random() * 2 - 1;
            }

            const noise = this.ctx.createBufferSource();
            noise.buffer = buffer;

            const filter = this.ctx.createBiquadFilter();
            filter.type = 'lowpass';
            filter.frequency.setValueAtTime(filterFreq, this.ctx.currentTime);
            filter.frequency.exponentialRampToValueAtTime(80, this.ctx.currentTime + duration);

            const gain = this.ctx.createGain();
            gain.gain.setValueAtTime(gainVal, this.ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + duration);

            noise.connect(filter);
            filter.connect(gain);
            gain.connect(this.ctx.destination);

            noise.start();
        } catch (e) {
            // Audio context error handling
        }
    }

    // Specific God Sounds
    playThunder() {
        this.playNoise(0.6, 0.4, 1800);
        setTimeout(() => this.playTone(80, 'sawtooth', 0.4, 0.2), 50);
    }

    playExplosion() {
        this.playNoise(0.8, 0.5, 900);
        this.playTone(60, 'square', 0.5, 0.3);
    }

    playSplash() {
        this.playTone(440, 'triangle', 0.08, 0.15);
        setTimeout(() => this.playTone(680, 'sine', 0.1, 0.1), 40);
    }

    playBlessing() {
        [523.25, 659.25, 783.99, 1046.50].forEach((freq, idx) => {
            setTimeout(() => this.playTone(freq, 'sine', 0.3, 0.08), idx * 70);
        });
    }

    playBuild() {
        this.playTone(320, 'square', 0.04, 0.08);
        setTimeout(() => this.playTone(480, 'square', 0.05, 0.08), 50);
    }

    playChop() {
        this.playTone(180, 'triangle', 0.04, 0.1);
    }

    playSpawn() {
        this.playTone(350, 'sine', 0.08, 0.1);
        setTimeout(() => this.playTone(520, 'sine', 0.1, 0.1), 60);
    }

    playDisaster() {
        this.playTone(110, 'sawtooth', 0.8, 0.3);
        this.playNoise(1.0, 0.3, 500);
    }
}

export const sound = new SoundEngine();
