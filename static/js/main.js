/**
 * FaceAttend — Main JavaScript
 * Handles recognition toggle and shared utilities.
 */

async function toggleRecognition() {
    try {
        const res = await fetch('/api/recognition/toggle', { method: 'POST' });
        const data = await res.json();
        const btn = document.getElementById('toggleBtn');

        if (data.active) {
            btn.className = 'btn btn-danger';
            btn.innerHTML = '<span class="status-dot active"></span> Pause Recognition';
        } else {
            btn.className = 'btn btn-success';
            btn.innerHTML = '<span class="status-dot paused"></span> Resume Recognition';
        }
    } catch (e) {
        console.error('Failed to toggle recognition:', e);
    }
}
