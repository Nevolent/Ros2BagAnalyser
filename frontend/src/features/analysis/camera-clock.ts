interface CameraState {
  seekStarted: number;
  playStarted: number;
  playToken: number;
  pendingPlay: boolean;
  retryAfter: number;
}
const states = new WeakMap<HTMLVideoElement, CameraState>();
export function stopCamera(video: HTMLVideoElement) {
  video.pause();
  const state = states.get(video);
  if (state) {
    state.playToken++;
    state.pendingPlay = false;
  }
}
/** One bag-relative clock; each camera starts at its measured coverage offset. */
export function syncCamera(video: HTMLVideoElement, time: number, playing: boolean) {
  let state = states.get(video);
  if (!state) {
    state = { seekStarted: 0, playStarted: 0, playToken: 0, pendingPlay: false, retryAfter: 0 };
    states.set(video, state);
  }
  const start = Number(video.dataset.coverageStart ?? 0);
  const end = Number(video.dataset.coverageEnd ?? 0);
  const status = video.parentElement?.querySelector<HTMLElement>('[data-camera-state]');
  const message = (text: string) => {
    if (status) {
      status.textContent = text;
      status.hidden = !text;
    }
    video.style.visibility = text ? 'hidden' : 'visible';
  };
  if (video.error) {
    stopCamera(video);
    message('Camera could not be loaded.');
    return;
  }
  if (time < start || time > end) {
    stopCamera(video);
    message('Outside camera coverage.');
    return;
  }
  if (video.readyState < 1) {
    message('Loading camera…');
    return;
  }
  const now = performance.now();
  const desired = Math.max(
    0,
    Math.min(time - start, Number.isFinite(video.duration) ? video.duration : time - start),
  );
  const drift = Math.abs(video.currentTime - desired);
  // Coalesce seeks while the decoder is busy. A bounded timeout allows recovery.
  if (
    (!video.seeking || now - state.seekStarted > 1500) &&
    ((!playing && drift > 0.001) || (playing && video.readyState >= 2 && drift > 0.1))
  ) {
    state.seekStarted = now;
    video.currentTime = desired;
  }
  if (!playing) stopCamera(video);
  else if (
    video.paused &&
    !video.seeking &&
    video.readyState >= 2 &&
    now >= state.retryAfter &&
    (!state.pendingPlay || now - state.playStarted > 1500)
  ) {
    state.pendingPlay = true;
    state.playStarted = now;
    const token = ++state.playToken;
    const pending = state;
    void video
      .play()
      .catch(() => {
        if (pending.playToken === token) pending.retryAfter = performance.now() + 250;
      })
      .finally(() => {
        if (pending.playToken === token) pending.pendingPlay = false;
      });
  }
  message(video.readyState < 2 || video.seeking ? 'Loading camera…' : '');
}
