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
    document.getElementById('time-counter').textContent = formatTime(diff);
}

document.getElementById('start-timer').addEventListener('click', async function() {
    const categoryId = document.querySelector('select[name="category_id"]').value;
    
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
            
            this.style.display = 'none';
            document.getElementById('stop-timer').style.display = 'inline-block';
        }
    } catch (error) {
        console.error('Failed to start timer:', error);
        alert('Failed to start timer. Please try again.');
    }
});

document.getElementById('stop-timer').addEventListener('click', async function() {
    if (!currentTimerId) return;
    
    try {
        const response = await fetch(`/study/timer/${currentTimerId}/stop`, {
            method: 'POST'
        });
        
        const data = await response.json();
        if (data.duration) {
            clearInterval(timerId);
            timerRunning = false;
            document.getElementById('time-counter').textContent = formatTime(data.duration);
            
            this.style.display = 'none';
            document.getElementById('start-timer').style.display = 'inline-block';
        }
    } catch (error) {
        console.error('Failed to stop timer:', error);
        alert('Failed to stop timer. Please try again.');
    }
});
