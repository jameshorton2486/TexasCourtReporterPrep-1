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

    timerElements.startButton.addEventListener('click', function() {
        if (!timerRunning) {
            timerRunning = true;
            startTime = new Date();
            timerId = setInterval(updateTimer, 1000);
            timerElements.startButton.textContent = 'Pause';
        } else {
            timerRunning = false;
            clearInterval(timerId);
            timerElements.startButton.textContent = 'Resume';
        }
    });

    timerElements.stopButton.addEventListener('click', function() {
        timerRunning = false;
        clearInterval(timerId);
        timerElements.timeCounter.textContent = '00:00:00';
        timerElements.startButton.textContent = 'Start';
        startTime = null;
    });

    console.log('Timer interface initialized successfully');
});
