document.addEventListener('DOMContentLoaded', function() {
    const ctx = document.getElementById('progressChart').getContext('2d');
    
    // Get test data from the page
    const tests = Array.from(document.querySelectorAll('.list-group-item')).map(item => ({
        category: item.querySelector('h6').textContent,
        score: parseFloat(item.querySelector('small').textContent)
    }));

    // Group tests by category and calculate averages
    const categoryData = {};
    tests.forEach(test => {
        if (!categoryData[test.category]) {
            categoryData[test.category] = [];
        }
        categoryData[test.category].push(test.score);
    });

    const labels = Object.keys(categoryData);
    const data = labels.map(category => {
        const scores = categoryData[category];
        return scores.reduce((a, b) => a + b) / scores.length;
    });

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Average Score',
                data: data,
                backgroundColor: '#800020',
                borderColor: '#800020',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });
});
