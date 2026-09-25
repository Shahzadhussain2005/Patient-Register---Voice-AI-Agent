import Vapi from '@vapi-ai/web';

/**
 * Thin wrapper around @vapi-ai/web.
 * Browser only: public key + assistant ID. Never use the private key here.
 */
export function createVoiceClient({ publicKey, assistantId, handlers = {} }) {
  if (!publicKey || publicKey.includes('your_vapi')) {
    throw new Error('Missing VITE_VAPI_PUBLIC_KEY. Copy frontend/.env.example to frontend/.env.');
  }
  if (!assistantId || assistantId.includes('your_assistant')) {
    throw new Error('Missing VITE_VAPI_ASSISTANT_ID. Use the assistant ID from the Vapi dashboard.');
  }

  const vapi = new Vapi(publicKey);
  let active = false;
  let muted = false;

  const on = (event, fn) => {
    if (typeof fn === 'function') vapi.on(event, fn);
  };

  on('call-start', () => {
    active = true;
    handlers.onCallStart?.();
  });

  on('call-end', () => {
    active = false;
    muted = false;
    handlers.onCallEnd?.();
  });

  on('speech-start', () => handlers.onSpeechStart?.());
  on('speech-end', () => handlers.onSpeechEnd?.());

  on('message', (message) => {
    if (message?.type === 'transcript' && message.transcriptType === 'final') {
      handlers.onTranscript?.({
        role: message.role === 'user' ? 'user' : 'assistant',
        text: message.transcript,
      });
    }
  });

  on('error', (error) => handlers.onError?.(error));

  return {
    start() {
      if (active) return;
      handlers.onConnecting?.();
      return vapi.start(assistantId);
    },
    stop() {
      if (!active) return;
      return vapi.stop();
    },
    setMuted(next) {
      muted = Boolean(next);
      vapi.setMuted(muted);
      return muted;
    },
    toggleMute() {
      return this.setMuted(!muted);
    },
    isActive: () => active,
    isMuted: () => muted,
  };
}
