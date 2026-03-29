let genres = [];

async function loadGenres() {
  const res = await apiFetch('/api/channels/genres');
  if (!res) return;
  genres = res.genres || [];
  ['add-genre', 'edit-genre'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = genres.map(g => `<option value="${g}">${g}</option>`).join('');
  });
}

async function loadChannels() {
  const channels = await apiFetch('/api/channels');
  if (!channels) return;
  renderChannels(channels);
}

function renderChannels(channels) {
  const grid = document.getElementById('channels-grid');
  if (!channels.length) {
    grid.innerHTML = `<div style="color:var(--text-muted);grid-column:1/-1;text-align:center;padding:3rem;">
      No channels yet. Click <strong>Add Channel</strong> to get started.
    </div>`;
    return;
  }
  grid.innerHTML = channels.map(ch => {
    const connected = ch.status === 'connected';
    const statusHtml = connected
      ? `<span class="badge badge-success">Connected as ${ch.youtube_channel_name||'Unknown'}</span>`
      : `<span class="badge badge-error">Not Connected</span>`;
    return `
    <div class="channel-card">
      <div>
        <div class="channel-genre-tag">${ch.genre}</div>
        <div class="channel-name-big">${ch.name}</div>
      </div>
      <div>${statusHtml}</div>
      ${connected ? `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;">
          <div class="metric-card" style="padding:0.65rem;">
            <div class="metric-label">Subscribers</div>
            <div style="font-size:1.1rem;font-weight:700;">${formatNum(ch.subscriber_count)}</div>
          </div>
          <div class="metric-card" style="padding:0.65rem;">
            <div class="metric-label">Views</div>
            <div style="font-size:1.1rem;font-weight:700;">${formatNum(ch.view_count)}</div>
          </div>
        </div>
        <div style="font-size:0.75rem;color:var(--text-muted);">Last upload: ${formatDate(ch.last_upload)}</div>
      ` : `<div style="font-size:0.8rem;color:var(--text-muted);">Connect a Google account to link a YouTube channel.</div>`}
      <div style="font-size:0.72rem;color:var(--text-muted);">
        📹 ${ch.videos_per_day||1} video/day · 📱 ${ch.shorts_per_day||2} shorts/day · ⏱ ${ch.video_length_min||10}–${ch.video_length_max||15} min
      </div>
      <div class="channel-actions">
        ${!connected ? `<a href="/auth/start/${ch.id}" class="btn btn-primary" style="flex:1;justify-content:center;">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
          Connect
        </a>` : ''}
        <button class="btn btn-ghost" onclick='openEditModal(${JSON.stringify(ch)})'>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          Edit
        </button>
        <button class="btn btn-ghost" style="color:var(--error);border-color:rgba(255,71,87,0.3);" onclick="openDeleteModal(${ch.id})">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
          Delete
        </button>
      </div>
    </div>`;
  }).join('');
}

function openAddModal() {
  document.getElementById('add-name').value = '';
  document.getElementById('add-modal').classList.add('open');
}
function closeAddModal() { document.getElementById('add-modal').classList.remove('open'); }

async function createChannel() {
  const payload = {
    name: document.getElementById('add-name').value.trim() || 'New Channel',
    genre: document.getElementById('add-genre').value,
    video_length_min: parseInt(document.getElementById('add-length-min').value),
    video_length_max: parseInt(document.getElementById('add-length-max').value),
    videos_per_day: parseInt(document.getElementById('add-vpd').value),
    shorts_per_day: parseInt(document.getElementById('add-spd').value),
  };
  const res = await apiFetch('/api/channels', { method: 'POST', body: payload });
  if (res && res.id) {
    closeAddModal();
    showAlert('alert-area', '✓ Channel created.', 'success');
    loadChannels();
  } else {
    showAlert('alert-area', '✗ Failed to create channel.', 'error');
  }
}

function openEditModal(ch) {
  document.getElementById('edit-id').value = ch.id;
  document.getElementById('edit-name').value = ch.name;
  document.getElementById('edit-genre').value = ch.genre;
  document.getElementById('edit-length-min').value = ch.video_length_min || 10;
  document.getElementById('edit-length-max').value = ch.video_length_max || 15;
  document.getElementById('edit-vpd').value = ch.videos_per_day || 1;
  document.getElementById('edit-spd').value = ch.shorts_per_day || 2;
  document.getElementById('edit-active').checked = !!ch.active;
  document.getElementById('edit-modal').classList.add('open');
}
function closeEditModal() { document.getElementById('edit-modal').classList.remove('open'); }

async function saveChannel() {
  const id = document.getElementById('edit-id').value;
  const payload = {
    name: document.getElementById('edit-name').value,
    genre: document.getElementById('edit-genre').value,
    video_length_min: parseInt(document.getElementById('edit-length-min').value),
    video_length_max: parseInt(document.getElementById('edit-length-max').value),
    videos_per_day: parseInt(document.getElementById('edit-vpd').value),
    shorts_per_day: parseInt(document.getElementById('edit-spd').value),
    active: document.getElementById('edit-active').checked ? 1 : 0,
  };
  const res = await apiFetch(`/api/channels/${id}`, { method: 'PUT', body: payload });
  if (res && res.id) {
    closeEditModal();
    showAlert('alert-area', '✓ Channel updated.', 'success');
    loadChannels();
  } else {
    showAlert('alert-area', '✗ Failed to update.', 'error');
  }
}

function openDeleteModal(id) {
  document.getElementById('delete-id').value = id;
  document.getElementById('delete-modal').classList.add('open');
}
function closeDeleteModal() { document.getElementById('delete-modal').classList.remove('open'); }

async function confirmDelete() {
  const id = document.getElementById('delete-id').value;
  const res = await apiFetch(`/api/channels/${id}`, { method: 'DELETE' });
  closeDeleteModal();
  if (res && res.success) {
    showAlert('alert-area', '✓ Channel deleted.', 'success');
    loadChannels();
  } else {
    showAlert('alert-area', '✗ Failed to delete.', 'error');
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  await loadGenres();
  await loadChannels();
});
