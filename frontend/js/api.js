// api.js — shared fetch helpers

async function apiFetch(url, options = {}) {
  const defaults = {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
  };
  const merged = { ...defaults, ...options };
  if (merged.body && typeof merged.body === 'object') {
    merged.body = JSON.stringify(merged.body);
  }
  const res = await fetch(url, merged);
  if (res.status === 401) {
    window.location.href = '/';
    return null;
  }
  return res.json();
}

function formatNum(n) {
  if (n == null) return '—';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString('en-NZ', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function badgeHtml(status) {
  const map = {
    connected: ['badge-success', 'Connected'],
    not_connected: ['badge-error', 'Not Connected'],
    idle: ['badge-muted', 'Idle'],
    uploading: ['badge-info', 'Uploading'],
    queued: ['badge-warning', 'Queued'],
    error: ['badge-error', 'Error'],
    running: ['badge-info', 'Running'],
    paused: ['badge-warning', 'Paused'],
    success: ['badge-success', 'Success'],
    failed: ['badge-error', 'Failed'],
    pending: ['badge-muted', 'Pending'],
  };
  const [cls, label] = map[status] || ['badge-muted', status];
  return `<span class="badge ${cls}">${label}</span>`;
}

function showAlert(containerId, message, type = 'success') {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
  setTimeout(() => { el.innerHTML = ''; }, 4000);
}
