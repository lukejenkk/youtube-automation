const FIELDS = [
  'YOUTUBE_API_KEY_1','YOUTUBE_API_KEY_2',
  'PEXELS_API_KEY','PIXABAY_API_KEY',
  'TTS_PROVIDER','GOOGLE_TTS_API_KEY','ELEVENLABS_API_KEY',
  'REDDIT_APP_ID','REDDIT_APP_SECRET','REDDIT_USER_AGENT',
  'UPLOAD_WINDOW_START','UPLOAD_WINDOW_END',
  'TWILIO_ACCOUNT_SID','TWILIO_AUTH_TOKEN','TWILIO_FROM','TWILIO_TO',
  'EMAIL_SENDER','EMAIL_PASSWORD','EMAIL_RECIPIENT',
  'DUCKDNS_DOMAIN','DUCKDNS_TOKEN','TIMEZONE','PI_LOCAL_IP','VIDEO_RETENTION_DAYS',
];

async function loadSettings() {
  const d = await apiFetch('/api/settings');
  if (!d) return;
  FIELDS.forEach(k => { const el = document.getElementById(k); if (el && d[k] !== undefined) el.value = d[k]; });
  updateTtsFields();
  if (d.oauth_json_set) {
    document.getElementById('oauth-upload-box').classList.add('upload-success');
    document.getElementById('oauth-icon').textContent = '✅';
    document.getElementById('oauth-upload-text').innerHTML =
      `<strong style="color:var(--success)">OAuth JSON saved</strong>${d.oauth_json_client_id ? '<br><span style="color:#555;font-size:0.75rem;">Client: ' + d.oauth_json_client_id + '...</span>' : ''}`;
  }
}

function updateTtsFields() {
  const v = document.getElementById('TTS_PROVIDER').value;
  document.getElementById('google-tts-fields').style.display = v === 'google' ? '' : 'none';
  document.getElementById('elevenlabs-fields').style.display = v === 'elevenlabs' ? '' : 'none';
}

async function saveAll() {
  const payload = {};
  FIELDS.forEach(k => { const el = document.getElementById(k); if (el) payload[k] = el.value; });
  const res = await apiFetch('/api/settings', { method: 'POST', body: payload });
  if (res?.success) showAlert('alert-area', '✓ All settings saved successfully.', 'success');
  else showAlert('alert-area', '✗ Save failed.', 'error');
}

// OAuth file upload
function dragOver(e) { e.preventDefault(); document.getElementById('oauth-upload-box').classList.add('dragover'); }
function dragLeave(e) { document.getElementById('oauth-upload-box').classList.remove('dragover'); }
function dropFile(e) {
  e.preventDefault();
  document.getElementById('oauth-upload-box').classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) uploadOAuthFile(file);
}
function handleFileSelect(e) { const file = e.target.files[0]; if (file) uploadOAuthFile(file); }

async function uploadOAuthFile(file) {
  const statusEl = document.getElementById('oauth-status');
  statusEl.innerHTML = '<span style="color:#555">Uploading...</span>';
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch('/api/settings/upload-oauth', { method: 'POST', body: formData, credentials: 'same-origin' });
    const d = await res.json();
    if (d.success) {
      statusEl.innerHTML = `<span style="color:var(--success)">✓ ${d.message} — Client: ${d.client_id}...</span>`;
      document.getElementById('oauth-upload-box').classList.add('upload-success');
      document.getElementById('oauth-icon').textContent = '✅';
      document.getElementById('oauth-upload-text').innerHTML = `<strong style="color:var(--success)">OAuth JSON saved!</strong><br><span style="color:#555;font-size:0.75rem;">Client: ${d.client_id}...</span>`;
    } else {
      statusEl.innerHTML = `<span style="color:var(--error)">✗ ${d.error}</span>`;
    }
  } catch (e) {
    statusEl.innerHTML = `<span style="color:var(--error)">✗ ${e.message}</span>`;
  }
}

async function testOAuth() {
  const el = document.getElementById('oauth-test-status');
  el.innerHTML = '<span style="color:#555">Testing...</span>';
  const res = await apiFetch('/api/settings/test-oauth', { method: 'POST', body: {} });
  el.innerHTML = res?.valid
    ? `<span style="color:var(--success)">✓ ${res.message}</span>`
    : `<span style="color:var(--error)">✗ ${res?.error || 'Not valid'}</span>`;
}

async function clearOAuth() {
  if (!confirm('Clear saved OAuth JSON? You will need to upload a new file to reconnect channels.')) return;
  const res = await apiFetch('/api/settings/clear-oauth', { method: 'POST' });
  if (res?.success) {
    document.getElementById('oauth-upload-box').classList.remove('upload-success');
    document.getElementById('oauth-icon').textContent = '📄';
    document.getElementById('oauth-upload-text').innerHTML = '<strong>Click to upload</strong> or drag & drop your <code>client_secret.json</code> here';
    document.getElementById('oauth-status').innerHTML = '';
    document.getElementById('oauth-test-status').textContent = '';
    showAlert('alert-area', '✓ OAuth JSON cleared.', 'success');
  }
}

// Test buttons
function setStatus(id, loading) {
  document.getElementById(id).innerHTML = `<span style="color:#555">${loading}</span>`;
}
function setOk(id, msg) { document.getElementById(id).innerHTML = `<span style="color:var(--success)">✓ ${msg}</span>`; }
function setErr(id, msg) { document.getElementById(id).innerHTML = `<span style="color:var(--error)">✗ ${msg}</span>`; }

async function testApi(name) {
  const statusId = `${name}-status`;
  setStatus(statusId, 'Testing...');
  const res = await apiFetch(`/api/settings/test-${name}`, { method: 'POST', body: {} });
  if (res?.success) setOk(statusId, res.message);
  else setErr(statusId, res?.error || 'Failed');
}

async function testSms() {
  setStatus('sms-status', 'Sending...');
  const res = await apiFetch('/api/settings/test-sms', { method: 'POST' });
  if (res?.success) setOk('sms-status', 'SMS sent!');
  else setErr('sms-status', 'Failed — check Twilio config');
}

async function testEmail() {
  setStatus('email-status', 'Sending...');
  const res = await apiFetch('/api/settings/test-email', { method: 'POST' });
  if (res?.success) setOk('email-status', 'Email sent!');
  else setErr('email-status', 'Failed — check email config');
}

// Change PIN modal
let pinStep = 'current', pinCurrent = '', pinNew = '', pinBuf = '';

function openPinModal() {
  pinStep = 'current'; pinCurrent = ''; pinNew = ''; pinBuf = '';
  document.getElementById('pin-modal-sub').textContent = 'Enter your current PIN';
  updatePinDots();
  document.getElementById('pin-err').textContent = '';
  document.getElementById('pin-modal').classList.add('open');
}
function closePinModal() { document.getElementById('pin-modal').classList.remove('open'); }

function updatePinDots() {
  for (let i = 0; i < 4; i++) {
    const el = document.getElementById('pm' + i);
    if (el) { el.classList.toggle('filled', i < pinBuf.length); el.classList.remove('error'); }
  }
}

function pinK(d) {
  if (pinBuf.length >= 4) return;
  pinBuf += d; updatePinDots();
  if (pinBuf.length === 4) setTimeout(pinNext, 130);
}
function pinDel() { pinBuf = pinBuf.slice(0,-1); updatePinDots(); }

async function pinNext() {
  if (pinStep === 'current') {
    pinCurrent = pinBuf; pinBuf = ''; pinStep = 'new';
    document.getElementById('pin-modal-sub').textContent = 'Enter your new PIN';
    updatePinDots();
  } else if (pinStep === 'new') {
    pinNew = pinBuf; pinBuf = ''; pinStep = 'confirm';
    document.getElementById('pin-modal-sub').textContent = 'Confirm your new PIN';
    updatePinDots();
  } else {
    if (pinBuf !== pinNew) {
      document.getElementById('pin-err').textContent = "PINs don't match";
      for (let i=0;i<4;i++) document.getElementById('pm'+i)?.classList.add('error');
      setTimeout(() => { pinBuf=''; pinNew=''; pinStep='new'; document.getElementById('pin-modal-sub').textContent='Enter your new PIN'; updatePinDots(); document.getElementById('pin-err').textContent=''; }, 900);
      return;
    }
    const res = await apiFetch('/api/settings/change-pin', { method:'POST', body:{ current_pin: pinCurrent, new_pin: pinNew } });
    if (res?.success) { closePinModal(); showAlert('alert-area', '✓ PIN changed.', 'success'); }
    else { document.getElementById('pin-err').textContent = res?.error || 'Failed'; setTimeout(() => { pinBuf=''; pinCurrent=''; pinNew=''; pinStep='current'; document.getElementById('pin-modal-sub').textContent='Enter your current PIN'; updatePinDots(); document.getElementById('pin-err').textContent=''; }, 900); }
  }
}

document.addEventListener('DOMContentLoaded', loadSettings);
