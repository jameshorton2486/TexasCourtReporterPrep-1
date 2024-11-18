class StudyTimer {
    constructor(sessionId) {
        this.sessionId = sessionId;
        this.startTime = null;
        this.timerId = null;
        this.isActive = false;
        this.timeDisplay = document.getElementById('time-counter');
        this.progressBar = document.getElementById('timer-progress');
        this.displayInterval = null;
        this.setupEventListeners();
    }

    setupEventListeners() {
        const startBtn = document.getElementById('start-timer');
        const stopBtn = document.getElementById('stop-timer');
        const pauseBtn = document.getElementById('pause-timer');

        if (startBtn) startBtn.addEventListener('click', () => this.start());
        if (stopBtn) stopBtn.addEventListener('click', () => this.stop());
        if (pauseBtn) pauseBtn.addEventListener('click', () => this.pause());
    }

    async start() {
        if (this.isActive) return;

        try {
            const response = await fetch('/study/timer/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ session_id: this.sessionId })
            });

            if (!response.ok) {
                throw new Error(await response.text() || 'Failed to start timer');
            }
            
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Failed to start timer');
            }

            this.timerId = data.timer_id;
            this.startTime = new Date();
            this.isActive = true;
            
            // Start updating display
            this.updateDisplay();
            if (this.displayInterval) clearInterval(this.displayInterval);
            this.displayInterval = setInterval(() => this.updateDisplay(), 1000);
            
            // Update button visibility
            this.updateButtonVisibility(true);
            
        } catch (error) {
            console.error('Error starting timer:', error);
            alert(error.message || 'Failed to start timer. Please try again.');
        }
    }

    async stop() {
        if (!this.isActive || !this.timerId) return;

        try {
            const response = await fetch('/study/timer/stop', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ timer_id: this.timerId })
            });

            if (!response.ok) {
                throw new Error(await response.text() || 'Failed to stop timer');
            }

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Failed to stop timer');
            }

            this.cleanup();
            this.updateButtonVisibility(false);
            
        } catch (error) {
            console.error('Error stopping timer:', error);
            alert(error.message || 'Failed to stop timer. Please try again.');
        }
    }

    pause() {
        if (!this.isActive) return;
        
        if (this.displayInterval) {
            clearInterval(this.displayInterval);
            this.displayInterval = null;
        }
        this.isActive = false;
        this.updateButtonVisibility(false);
    }

    cleanup() {
        if (this.displayInterval) {
            clearInterval(this.displayInterval);
            this.displayInterval = null;
        }
        this.isActive = false;
        this.startTime = null;
        this.timerId = null;
    }

    updateButtonVisibility(timerActive) {
        const startBtn = document.getElementById('start-timer');
        const stopBtn = document.getElementById('stop-timer');
        const pauseBtn = document.getElementById('pause-timer');

        if (startBtn) startBtn.style.display = timerActive ? 'none' : 'inline-block';
        if (stopBtn) stopBtn.style.display = timerActive ? 'inline-block' : 'none';
        if (pauseBtn) pauseBtn.style.display = timerActive ? 'inline-block' : 'none';
    }

    updateDisplay() {
        if (!this.startTime || !this.isActive || !this.timeDisplay) return;
        
        const now = new Date();
        const elapsedSeconds = Math.floor((now - this.startTime) / 1000);
        
        // Format time
        const hours = Math.floor(elapsedSeconds / 3600);
        const minutes = Math.floor((elapsedSeconds % 3600) / 60);
        const seconds = elapsedSeconds % 60;
        
        this.timeDisplay.textContent = 
            `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        
        // Update progress bar if available
        if (this.progressBar) {
            const duration = parseInt(this.progressBar.dataset.duration) || 0;
            if (duration > 0) {
                const progress = Math.min((elapsedSeconds / (duration * 60)) * 100, 100);
                this.progressBar.style.width = `${progress}%`;
                this.progressBar.setAttribute('aria-valuenow', progress);
            }
        }
    }
}

// Initialize timer when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    const sessionContainer = document.getElementById('study-session');
    if (sessionContainer && sessionContainer.dataset.sessionId) {
        console.log('Initializing study timer...');
        window.studyTimer = new StudyTimer(sessionContainer.dataset.sessionId);
    }
});
