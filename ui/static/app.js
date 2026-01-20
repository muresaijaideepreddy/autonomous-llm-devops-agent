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
// COVERAGE RUNNER
// ─────────────────────────────────────────────
async function runCoverage() {
    const btn = document.getElementById('runCoverageBtn');
    const panel = document.getElementById('coveragePanel');

    // Disable button and show running state
    btn.disabled = true;
    btn.innerHTML = '<span class="coverage-icon">⏳</span> Running...';

    // Show panel
    panel.style.display = 'block';
    document.getElementById('covPercent').textContent = '...';
    document.getElementById('covPassed').textContent = '...';
    document.getElementById('covFailed').textContent = '...';
    document.getElementById('covTotal').textContent = '...';
    document.getElementById('coverageOutput').textContent = 'Running pytest with coverage...';
    document.getElementById('uncoveredSection').style.display = 'none';

    try {
        const response = await fetch('/api/coverage/run', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            // Update stats
            document.getElementById('covPercent').textContent =
                data.coverage_percent != null ? `${data.coverage_percent.toFixed(1)}%` : '--';
            document.getElementById('covPassed').textContent = data.passed || 0;
            document.getElementById('covFailed').textContent = data.failed || 0;
            document.getElementById('covTotal').textContent = data.total || 0;

            // Show uncovered files if any
            const uncoveredFiles = data.uncovered_files || {};
            const uncoveredCount = Object.keys(uncoveredFiles).length;

            if (uncoveredCount > 0) {
                document.getElementById('uncoveredSection').style.display = 'block';
                let uncoveredHtml = '';
                for (const [file, lines] of Object.entries(uncoveredFiles)) {
                    const fileName = file.split('/').pop();
                    uncoveredHtml += `<div class="uncovered-item">
                        <span class="uncovered-file">${fileName}</span>
                        <span class="uncovered-lines">${lines.length} lines</span>
                    </div>`;
                }
                document.getElementById('uncoveredList').innerHTML = uncoveredHtml;
            }

            // Status message
            const status = data.returncode === 0 ? '✅ All tests passed!' : `⚠️ ${data.failed} test(s) failed`;
            document.getElementById('coverageOutput').innerHTML = `
                <div class="coverage-status ${data.returncode === 0 ? 'success' : 'warning'}">
                    ${status}
                </div>
                <div class="coverage-hint">
                    ${data.coverage_percent < 98 ? '💡 Coverage below 98% - Healer Agent will activate when you run the pipeline!' : '✨ Coverage meets threshold!'}
                </div>
            `;
        } else {
            document.getElementById('coverageOutput').innerHTML = `
                <div class="coverage-status error">
                    ❌ Error: ${data.error || 'Failed to run coverage'}
                </div>
            `;
        }
    } catch (error) {
        document.getElementById('coverageOutput').innerHTML = `
            <div class="coverage-status error">
                ❌ Error: ${error.message}
            </div>
        `;
    }

    // Re-enable button
    btn.disabled = false;
    btn.innerHTML = '<span class="coverage-icon">📊</span> Run Coverage';
}

function closeCoveragePanel() {
    document.getElementById('coveragePanel').style.display = 'none';
}

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

// ─────────────────────────────────────────────
// LIVE PIPELINE EXECUTION
// ─────────────────────────────────────────────
let eventSource = null;
let logCount = 0;

function startPipeline() {
    const btn = document.getElementById('runPipelineBtn');
    const livePanel = document.getElementById('livePanel');

    // Disable button and show running state
    btn.disabled = true;
    btn.classList.add('running');
    btn.innerHTML = '<span class="run-icon">⏳</span> Running...';

    // Reset and show live panel
    resetLivePanel();
    livePanel.style.display = 'block';
    livePanel.scrollIntoView({ behavior: 'smooth' });

    // Start SSE connection
    eventSource = new EventSource('/api/run/stream');

    eventSource.onmessage = function (e) {
        try {
            const event = JSON.parse(e.data);
            handleSSEEvent(event);
        } catch (err) {
            console.error('Failed to parse SSE event:', err);
        }
    };

    eventSource.onerror = function (e) {
        console.error('SSE connection error:', e);
        eventSource.close();
        btn.disabled = false;
        btn.classList.remove('running');
        btn.innerHTML = '<span class="run-icon">▶</span> Run Pipeline';
    };
}

function handleSSEEvent(event) {
    const type = event.type;
    const stage = event.stage;
    const message = event.message;
    const data = event.data || {};

    // Add to logs
    addLogEntry(event);

    switch (type) {
        case 'pipeline_start':
            document.getElementById('liveRunId').textContent = data.run_id || '--';
            document.getElementById('liveCommit').textContent = data.commit || '--';
            break;

        case 'stage_start':
            setStageState(stage, 'active', message);
            break;

        case 'stage_complete':
            setStageState(stage, 'completed', message);
            break;

        case 'stage_skip':
            setStageState(stage, 'skipped', message || 'Skipped');
            break;

        case 'log':
            // Already added to logs above
            break;

        case 'coverage_report':
            // Display coverage details
            showCoverageDetails(data);
            break;

        case 'summary':
            showSummary(data, message);
            finishPipeline();
            break;

        case 'pipeline_complete':
            if (eventSource) {
                eventSource.close();
            }
            refreshData(); // Refresh dashboard data
            break;
    }
}

function setStageState(stageName, state, message) {
    const stageMap = {
        'planner': 'stagePlanner',
        'tester': 'stageTester',
        'executor': 'stageExecutor',
        'healer': 'stageHealer'
    };

    const stageId = stageMap[stageName];
    if (!stageId) return;

    const stageEl = document.getElementById(stageId);
    stageEl.setAttribute('data-state', state);

    // Update badge
    const badge = stageEl.querySelector('.stage-badge');
    const stateLabels = {
        'waiting': 'WAITING',
        'active': 'RUNNING',
        'completed': 'COMPLETED',
        'skipped': 'SKIPPED',
        'error': 'ERROR'
    };
    badge.textContent = stateLabels[state] || state.toUpperCase();

    // Update message
    if (message) {
        stageEl.querySelector('.stage-message').textContent = message;
    }
}

function addLogEntry(event) {
    const terminal = document.getElementById('logsTerminal');
    const timestamp = new Date(event.timestamp).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    const stageTag = event.stage ? `[${event.stage.toUpperCase()}]` : '[SYSTEM]';
    const message = event.message || event.type;

    const entryClass = event.type === 'stage_complete' ? 'info' : '';

    const entry = document.createElement('div');
    entry.className = `log-entry ${entryClass}`;
    entry.innerHTML = `
        <span class="timestamp">${timestamp}</span>
        <span class="stage-tag">${stageTag}</span>
        <span class="message">${escapeHtml(message)}</span>
    `;

    terminal.appendChild(entry);
    terminal.scrollTop = terminal.scrollHeight;

    logCount++;
    document.getElementById('logCount').textContent = `${logCount} entries`;
}

function showSummary(data, message) {
    const summaryEl = document.getElementById('liveSummary');
    const statusEl = document.getElementById('summaryStatus');

    const isPassed = data.status === 'pass';

    summaryEl.classList.toggle('failed', !isPassed);
    statusEl.querySelector('.summary-icon').textContent = isPassed ? '✔' : '✖';
    statusEl.querySelector('.summary-text').textContent = message || (isPassed ? 'CI PASSED' : 'CI FAILED');

    document.getElementById('summaryPassed').textContent = data.passed || 0;
    document.getElementById('summaryFailed').textContent = data.failed || 0;

    const coverage = data.coverage || 0;
    document.getElementById('summaryCoverage').textContent = `${coverage.toFixed(1)}%`;

    // Animate coverage ring with color based on threshold
    const ring = document.getElementById('coverageRing');

    // Remove existing color classes
    ring.classList.remove('high', 'medium', 'low');

    // Add color class based on coverage level
    if (coverage >= 80) {
        ring.classList.add('high');  // Green
    } else if (coverage >= 50) {
        ring.classList.add('medium');  // Yellow
    } else {
        ring.classList.add('low');  // Red
    }

    // Animate the ring fill
    ring.style.strokeDasharray = `${coverage}, 100`;

    summaryEl.style.display = 'block';
}

function finishPipeline() {
    const btn = document.getElementById('runPipelineBtn');
    btn.disabled = false;
    btn.classList.remove('running');
    btn.innerHTML = '<span class="run-icon">▶</span> Run Pipeline';
}

function resetLivePanel() {
    // Reset stages
    ['stagePlanner', 'stageTester', 'stageExecutor', 'stageHealer'].forEach(id => {
        const el = document.getElementById(id);
        el.setAttribute('data-state', 'waiting');
        el.querySelector('.stage-badge').textContent = 'WAITING';
        el.querySelector('.stage-message').textContent = '--';
    });

    // Reset logs
    document.getElementById('logsTerminal').innerHTML = '';
    logCount = 0;
    document.getElementById('logCount').textContent = '0 entries';

    // Reset meta
    document.getElementById('liveRunId').textContent = '--';
    document.getElementById('liveCommit').textContent = '--';

    // Hide summary
    document.getElementById('liveSummary').style.display = 'none';
}

function closeLivePanel() {
    document.getElementById('livePanel').style.display = 'none';
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ─────────────────────────────────────────────
// COVERAGE DETAILS DISPLAY
// ─────────────────────────────────────────────
function showCoverageDetails(data) {
    const terminal = document.getElementById('logsTerminal');
    const coverage = data.coverage_percent || 0;
    const threshold = data.threshold || 98;
    const meetsThreshold = data.meets_threshold || false;
    const uncoveredFiles = data.uncovered_files || {};

    // Create coverage summary entry
    const entry = document.createElement('div');
    entry.className = `log-entry ${meetsThreshold ? 'success' : 'warning'}`;

    const statusIcon = meetsThreshold ? '✅' : '⚠️';
    const statusText = meetsThreshold ? 'meets threshold' : `below ${threshold}% threshold`;

    let html = `
        <div class="coverage-report">
            <div class="coverage-header">
                ${statusIcon} <strong>Coverage: ${coverage.toFixed(2)}%</strong> (${statusText})
            </div>
    `;

    // Show uncovered files if any
    const uncoveredCount = Object.keys(uncoveredFiles).length;
    if (uncoveredCount > 0) {
        html += `<div class="uncovered-files">`;
        html += `<div class="uncovered-header">📂 ${uncoveredCount} file(s) with uncovered lines:</div>`;

        for (const [file, lines] of Object.entries(uncoveredFiles)) {
            const fileName = file.split('/').pop();
            const lineCount = Array.isArray(lines) ? lines.length : 0;
            html += `<div class="uncovered-file">
                <span class="file-name">${escapeHtml(fileName)}</span>
                <span class="line-count">${lineCount} line(s) uncovered</span>
            </div>`;
        }
        html += `</div>`;
    }

    html += `</div>`;
    entry.innerHTML = html;

    terminal.appendChild(entry);
    terminal.scrollTop = terminal.scrollHeight;
}
