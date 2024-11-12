document.addEventListener('DOMContentLoaded', function() {
    const testForm = document.getElementById('testForm');
    
    testForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const answers = {};
        const formData = new FormData(testForm);
        
        for (let [name, value] of formData.entries()) {
            const questionId = name.split('_')[1];
            answers[questionId] = value;
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
            
            if (data.redirect) {
                window.location.href = data.redirect;
            }
        } catch (error) {
            console.error('Error submitting test:', error);
            alert('An error occurred while submitting the test. Please try again.');
        }
    });
});
