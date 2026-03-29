let refreshTimer = null;

async function loadDashboard() {
  const data = await apiFetch('/api/dashboard/stats');
  if (!data) return;

  document.getElementById('m-subs').textContent = formatNum(data.total_subscribers);
  document.getElementById('m-views').textContent = formatNum(data.total_views);
  document.getElementById('m-earnings').textContent = `$${(data.estimated_earnings_nzd||0).toFixed(2)}`;
  document.getElementById('m-week').textContent = data.videos_this_week ?? '0';

  const sched = data.scheduler || {};
  const statusMap = {
    idle:['badge-muted','Idle'], running:['badge-info','Running'],
    paused:['badge-warning','Paused'], uploading:['badge-info','Uploading'],
    downloading:['badge-info','Downloading'], processing:['badge-info','Processing'],
    editing:['badge-info','Editing'], monitoring:['badge-info','Monitoring'],
  };
  const [cls, lbl] = statusMap[sched.status] || ['badge-muted', sched.status||'Unknown'];
  document.getElementById('status-badge').innerHTML = `<span class="badge ${cls}">${lbl}</span>`;
  document.getElementById('sys-status').innerHTML = `<span class="badge ${cls}">${lbl}</span>`;
  if (sched.next_run) document.getElementById('next-run').textContent = formatDate(sched.next_run);

  renderChannelCards(data.channels||[]);
  renderNotifications(data.notifications||[]);
  renderQueue(data.queue||[]);
  renderHistory(data.upload_history||[]);

  // Load system stats
  loadSystemStats();
}

async function loadSystemStats() {
  const s = await apiFetch('/api/system/stats');
  if (!s) return;

  // CPU
  const cpuEl = document.getElementById('stat-cpu');
  if (cpuEl) {
    const pct = s.cpu_percent || 0;
    const color = pct > 80 ? 'var(--error)' : pct > 60 ? 'var(--warning)' : 'var(--success)';
    cpuEl.innerHTML = `<span style="color:${color}">${pct}%</span>`;
  }

  // RAM
  const ramEl = document.getElementById('stat-ram');
  if (ramEl) ramEl.textContent = `${s.ram_used_gb}/${s.ram_total_gb}GB`;

  // Temp
  const tempEl = document.getElementById('stat-temp');
  if (tempEl) {
    if (s.cpu_temp) {
      const color = s.cpu_temp > 80 ? 'var(--error)' : s.cpu_temp > 65 ? 'var(--warning)' : 'var(--success)';
      tempEl.innerHTML = `<span style="color:${color}">${s.cpu_temp}°C</span>`;
    } else {
      tempEl.textContent = 'N/A';
    }
  }

  // Uptime
  const uptEl = document.getElementById('stat-uptime');
  if (uptEl) uptEl.textContent = s.uptime || '—';

  // Disk
  const diskEl = document.getElementById('stat-disk');
  if (diskEl) diskEl.textContent = s.disk_used || '—';
  const diskFreeEl = document.getElementById('stat-disk-free');
  if (diskFreeEl) diskFreeEl.textContent = s.disk_free || '—';

  // TTS counter
  const used = s.tts_chars_used || 0;
  const limit = s.tts_chars_limit || 1_000_000;
  const pct = Math.min((used / limit) * 100, 100);
  const barColor = pct >= 95 ? 'var(--error)' : pct >= 80 ? 'var(--warning)' : 'var(--success)';

  const ttsCharsEl = document.getElementById('tts-chars');
  if (ttsCharsEl) ttsCharsEl.textContent = formatNum(used);
  const ttsBarEl = document.getElementById('tts-bar');
  if (ttsBarEl) { ttsBarEl.style.width = pct + '%'; ttsBarEl.style.background = barColor; }
  const ttsPctEl = document.getElementById('tts-percent');
  if (ttsPctEl) ttsPctEl.textContent = pct.toFixed(1) + '%';

  const pausedBanner = document.getElementById('tts-paused-banner');
  if (pausedBanner) pausedBanner.style.display = s.tts_paused ? 'block' : 'none';
}

function renderChannelCards(channels) {
  const el = document.getElementById('channel-cards');
  if (!channels.length) { el.innerHTML = '<p style="color:var(--text-muted)">No channels yet. Add one in the Channels page.</p>'; return; }
  el.innerHTML = channels.map(ch => {
    const connected = ch.status === 'connected';
    const statusHtml = connected
      ? `<span class="badge badge-success">Connected as ${ch.youtube_channel_name||'Unknown'}</span>`
      : `<span class="badge badge-error">Not Connected</span>`;
    return `
    <div class="card" style="display:flex;flex-direction:column;gap:0.6rem;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.5rem;">
        <div><div class="channel-genre-tag">${ch.genre}</div><div class="channel-name-big">${ch.name}</div></div>
        ${statusHtml}
      </div>
      ${connected ? `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;font-size:0.82rem;">
          <div><span style="color:var(--text-muted)">Subscribers</span><br><strong>${formatNum(ch.subscriber_count)}</strong></div>
          <div><span style="color:var(--text-muted)">Views</span><br><strong>${formatNum(ch.view_count)}</strong></div>
        </div>
        <div style="font-size:0.75rem;color:var(--text-muted);">Last upload: ${formatDate(ch.last_upload)}</div>
      ` : `<div style="font-size:0.8rem;color:var(--text-muted);">Connect in <a href="/channels">Channels</a> page</div>`}
      <div style="font-size:0.72rem;color:var(--text-muted);">${ch.videos_per_day||1} video/day · ${ch.shorts_per_day||2} shorts/day · ${ch.video_length_min||10}–${ch.video_length_max||15} min</div>
    </div>`;
  }).join('');
}

function renderNotifications(notifs) {
  const countEl = document.getElementById('notif-count');
  const listEl = document.getElementById('notif-list');
  if (!notifs.length) { countEl.style.display='none'; listEl.innerHTML='<div class="notif-empty">No new notifications</div>'; return; }
  countEl.textContent = notifs.length; countEl.style.display='block';
  const typeColor = {error:'error',warning:'warning',milestone:'milestone',info:'info'};
  listEl.innerHTML = notifs.map(n => `
    <div class="notif-item" id="notif-${n.id}">
      <div class="notif-dot ${typeColor[n.type]||'info'}"></div>
      <div class="notif-text">
        <div class="notif-title">${n.title}</div>
        <div class="notif-msg">${n.message}</div>
        <div class="notif-msg" style="font-size:0.7rem;margin-top:2px;">${formatDate(n.created_at)}</div>
      </div>
      <button class="notif-dismiss" onclick="dismissNotif(${n.id})">×</button>
    </div>`).join('');
}

function renderQueue(queue) {
  const tbody = document.getElementById('queue-body');
  if (!queue.length) { tbody.innerHTML='<tr><td colspan="4" style="color:var(--text-muted);text-align:center;padding:1.5rem;">Queue is empty</td></tr>'; return; }
  tbody.innerHTML = queue.map(q=>`<tr><td>${q.channel_name}</td><td>${q.title||'—'}</td><td>${formatDate(q.scheduled_time)}</td><td>${badgeHtml(q.status)}</td></tr>`).join('');
}

function renderHistory(history) {
  const tbody = document.getElementById('history-body');
  if (!history.length) { tbody.innerHTML='<tr><td colspan="6" style="color:var(--text-muted);text-align:center;padding:1.5rem;">No uploads yet</td></tr>'; return; }
  tbody.innerHTML = history.map(h=>`<tr><td>${formatDate(h.uploaded_at)}</td><td>${h.channel_name}</td><td>${h.title||'—'}</td><td>${h.duration?h.duration+' min':'—'}</td><td>${badgeHtml(h.status)}</td><td>${formatNum(h.views)}</td></tr>`).join('');
}

function toggleNotifications() { document.getElementById('notif-dropdown').classList.toggle('open'); }

async function dismissNotif(id) {
  await apiFetch(`/api/notifications/${id}/dismiss`, {method:'POST'});
  document.getElementById(`notif-${id}`)?.remove();
  loadDashboard();
}

async function pauseSystem() {
  const res = await apiFetch('/api/dashboard/pause', {method:'POST'});
  if (res) loadDashboard();
}

async function resumeSystem() {
  const res = await apiFetch('/api/dashboard/resume', {method:'POST'});
  if (res) loadDashboard();
}

function openShutdownModal() { document.getElementById('shutdown-modal').classList.add('open'); }
function closeShutdownModal() { document.getElementById('shutdown-modal').classList.remove('open'); }

async function doShutdown() {
  closeShutdownModal();
  await apiFetch('/api/system/shutdown', {method:'POST'});
  document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:1rem;color:var(--text-muted);"><div style="font-size:2rem;">🔴</div><div style="font-size:1.1rem;">System shutting down...</div><div style="font-size:0.85rem;">You can close this tab.</div></div>';
}

document.addEventListener('click', e => {
  const bell = document.getElementById('notif-bell');
  if (bell && !bell.contains(e.target)) document.getElementById('notif-dropdown')?.classList.remove('open');
});

document.addEventListener('DOMContentLoaded', () => {
  loadDashboard();
  refreshTimer = setInterval(loadDashboard, 10000);
  setInterval(loadSystemStats, 5000);
});
