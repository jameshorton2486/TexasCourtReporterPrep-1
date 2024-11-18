document.addEventListener('DOMContentLoaded', function() {
    const testForm = document.getElementById('testForm');
    const questions = document.querySelectorAll('.question-container');
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const submitBtn = document.getElementById('submitBtn');
    const progressBar = document.getElementById('progressBar');
    let currentQuestionIndex = 0;
    const totalQuestions = questions.length;
    const answers = {};
    const isPracticeMode = document.querySelector('.badge.bg-success') !== null;
    let timer = null;

    console.log('Test interface initializing...');
    console.log(`Total questions: ${totalQuestions}`);
    console.log(`Practice mode: ${isPracticeMode}`);

    // Initialize timer if study session exists
    const sessionContainer = document.getElementById('study-session');
    if (sessionContainer && sessionContainer.dataset.sessionId) {
        timer = new StudyTimer(sessionContainer.dataset.sessionId);
        timer.start().catch(error => {
            console.error('Failed to start timer:', error);
        });
    }

    function updateNavigationButtons() {
        prevBtn.style.display = currentQuestionIndex > 0 ? 'inline-block' : 'none';
        nextBtn.style.display = currentQuestionIndex < totalQuestions - 1 ? 'inline-block' : 'none';
        submitBtn.style.display = currentQuestionIndex === totalQuestions - 1 ? 'inline-block' : 'none';
    }

    function updateProgressBar() {
        const progress = ((currentQuestionIndex + 1) / totalQuestions) * 100;
        progressBar.style.width = `${progress}%`;
        progressBar.textContent = `Question ${currentQuestionIndex + 1} of ${totalQuestions}`;
    }

    function showQuestion(index) {
        questions.forEach((q, i) => {
            q.style.display = i === index ? 'block' : 'none';
        });
        currentQuestionIndex = index;
        updateNavigationButtons();
        updateProgressBar();
    }

    function validateCurrentQuestion() {
        const currentQuestion = questions[currentQuestionIndex];
        const radios = currentQuestion.querySelectorAll('input[type="radio"]');
        return Array.from(radios).some(radio => radio.checked);
    }

    function checkAnswer(questionId, selectedAnswer, correctAnswer) {
        if (!isPracticeMode) return;

        const feedbackDiv = document.getElementById(`feedback_${questionId}`);
        if (!feedbackDiv) return;

        const alertDiv = feedbackDiv.querySelector('.alert');
        if (!alertDiv) return;
        
        if (selectedAnswer === correctAnswer) {
            alertDiv.className = 'alert alert-success';
            alertDiv.textContent = 'Correct! Well done!';
        } else {
            alertDiv.className = 'alert alert-danger';
            alertDiv.innerHTML = `Incorrect. The correct answer is: ${correctAnswer}`;
        }
        
        feedbackDiv.style.display = 'block';
    }

    // Event listeners for navigation
    prevBtn.addEventListener('click', () => {
        if (currentQuestionIndex > 0) {
            showQuestion(currentQuestionIndex - 1);
        }
    });

    nextBtn.addEventListener('click', () => {
        if (!validateCurrentQuestion()) {
            alert('Please answer the current question before proceeding.');
            return;
        }

        if (currentQuestionIndex < totalQuestions - 1) {
            showQuestion(currentQuestionIndex + 1);
        }
    });

    // Handle radio button selections
    testForm.addEventListener('change', function(e) {
        if (e.target.type === 'radio') {
            const questionId = e.target.name.split('_')[1];
            answers[questionId] = e.target.value;

            if (isPracticeMode) {
                const currentQuestion = e.target.closest('.question-container');
                const allAnswers = currentQuestion.querySelectorAll('input[type="radio"]');
                const correctAnswer = Array.from(allAnswers)
                    .find(radio => radio.dataset.correct === 'true')?.value;
                
                if (correctAnswer) {
                    checkAnswer(questionId, e.target.value, correctAnswer);
                }
            }
        }
    });

    // Handle form submission
    testForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        if (!Array.from(questions).every(() => validateCurrentQuestion())) {
            alert('Please answer all questions before submitting.');
            return;
        }

        try {
            if (timer) {
                await timer.stop();
            }

            const response = await fetch(`/test/${window.location.pathname.split('/').pop()}/submit`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(answers)
            });
            
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }

            const data = await response.json();
            
            if (data.redirect) {
                window.location.href = data.redirect;
            } else if (isPracticeMode && data.score !== undefined) {
                const scoreAlert = document.createElement('div');
                scoreAlert.className = 'alert alert-info mt-3';
                scoreAlert.innerHTML = `Practice session completed! Your score: ${data.score}%`;
                testForm.insertAdjacentElement('beforebegin', scoreAlert);
            }
        } catch (error) {
            console.error('Error submitting test:', error);
            alert('An error occurred while submitting the test. Please try again.');
        }
    });

    // Initialize the first question
    showQuestion(0);
    console.log('Test interface initialized successfully');
});
