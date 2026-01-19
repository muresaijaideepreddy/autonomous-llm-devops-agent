/**
 * Autonomous Testing Dashboard - Frontend Logic
 * ==============================================
 * Fetches data from API and updates UI components
 */

// ─────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────
let coverageChart = null;
let resultsChart = null;
let refreshInterval = null;

// ─────────────────────────────────────────────
// INITIALIZATION
// ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    refreshData();

    // Auto-refresh every 5 seconds
    refreshInterval = setInterval(refreshData, 5000);
});

// ─────────────────────────────────────────────
// DATA FETCHING
// ─────────────────────────────────────────────
async function refreshData() {
    try {
        const [runsRes, metricsRes, latestRes] = await Promise.all([
            fetch('/api/runs'),
            fetch('/api/metrics'),
            fetch('/api/latest')
        ]);

        const runs = await runsRes.json();
        const metrics = await metricsRes.json();
        const latest = await latestRes.json();

        updateStats(runs.runs, metrics.metrics);
        updateCharts(metrics.metrics);
        updateLatestRun(latest);
        updateRunsTable(runs.runs);

        document.getElementById('connectionStatus').textContent = 'Connected';
    } catch (error) {
        console.error('Error fetching data:', error);
        document.getElementById('connectionStatus').textContent = 'Error';
    }
}

// ─────────────────────────────────────────────
// STATS UPDATE
// ─────────────────────────────────────────────
function updateStats(runs, metrics) {
    // Total runs
    document.getElementById('totalRuns').textContent = runs.length;

    // Latest coverage
    const latestCoverage = runs.length > 0 && runs[0].coverage != null
        ? `${runs[0].coverage.toFixed(1)}%`
        : '--';
    document.getElementById('latestCoverage').textContent = latestCoverage;

    // Pass rate
    const passedRuns = runs.filter(r => r.status === 'pass').length;
    const passRate = runs.length > 0
        ? `${((passedRuns / runs.length) * 100).toFixed(0)}%`
        : '--';
    document.getElementById('passRate').textContent = passRate;

    // Average execution time
    const timings = metrics
        .filter(m => m.execution_time_ms)
        .map(m => m.execution_time_ms);
    const avgTime = timings.length > 0
        ? `${Math.round(timings.reduce((a, b) => a + b, 0) / timings.length)}ms`
        : '--';
    document.getElementById('avgTime').textContent = avgTime;
}

// ─────────────────────────────────────────────
// CHARTS
// ─────────────────────────────────────────────
function initCharts() {
    // Coverage Trend Chart
    const coverageCtx = document.getElementById('coverageChart').getContext('2d');
    coverageChart = new Chart(coverageCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Coverage %',
                data: [],
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 3,
                pointBackgroundColor: '#6366f1'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: false,
                    min: 0,
                    max: 100,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    },
                    ticks: {
                        color: '#94a3b8',
                        callback: val => val + '%'
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: '#94a3b8',
                        maxRotation: 0
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

    // Results Donut Chart
    const resultsCtx = document.getElementById('resultsChart').getContext('2d');
    resultsChart = new Chart(resultsCtx, {
        type: 'doughnut',
        data: {
            labels: ['Passed', 'Failed', 'Error'],
            datasets: [{
                data: [0, 0, 0],
                backgroundColor: ['#10b981', '#ef4444', '#f59e0b'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#94a3b8',
                        padding: 16,
                        usePointStyle: true
                    }
                }
            }
        }
    });
}

function updateCharts(metrics) {
    // Update coverage chart with last 20 runs
    const coverageData = metrics
        .filter(m => m.coverage != null)
        .slice(-20);

    coverageChart.data.labels = coverageData.map((m, i) => `#${i + 1}`);
    coverageChart.data.datasets[0].data = coverageData.map(m => m.coverage);
    coverageChart.update('none');

    // Update results donut
    const passed = metrics.filter(m => m.status === 'pass').length;
    const failed = metrics.filter(m => m.status === 'fail').length;
    const error = metrics.filter(m => m.status === 'error' || m.status === 'no_tests').length;

    resultsChart.data.datasets[0].data = [passed, failed, error];
    resultsChart.update('none');
}

// ─────────────────────────────────────────────
// LATEST RUN
// ─────────────────────────────────────────────
function updateLatestRun(run) {
    if (run.error) {
        document.getElementById('latestRunId').textContent = 'No runs found';
        return;
    }

    const executor = run.executor_output || {};
    const planner = run.planner_output || {};
    const tester = run.tester_output || {};

    // Header
    document.getElementById('latestRunId').textContent = run.run_id || '--';

    const statusEl = document.getElementById('latestRunStatus');
    const status = executor.status || 'unknown';
    statusEl.textContent = status.toUpperCase();
    statusEl.className = `run-status ${status}`;

    // Info grid
    document.getElementById('latestStartTime').textContent = formatTime(run.start_time);
    document.getElementById('latestDuration').textContent = executor.execution_time_ms
        ? `${executor.execution_time_ms}ms`
        : '--';
    document.getElementById('latestRunCoverage').textContent = executor.coverage_percent != null
        ? `${executor.coverage_percent.toFixed(1)}%`
        : '--';
    document.getElementById('latestTests').textContent = executor.total_tests != null
        ? `${executor.passed_tests || 0}/${executor.total_tests} passed`
        : '--';

    // Agent steps
    updateAgentStep('stepPlanner', !!planner.modules_to_test, planner.reason || 'Analyzed');
    updateAgentStep('stepTester', !!tester.test_files_created,
        tester.num_tests_generated ? `${tester.num_tests_generated} tests` : 'Skipped');
    updateAgentStep('stepExecutor', !!executor.status, executor.summary_report || '--');
    updateAgentStep('stepHealer', !!run.executor_output?.healer_report,
        run.executor_output?.coverage_healer_ran ? 'Ran' : 'Idle');

    // Planner output
    document.getElementById('plannerOutput').innerHTML = planner.modules_to_test
        ? `<strong>Modules:</strong> ${planner.modules_to_test.join(', ')}<br>
           <strong>Risk:</strong> ${planner.risk_level}<br>
           <strong>Tests:</strong> ${planner.test_types?.join(', ')}`
        : '--';

    // Failed tests
    const failedSection = document.getElementById('failedTestsSection');
    const failedList = document.getElementById('failedTestsList');
    const failedTests = executor.failed_tests || [];

    if (failedTests.length > 0) {
        failedSection.style.display = 'block';
        failedList.innerHTML = failedTests.map(t => `<li>❌ ${escapeHtml(t)}</li>`).join('');
    } else {
        failedSection.style.display = 'none';
    }
}

function updateAgentStep(stepId, completed, statusText) {
    const step = document.getElementById(stepId);
    step.className = completed ? 'step completed' : 'step';
    step.querySelector('.step-status').textContent = statusText || '--';
}

// ─────────────────────────────────────────────
// RUNS TABLE
// ─────────────────────────────────────────────
function updateRunsTable(runs) {
    const tbody = document.getElementById('runsTableBody');

    if (runs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="loading">No runs found</td></tr>';
        return;
    }

    tbody.innerHTML = runs.slice(0, 20).map(run => `
        <tr>
            <td style="font-family: monospace; color: #818cf8;">${run.run_id || '--'}</td>
            <td>
                <span class="table-status ${run.status || 'unknown'}">
                    ${(run.status || '--').toUpperCase()}
                </span>
            </td>
            <td>${run.coverage != null ? run.coverage.toFixed(1) + '%' : '--'}</td>
            <td>${run.passed || 0}/${run.total || 0}</td>
            <td>${run.start_time ? formatDuration(run.start_time, run.end_time) : '--'}</td>
            <td>${formatDate(run.start_time)}</td>
        </tr>
    `).join('');
}

// ─────────────────────────────────────────────
// UTILITIES
// ─────────────────────────────────────────────
function formatTime(isoString) {
    if (!isoString) return '--';
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function formatDate(isoString) {
    if (!isoString) return '--';
    const date = new Date(isoString);
    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatDuration(start, end) {
    if (!start || !end) return '--';
    const ms = new Date(end) - new Date(start);
    const seconds = Math.floor(ms / 1000);
    return seconds > 60 ? `${Math.floor(seconds / 60)}m ${seconds % 60}s` : `${seconds}s`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
