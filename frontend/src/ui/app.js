import { createVoiceClient } from '../lib/vapi.js';

const STATUS = {
  idle: 'Ready when you are',
  connecting: 'Connecting…',
  listening: 'Listening',
  speaking: 'Assistant speaking',
  error: 'Something went wrong',
};

function brandMark() {
  return `
    <span class="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4 14c3-7 13-7 16 0" stroke="#7FD4C5" stroke-width="2" stroke-linecap="round"/>
        <circle cx="12" cy="8" r="2.2" fill="#E8F7F3"/>
      </svg>
    </span>
  `;
}

function micIcon() {
  return `
    <svg class="btn-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" stroke="currentColor" stroke-width="1.8"/>
      <path d="M6 11a6 6 0 0 0 12 0" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
      <path d="M12 17v3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
    </svg>
  `;
}

function endIcon() {
  return `
    <svg class="btn-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
    </svg>
  `;
}

function muteIcon(muted) {
  if (muted) {
    return `
      <svg class="btn-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M4 4l16 16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        <rect x="9" y="3" width="6" height="11" rx="3" stroke="currentColor" stroke-width="1.8"/>
        <path d="M6 11a6 6 0 0 0 8.5 5.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
      </svg>
    `;
  }
  return `
    <svg class="btn-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" stroke="currentColor" stroke-width="1.8"/>
      <path d="M6 11a6 6 0 0 0 12 0M12 17v3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
    </svg>
  `;
}

function renderShell(root) {
  root.innerHTML = `
    <div class="atmosphere" aria-hidden="true"></div>
    <div class="shell">
      <header class="brand-bar">
        ${brandMark()}
        <span class="brand-name">Auralis</span>
      </header>

      <main class="hero">
        <div class="hero-copy">
          <h1 class="hero-title">Patient intake,<br /><em>spoken simply</em></h1>
          <p class="hero-lede">
            Start a secure voice session. Our assistant registers or updates
            your record — no forms to hunt through.
          </p>
        </div>

        <div class="orb-stage" data-state="idle" id="orb-stage" aria-hidden="true">
          <div class="orb-ring"></div>
          <div class="orb-ring"></div>
          <div class="orb"></div>
        </div>

        <p class="status" id="status" data-tone="ok" role="status">${STATUS.idle}</p>

        <div id="setup-slot"></div>

        <div class="controls" id="controls">
          <button type="button" class="btn btn-primary" id="btn-start">
            ${micIcon()}
            Start Call
          </button>
          <button type="button" class="btn btn-ghost" id="btn-mute" disabled>
            ${muteIcon(false)}
            Mute
          </button>
          <button type="button" class="btn btn-danger" id="btn-end" disabled>
            ${endIcon()}
            End Call
          </button>
        </div>

        <section class="panel" id="transcript-panel" aria-live="polite">
          <div class="panel-header">Live transcript</div>
          <div class="transcript" id="transcript">
            <p class="transcript-empty">Conversation will appear here.</p>
          </div>
        </section>
      </main>

      <p class="footer-note">Mic stays in your browser. Records save through the clinic API.</p>
    </div>
  `;
}

function setStatus(el, key, tone = 'ok') {
  el.textContent = STATUS[key] || key;
  el.dataset.tone = tone;
}

function setOrbState(stage, state) {
  stage.dataset.state = state;
}

function appendTranscript(list, { role, text }) {
  const empty = list.querySelector('.transcript-empty');
  if (empty) empty.remove();

  const bubble = document.createElement('div');
  bubble.className = `bubble ${role}`;
  bubble.textContent = text;
  list.appendChild(bubble);
  list.scrollTop = list.scrollHeight;
}

function clearTranscript(list) {
  list.innerHTML = '<p class="transcript-empty">Conversation will appear here.</p>';
}

export function mountApp(root) {
  renderShell(root);

  const orbStage = root.querySelector('#orb-stage');
  const statusEl = root.querySelector('#status');
  const setupSlot = root.querySelector('#setup-slot');
  const btnStart = root.querySelector('#btn-start');
  const btnMute = root.querySelector('#btn-mute');
  const btnEnd = root.querySelector('#btn-end');
  const panel = root.querySelector('#transcript-panel');
  const transcript = root.querySelector('#transcript');

  const publicKey = import.meta.env.VITE_VAPI_PUBLIC_KEY;
  const assistantId = import.meta.env.VITE_VAPI_ASSISTANT_ID;

  let client;

  try {
    client = createVoiceClient({
      publicKey,
      assistantId,
      handlers: {
        onConnecting() {
          setOrbState(orbStage, 'connecting');
          setStatus(statusEl, 'connecting');
          btnStart.disabled = true;
        },
        onCallStart() {
          setOrbState(orbStage, 'listening');
          setStatus(statusEl, 'listening');
          btnStart.disabled = true;
          btnEnd.disabled = false;
          btnMute.disabled = false;
          panel.classList.add('is-open');
          clearTranscript(transcript);
        },
        onCallEnd() {
          setOrbState(orbStage, 'idle');
          setStatus(statusEl, 'idle');
          btnStart.disabled = false;
          btnEnd.disabled = true;
          btnMute.disabled = true;
          btnMute.innerHTML = `${muteIcon(false)} Mute`;
          panel.classList.remove('is-open');
        },
        onSpeechStart() {
          setOrbState(orbStage, 'speaking');
          setStatus(statusEl, 'speaking');
        },
        onSpeechEnd() {
          setOrbState(orbStage, 'listening');
          setStatus(statusEl, 'listening');
        },
        onTranscript(entry) {
          appendTranscript(transcript, entry);
        },
        onError(error) {
          console.error('[Auralis]', error);
          setOrbState(orbStage, 'error');
          setStatus(statusEl, 'error', 'error');
          btnStart.disabled = false;
          btnEnd.disabled = true;
          btnMute.disabled = true;
        },
      },
    });
  } catch (err) {
    setupSlot.innerHTML = `
      <p class="setup-hint">
        ${err.message}
        Add <code>VITE_VAPI_PUBLIC_KEY</code> and
        <code>VITE_VAPI_ASSISTANT_ID</code> to <code>frontend/.env</code>,
        then restart <code>npm run dev</code>.
      </p>
    `;
    btnStart.disabled = true;
    return;
  }

  btnStart.addEventListener('click', async () => {
    try {
      await client.start();
    } catch (err) {
      console.error('[Auralis] start failed', err);
      setOrbState(orbStage, 'error');
      setStatus(statusEl, 'error', 'error');
      btnStart.disabled = false;
    }
  });

  btnEnd.addEventListener('click', () => {
    client.stop();
  });

  btnMute.addEventListener('click', () => {
    const muted = client.toggleMute();
    btnMute.innerHTML = `${muteIcon(muted)} ${muted ? 'Unmute' : 'Mute'}`;
  });
}
