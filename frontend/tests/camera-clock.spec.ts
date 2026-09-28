import { test, expect, type Page } from '@playwright/test';

// A controllable decoder makes races reproducible, independent of machine speed.
async function decoder(page: Page, delay: number | null) {
  await page.clock.install({ time: new Date('2026-09-28T12:00:00Z') });
  await page.clock.pauseAt(new Date('2026-09-28T12:00:00Z'));
  await page.goto('/?demo=1#/analysis');
  await page.evaluate(async (delay) => {
    const module = '/src/features/analysis/camera-clock.ts';
    const { syncCamera, stopCamera } = await import(/* @vite-ignore */ module);
    const pane = document.createElement('section');
    pane.innerHTML = '<video></video><p data-camera-state>Loading camera…</p>';
    document.body.append(pane);
    const video = pane.querySelector('video')!;
    video.dataset.coverageStart = '0';
    video.dataset.coverageEnd = '60';
    let position = 0;
    let since = performance.now();
    let paused = true;
    let seeking = false;
    const audit = {
      time: 0,
      playing: false,
      revision: 0,
      seeks: [] as number[],
      plays: 0,
      stalls: 0,
      mutations: 0,
      sync: () => syncCamera(video, audit.time, audit.playing, audit.revision),
      stop: () => stopCamera(video),
      video,
    };
    Object.defineProperties(video, {
      duration: { value: 60 },
      readyState: { get: () => (seeking ? 1 : 4) },
      seeking: { get: () => seeking },
      paused: { get: () => paused },
      currentTime: {
        get: () => position + (!paused && !seeking ? (performance.now() - since) / 1000 : 0),
        set: (value: number) => {
          audit.seeks.push(value);
          position = value;
          since = performance.now();
          seeking = true;
          if (delay !== null)
            setTimeout(() => {
              seeking = false;
              since = performance.now();
              video.dispatchEvent(new Event('seeked'));
            }, delay);
        },
      },
    });
    video.pause = () => {
      position = video.currentTime;
      paused = true;
    };
    video.play = () => {
      audit.plays++;
      paused = false;
      since = performance.now();
      return Promise.resolve();
    };
    video.addEventListener('seeked', audit.sync);
    video.addEventListener('camera-stalled', () => audit.stalls++);
    const observer = new MutationObserver((records) => (audit.mutations += records.length));
    observer.observe(pane, {
      subtree: true,
      childList: true,
      attributes: true,
      characterData: true,
    });
    (window as any).decoder = audit;
    audit.sync();
  }, delay);
}

test('busy decoder finishes one seek then goes directly to the latest scrub position', async ({
  page,
}) => {
  await decoder(page, 250);
  await page.evaluate(() => {
    const d = (window as any).decoder;
    for (const time of [10, 40, 5, 35, 20]) {
      d.time = time;
      d.revision++;
      d.sync();
    }
  });
  expect(await page.evaluate(() => (window as any).decoder.seeks)).toEqual([10]);
  await page.clock.runFor(600);
  expect(await page.evaluate(() => (window as any).decoder.seeks)).toEqual([10, 20]);
  expect(await page.evaluate(() => (window as any).decoder.video.currentTime)).toBe(20);
});

test('slow seeks give playback a chance to resume instead of endlessly chasing the clock', async ({
  page,
}) => {
  await decoder(page, 250);
  await page.evaluate(() => {
    const d = (window as any).decoder;
    d.time = 10;
    d.playing = true;
    d.revision++;
    const start = performance.now();
    const tick = () => {
      d.time = 10 + (performance.now() - start) / 1000;
      d.sync();
      requestAnimationFrame(tick);
    };
    tick();
  });
  await page.clock.runFor(2000);
  expect(await page.evaluate(() => (window as any).decoder.plays)).toBeGreaterThan(0);
  expect(await page.evaluate(() => (window as any).decoder.seeks.length)).toBeLessThan(5);
});

test('a paused seek that never completes requests recovery without another interaction', async ({
  page,
}) => {
  await decoder(page, null);
  await page.evaluate(() => {
    const d = (window as any).decoder;
    d.time = 20;
    d.sync();
  });
  await page.clock.runFor(9000);
  expect(await page.evaluate(() => (window as any).decoder.stalls)).toBe(1);
  expect(await page.evaluate(() => (window as any).decoder.seeks)).toEqual([20]);
  await page.clock.runFor(10000);
  expect(await page.evaluate(() => (window as any).decoder.stalls)).toBe(1);
});

test('unchanged camera status causes no DOM mutations during clock updates', async ({ page }) => {
  await decoder(page, 0);
  await page.evaluate(() => {
    const d = (window as any).decoder;
    d.mutations = 0;
    for (let i = 0; i < 100; i++) d.sync();
  });
  expect(await page.evaluate(() => (window as any).decoder.mutations)).toBe(0);
});

test('leaving analysis cancels a stalled decoder watchdog', async ({ page }) => {
  await decoder(page, null);
  await page.evaluate(() => {
    const d = (window as any).decoder;
    d.time = 20;
    d.sync();
    d.stop();
  });
  await page.clock.runFor(9000);
  expect(await page.evaluate(() => (window as any).decoder.stalls)).toBe(0);
});

test('resuming after a long pause starts a fresh recovery deadline', async ({ page }) => {
  await decoder(page, null);
  await page.clock.runFor(60000);
  await page.evaluate(() => {
    const d = (window as any).decoder;
    d.time = 20;
    d.sync();
  });
  await page.clock.runFor(7000);
  expect(await page.evaluate(() => (window as any).decoder.stalls)).toBe(0);
  await page.clock.runFor(2000);
  expect(await page.evaluate(() => (window as any).decoder.stalls)).toBe(1);
});

test('small clock steps at high refresh rates count as playback progress', async ({ page }) => {
  await decoder(page, 0);
  await page.evaluate(() => {
    const d = (window as any).decoder;
    d.playing = true;
    const start = performance.now();
    setInterval(() => {
      d.time = (performance.now() - start) / 1000;
      d.sync();
    }, 5);
    d.sync();
  });
  await page.clock.runFor(12000);
  expect(await page.evaluate(() => (window as any).decoder.stalls)).toBe(0);
  expect(await page.evaluate(() => (window as any).decoder.video.currentTime)).toBeGreaterThan(11);
  expect(await page.evaluate(() => (window as any).decoder.seeks)).toEqual([]);
});

test('an explicit seek bypasses drift cooldown and stale play promises cannot block resume', async ({
  page,
}) => {
  await decoder(page, 100);
  await page.evaluate(() => {
    const d = (window as any).decoder;
    d.video.play = () =>
      new Promise((_, reject) => {
        d.rejectPlay = reject;
      });
    d.time = 10;
    d.playing = true;
    d.sync();
  });
  await page.clock.runFor(100);
  await page.evaluate(() => {
    const d = (window as any).decoder;
    d.playing = false;
    d.sync();
    d.playing = true;
    d.time = 30;
    d.revision++;
    d.sync();
    d.rejectPlay(new DOMException('Interrupted by a seek', 'AbortError'));
    d.video.play = () => {
      d.plays++;
      return Promise.resolve();
    };
  });
  await page.clock.runFor(100);
  expect(await page.evaluate(() => (window as any).decoder.seeks)).toEqual([10, 30]);
  expect(await page.evaluate(() => (window as any).decoder.plays)).toBe(1);
});
