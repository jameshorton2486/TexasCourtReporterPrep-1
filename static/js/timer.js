document.addEventListener('DOMContentLoaded', function() {
    const timerElements = {
        startButton: document.getElementById('start-timer'),
        stopButton: document.getElementById('stop-timer'),
        timeCounter: document.getElementById('time-counter')
    };

    // Only initialize if we're on the right page
    if (!timerElements.startButton || !timerElements.stopButton || !timerElements.timeCounter) {
        console.log('Timer elements not found - skipping initialization');
        return;
    }

    let timerId = null;
    let timerRunning = false;
    let startTime = null;
    let currentTimerId = null;

    function formatTime(seconds) {
        const hrs = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        return `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }

    function updateTimer() {
        if (!startTime || !timerRunning) return;
        const now = new Date();
        const diff = Math.floor((now - startTime) / 1000);
        timerElements.timeCounter.textContent = formatTime(diff);
    }

    console.log('Timer interface initialized successfully');
});