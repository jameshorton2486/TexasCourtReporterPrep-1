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

    timerElements.startButton.addEventListener('click', async function() {
        const categorySelect = document.querySelector('select[name="category_id"]');
        if (!categorySelect) {
            console.warn('Category select element not found');
            return;
        }
        
        const categoryId = categorySelect.value;
        if (!categoryId) {
            console.warn('No category selected');
            return;
        }
        
        try {
            const response = await fetch('/study/timer/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ category_id: categoryId })
            });
            
            const data = await response.json();
            if (data.timer_id) {
                currentTimerId = data.timer_id;
                startTime = new Date();
                timerRunning = true;
                timerId = setInterval(updateTimer, 1000);
                
                timerElements.startButton.style.display = 'none';
                timerElements.stopButton.style.display = 'inline-block';
            }
        } catch (error) {
            console.error('Failed to start timer:', error);
            alert('Failed to start timer. Please try again.');
        }
    });

    timerElements.stopButton.addEventListener('click', async function() {
        if (!currentTimerId) return;
        
        try {
            const response = await fetch(`/study/timer/${currentTimerId}/stop`, {
                method: 'POST'
            });
            
            const data = await response.json();
            if (data.duration) {
                clearInterval(timerId);
                timerRunning = false;
                timerElements.timeCounter.textContent = formatTime(data.duration);
                
                timerElements.stopButton.style.display = 'none';
                timerElements.startButton.style.display = 'inline-block';
            }
        } catch (error) {
            console.error('Failed to stop timer:', error);
            alert('Failed to stop timer. Please try again.');
        }
    });

    console.log('Timer interface initialized successfully');
});
