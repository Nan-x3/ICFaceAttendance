const OLED_WIDTH = 128;
const OLED_HEIGHT = 64;
const PIXELS = OLED_WIDTH * OLED_HEIGHT;

const canvas = document.getElementById('oledCanvas');
const context = canvas.getContext('2d');
const nameInput = document.getElementById('animationName');
const stateInput = document.getElementById('animationState');
const fpsInput = document.getElementById('fpsInput');
const timeline = document.getElementById('timeline');
const frameLabel = document.getElementById('frameLabel');
const savedAnimations = document.getElementById('savedAnimations');
const toast = document.getElementById('studioToast');

let frames = [new Array(PIXELS).fill(0)];
let currentFrame = 0;
let selectedColor = 1;
let selectedTool = 'pencil';
let drawing = false;
let playing = false;
let playbackTimer;

function blankFrame() {
    return new Array(PIXELS).fill(0);
}

function showToast(message, error = false) {
    toast.textContent = message;
    toast.className = `studio-toast visible${error ? ' error' : ''}`;
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => { toast.className = 'studio-toast'; }, 2600);
}

function drawFrame() {
    const frame = frames[currentFrame];
    const image = context.createImageData(OLED_WIDTH, OLED_HEIGHT);
    const previous = document.getElementById('onionSkin').checked && currentFrame > 0 ? frames[currentFrame - 1] : null;
    for (let index = 0; index < PIXELS; index++) {
        const value = frame[index];
        const prior = previous && previous[index] ? 1 : 0;
        const color = value === 2 ? [235, 70, 87] : value ? [232, 244, 239] : prior ? [50, 100, 83] : [8, 12, 16];
        image.data[index * 4] = color[0];
        image.data[index * 4 + 1] = color[1];
        image.data[index * 4 + 2] = color[2];
        image.data[index * 4 + 3] = 255;
    }
    context.putImageData(image, 0, 0);
    frameLabel.textContent = `Frame ${currentFrame + 1} / ${frames.length}`;
    renderTimeline();
}

function renderTimeline() {
    timeline.innerHTML = '';
    frames.forEach((frame, index) => {
        const button = document.createElement('button');
        button.className = `timeline-frame${index === currentFrame ? ' active' : ''}`;
        button.title = `Frame ${index + 1}`;
        const preview = document.createElement('canvas');
        preview.width = OLED_WIDTH;
        preview.height = OLED_HEIGHT;
        preview.className = 'frame-preview';
        const previewContext = preview.getContext('2d');
        const image = previewContext.createImageData(OLED_WIDTH, OLED_HEIGHT);
        frame.forEach((value, pixel) => {
            const color = value === 2 ? [235, 70, 87] : value ? [232, 244, 239] : [8, 12, 16];
            image.data[pixel * 4] = color[0];
            image.data[pixel * 4 + 1] = color[1];
            image.data[pixel * 4 + 2] = color[2];
            image.data[pixel * 4 + 3] = 255;
        });
        previewContext.putImageData(image, 0, 0);
        button.append(preview);
        button.insertAdjacentHTML('beforeend', `<span>${index + 1}</span>`);
        button.addEventListener('click', () => { currentFrame = index; drawFrame(); });
        timeline.append(button);
    });
}

function canvasPixel(event) {
    const bounds = canvas.getBoundingClientRect();
    return {
        x: Math.max(0, Math.min(OLED_WIDTH - 1, Math.floor((event.clientX - bounds.left) * OLED_WIDTH / bounds.width))),
        y: Math.max(0, Math.min(OLED_HEIGHT - 1, Math.floor((event.clientY - bounds.top) * OLED_HEIGHT / bounds.height)))
    };
}

function paint(event) {
    const { x, y } = canvasPixel(event);
    const index = y * OLED_WIDTH + x;
    const frame = frames[currentFrame];
    if (selectedTool === 'fill') {
        frame.fill(selectedColor);
    } else {
        frame[index] = selectedTool === 'eraser' ? 0 : selectedColor;
    }
    drawFrame();
}

function moveFrame(step) {
    currentFrame = (currentFrame + step + frames.length) % frames.length;
    drawFrame();
}

function addFrame(copyCurrent = true) {
    const source = copyCurrent ? frames[currentFrame] : blankFrame();
    frames.splice(currentFrame + 1, 0, [...source]);
    currentFrame += 1;
    drawFrame();
}

function resetEditor() {
    stopPlayback();
    frames = [blankFrame()];
    currentFrame = 0;
    nameInput.value = 'new_animation';
    stateInput.value = 'locked';
    fpsInput.value = 8;
    drawFrame();
}

function stopPlayback() {
    playing = false;
    window.clearInterval(playbackTimer);
    document.getElementById('playBtn').textContent = '▶ Play';
}

function togglePlayback() {
    if (playing) {
        stopPlayback();
        return;
    }
    playing = true;
    document.getElementById('playBtn').textContent = '■ Stop';
    playbackTimer = window.setInterval(() => moveFrame(1), 1000 / Number(fpsInput.value || 8));
}

async function saveAnimation() {
    const payload = {
        name: nameInput.value.trim(),
        state: stateInput.value,
        fps: Number(fpsInput.value),
        frames
    };
    try {
        const response = await fetch('/api/animations', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Could not save animation');
        showToast(`Saved ${result.name}.json`);
        loadSavedAnimations();
    } catch (error) {
        showToast(error.message, true);
    }
}

async function loadAnimation(name) {
    const response = await fetch(`/api/animations/${encodeURIComponent(name)}`);
    const animation = await response.json();
    if (!response.ok) { showToast(animation.error, true); return; }
    frames = animation.frames;
    currentFrame = 0;
    nameInput.value = animation.name;
    stateInput.value = animation.state;
    fpsInput.value = animation.fps;
    drawFrame();
}

async function loadSavedAnimations() {
    const response = await fetch('/api/animations');
    const animations = await response.json();
    document.getElementById('savedCount').textContent = animations.length;
    savedAnimations.innerHTML = '';
    animations.forEach(animation => {
        const button = document.createElement('button');
        button.className = 'saved-animation';
        button.innerHTML = `<strong>${animation.name}</strong><span>${animation.state} · ${animation.frames} frames</span>`;
        button.addEventListener('click', () => loadAnimation(animation.name));
        savedAnimations.append(button);
    });
}

canvas.addEventListener('pointerdown', event => { drawing = true; canvas.setPointerCapture(event.pointerId); paint(event); });
canvas.addEventListener('pointermove', event => { if (drawing) paint(event); });
canvas.addEventListener('pointerup', () => { drawing = false; });
canvas.addEventListener('contextmenu', event => { event.preventDefault(); selectedTool = 'eraser'; paint(event); });
document.getElementById('playBtn').addEventListener('click', togglePlayback);
document.getElementById('prevFrameBtn').addEventListener('click', () => moveFrame(-1));
document.getElementById('nextFrameBtn').addEventListener('click', () => moveFrame(1));
document.getElementById('duplicateFrameBtn').addEventListener('click', () => addFrame(true));
document.getElementById('deleteFrameBtn').addEventListener('click', () => {
    if (frames.length === 1) return;
    frames.splice(currentFrame, 1);
    currentFrame = Math.min(currentFrame, frames.length - 1);
    drawFrame();
});
document.getElementById('newAnimationBtn').addEventListener('click', resetEditor);
document.getElementById('saveAnimationBtn').addEventListener('click', saveAnimation);
document.getElementById('onionSkin').addEventListener('change', drawFrame);
document.querySelectorAll('.icon-tool').forEach(button => button.addEventListener('click', () => {
    selectedTool = button.dataset.tool;
    document.querySelectorAll('.icon-tool').forEach(item => item.classList.toggle('active', item === button));
}));
document.querySelectorAll('.swatch').forEach(button => button.addEventListener('click', () => {
    selectedColor = Number(button.dataset.color);
    selectedTool = 'pencil';
    document.querySelectorAll('.swatch').forEach(item => item.classList.toggle('active', item === button));
}));

loadSavedAnimations();
drawFrame();
