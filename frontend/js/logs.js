// logs.js

let refreshTimer = null;

async function loadLogs() {
  const data = await apiFetch('/api/logs');
  if (!data) return;

  const container = document.getElementById('log-container');
  const logs = data.logs || [];

  if (!logs.length) {
    container.innerHTML = '<div style="padding:2rem;color:var(--text-muted);text-align:center;">No log entries yet.</div>';
    return;
  }

  container.innerHTML = logs.map(entry => {
    const levelClass = `log-level-${entry.level || 'INFO'}`;
    const ts = entry.timestamp || '';
    const level = entry.level || 'INFO';
    const msg = escapeHtml(entry.message || '');

    return `<div class="log-entry">
      <span class="log-ts">${ts}</span>
      <span class="${levelClass}">${level}</span>
      <span>${msg}</span>
    </div>`;
  }).join('');
}

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

document.addEventListener('DOMContentLoaded', () => {
  loadLogs();
  refreshTimer = setInterval(loadLogs, 5000);
});
