    (() => {
        const tok = (name, fallback) => {
            try {
                const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
                return v || fallback;
            } catch (_e) { return fallback; }
        };
        const activityPayload = JSON.parse(document.getElementById('activityData').textContent);
        const activityCtx = document.getElementById('activityChartCanvas');
        if (activityCtx && activityPayload) {
            new Chart(activityCtx, {
                type: 'line',
                data: {
                    labels: activityPayload.labels,
                    datasets: [{
                        label: 'Audit Events',
                        data: activityPayload.data,
                        fill: false,
                        borderColor: tok('--chart-color-1', '#1f78d1'),
                        backgroundColor: 'rgba(31, 120, 209, 0.15)',
                        tension: 0.25,
                        pointRadius: 2,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { beginAtZero: true }
                    },
                    plugins: { legend: { display: false } }
                }
            });
        }

        const heatmapCtx = document.getElementById('heatmapChartCanvas');
        if (heatmapCtx) {
            const heatmapPayload = JSON.parse(document.getElementById('heatmapData').textContent);
            const hours = heatmapPayload.hours || [];
            const counts = heatmapPayload.data || [];
            new Chart(heatmapCtx, {
                type: 'bar',
                data: {
                    labels: hours.map(h => `${h}:00`),
                    datasets: [{
                        label: 'Logins',
                        data: counts,
                        backgroundColor: counts.map(c => `rgba(46, 204, 113, ${Math.min(1, (c || 0) / 10 + 0.1)})`),
                        borderWidth: 0,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { beginAtZero: true }
                    },
                    plugins: { legend: { display: false } }
                }
            });
        }
    })();
