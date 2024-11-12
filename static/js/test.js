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

    function checkCurrentQuestionAnswered() {
        const currentQuestion = questions[currentQuestionIndex];
        const questionId = currentQuestion.querySelector('input[type="radio"]').name.split('_')[1];
        return !!answers[questionId];
    }

    // Event listeners for navigation buttons
    prevBtn.addEventListener('click', () => {
        if (currentQuestionIndex > 0) {
            showQuestion(currentQuestionIndex - 1);
        }
    });

    nextBtn.addEventListener('click', () => {
        if (!checkCurrentQuestionAnswered()) {
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
        }
    });

    // Handle form submission
    testForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        // Check if all questions are answered
        const allQuestionsAnswered = Array.from(questions).every(question => {
            const questionId = question.querySelector('input[type="radio"]').name.split('_')[1];
            return !!answers[questionId];
        });

        if (!allQuestionsAnswered) {
            alert('Please answer all questions before submitting.');
            return;
        }

        try {
            const response = await fetch(window.location.href + '/submit', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(answers)
            });
            
            const data = await response.json();
            
            if (response.ok && data.redirect) {
                window.location.href = data.redirect;
            } else if (data.error) {
                alert(data.error);
            }
        } catch (error) {
            console.error('Error submitting test:', error);
            alert('An error occurred while submitting the test. Please try again.');
        }
    });

    // Initialize the first question
    showQuestion(0);
});
