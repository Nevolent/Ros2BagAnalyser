interface CameraState {
  seekTarget: number | null;
  seekVersion: number;
  userSeek: boolean;
  correctAfter: number;
  playToken: number;
  pendingPlay: boolean;
  retryAfter: number;
  hasFrame: boolean;
  lastTime: number;
  progressAt: number;
  recovering: boolean;
  timer?: ReturnType<typeof setTimeout>;
  clock: { time: number; playing: boolean; seekVersion: number };
}
const states = new WeakMap<HTMLVideoElement, CameraState>();
const stallTimeout = 8000;

function pause(video: HTMLVideoElement, state: CameraState) {
  if (!video.paused || state.pendingPlay) video.pause();
  if (state.pendingPlay) {
    state.playToken++;
    state.pendingPlay = false;
  }
}

/** Cancel recovery and invalidate outstanding play promises on reload or unmount. */
export function stopCamera(video: HTMLVideoElement) {
  const state = states.get(video);
  if (state) {
    clearTimeout(state.timer);
    pause(video, state);
    states.delete(video);
  } else if (!video.paused) video.pause();
}

/** One bag-relative clock; each camera starts at its measured coverage offset. */
export function syncCamera(
  video: HTMLVideoElement,
  time: number,
  playing: boolean,
  seekVersion = 0,
) {
  const now = performance.now();
  let state = states.get(video);
  if (!state) {
    state = {
      seekTarget: null,
      seekVersion,
      userSeek: false,
      correctAfter: 0,
      playToken: 0,
      pendingPlay: false,
      retryAfter: 0,
      hasFrame: false,
      lastTime: video.currentTime,
      progressAt: now,
      recovering: false,
      clock: { time, playing, seekVersion },
    };
    states.set(video, state);
  }
  state.clock = { time, playing, seekVersion };
  if (seekVersion !== state.seekVersion) {
    state.seekVersion = seekVersion;
    state.userSeek = true;
  }
  const status = video.parentElement?.querySelector<HTMLElement>('[data-camera-state]');
  const message = (text: string, hideVideo = !!text) => {
    // Assigning textContent even to the same string replaces its DOM text node.
    if (status) {
      if (status.textContent !== text) status.textContent = text;
      if (status.hidden !== !text) status.hidden = !text;
    }
    const visibility = hideVideo ? 'hidden' : 'visible';
    if (video.style.visibility !== visibility) video.style.visibility = visibility;
  };
  const stopWatch = () => {
    clearTimeout(state.timer);
    state.timer = undefined;
    state.progressAt = now;
  };
  if (video.error || state.recovering) {
    stopWatch();
    pause(video, state);
    message(
      video.dataset.failed === 'true'
        ? 'Camera could not be loaded.'
        : state.hasFrame
          ? ''
          : 'Loading camera…',
      video.dataset.failed === 'true' || !state.hasFrame,
    );
    return;
  }
  const start = Number(video.dataset.coverageStart ?? 0);
  const end = Number(video.dataset.coverageEnd ?? 0);
  if (time < start || time > end) {
    stopWatch();
    pause(video, state);
    message('Outside camera coverage.');
    return;
  }
  if (!playing) pause(video, state);
  if (video.readyState === 0) state.hasFrame = false;
  if (video.readyState >= 2) {
    if (!state.hasFrame) state.progressAt = now;
    state.hasFrame = true;
    if (!video.seeking) {
      if (state.seekTarget !== null) {
        state.seekTarget = null;
        state.progressAt = now;
        state.lastTime = video.currentTime;
        // A slow seek must get a chance to play before correcting drift again.
        state.correctAfter = now + 500;
      } else if (!video.paused && Math.abs(video.currentTime - state.lastTime) > 0.01) {
        state.progressAt = now;
        state.lastTime = video.currentTime;
      }
    }
  }
  const desired = Math.max(
    0,
    Math.min(time - start, Number.isFinite(video.duration) ? video.duration : time - start),
  );
  const drift = Math.abs(video.currentTime - desired);
  // Never interrupt an in-flight decode. Events drain the latest clock position,
  // and the watchdog handles a decoder that stops emitting events, even paused.
  if (
    video.readyState >= 1 &&
    !video.seeking &&
    (state.userSeek || !playing || (!state.pendingPlay && now >= state.correctAfter)) &&
    drift > (playing && !state.userSeek ? 0.1 : 0.001)
  ) {
    state.seekTarget = desired;
    state.userSeek = false;
    video.currentTime = desired;
    state.lastTime = desired;
  } else if (!video.seeking && drift <= 0.001) state.userSeek = false;
  if (
    playing &&
    video.paused &&
    !video.seeking &&
    !video.ended &&
    video.readyState >= 2 &&
    now >= state.retryAfter &&
    !state.pendingPlay
  ) {
    state.pendingPlay = true;
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
  message(state.hasFrame ? '' : 'Loading camera…');
  const needsProgress =
    !state.hasFrame ||
    video.seeking ||
    state.seekTarget !== null ||
    state.pendingPlay ||
    (playing && !video.ended) ||
    drift > (playing ? 0.1 : 0.001);
  if (!needsProgress) stopWatch();
  else if (state.timer === undefined) {
    const watched = state;
    watched.progressAt = now;
    const check = () => {
      watched.timer = setTimeout(check, 1000);
      const clock = watched.clock;
      syncCamera(video, clock.time, clock.playing, clock.seekVersion);
      if (watched.timer !== undefined && performance.now() - watched.progressAt >= stallTimeout) {
        clearTimeout(watched.timer);
        watched.timer = undefined;
        watched.recovering = true;
        pause(video, watched);
        // Share the camera component's bounded retries and explicit Retry UI.
        video.dispatchEvent(new Event('camera-stalled'));
      }
    };
    watched.timer = setTimeout(check, 1000);
  }
}
