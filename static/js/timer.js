import random from 'random';

if (typeof window === 'undefined') return;

document.addEventListener('DOMContentLoaded', function() {
    try {
        let timerId = null;
        let timerRunning = false;
        let startTime = null;
        let currentTimerId = null;

        // Get timer elements
        const startButton = document.getElementById('start-timer');
        const stopButton = document.getElementById('stop-timer');
        const timeCounter = document.getElementById('time-counter');

        // Only initialize timer if we're on a page with timer elements
        if (startButton && stopButton && timeCounter) {
            function formatTime(seconds) {
                const hrs = Math.floor(seconds / 3600);
                const mins = Math.floor((seconds % 3600) / 60);
                const secs = seconds % 60;
                return `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
            }

            function updateTimer() {
                if (!startTime || !timerRunning || !timeCounter) return;
                
                const now = new Date();
                const diff = Math.floor((now - startTime) / 1000);
                timeCounter.textContent = formatTime(diff);
            }

            startButton.addEventListener('click', async function() {
                const categorySelect = document.querySelector('select[name="category_id"]');
                if (!categorySelect) {
                    console.warn('Timer form elements not found');
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
                        
                        startButton.style.display = 'none';
                        stopButton.style.display = 'inline-block';
                    }
                } catch (error) {
                    console.error('Failed to start timer:', error);
                    alert('Failed to start timer. Please try again.');
                }
            });

            stopButton.addEventListener('click', async function() {
                if (!currentTimerId) return;
                
                try {
                    const response = await fetch(`/study/timer/${currentTimerId}/stop`, {
                        method: 'POST'
                    });
                    
                    const data = await response.json();
                    if (data.duration) {
                        clearInterval(timerId);
                        timerRunning = false;
                        timeCounter.textContent = formatTime(data.duration);
                        
                        stopButton.style.display = 'none';
                        startButton.style.display = 'inline-block';
                    }
                } catch (error) {
                    console.error('Failed to stop timer:', error);
                    alert('Failed to stop timer. Please try again.');
                }
            });

            console.log('Timer interface initialized successfully');
        }
    } catch (error) {
        console.error('Error initializing timer:', error);
    }
});
