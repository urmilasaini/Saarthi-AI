// Saarthi AI splash — flight-path physics driver + timeline orchestration.
//
// The plane follows an SVG path (rise → wide loop → tight loop → dash to the
// navbar) with piecewise easing: ease-out on the rise, steady through the
// loops, hard ease-in acceleration on the exit. The crimson trail is the same
// path revealed by stroke-dashoffset, perfectly synced to the plane.

(function () {
  const splash = document.getElementById('splash');
  if (!splash) return;

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    splash.remove();
    return;
  }

  const flight = document.getElementById('flight');
  const trail = document.getElementById('trail');
  const plane = document.getElementById('plane');

  const totalLength = flight.getTotalLength();
  trail.style.strokeDasharray = `${totalLength}`;
  trail.style.strokeDashoffset = `${totalLength}`;

  // ---- piecewise distance mapping -------------------------------------
  // time fraction -> distance fraction, with per-segment easing
  const KEY_T = [0, 0.14, 0.52, 0.74, 1];        // timeline checkpoints
  const KEY_S = [0, 0.095, 0.492, 0.704, 1];     // arc-length checkpoints
  const easeOutQuad = (x) => 1 - (1 - x) * (1 - x);
  const easeInCubic = (x) => x * x * x;
  const linear = (x) => x;
  const SEG_EASE = [easeOutQuad, linear, linear, easeInCubic];

  function distanceAt(t) {
    for (let i = 0; i < KEY_T.length - 1; i++) {
      if (t <= KEY_T[i + 1]) {
        const local = (t - KEY_T[i]) / (KEY_T[i + 1] - KEY_T[i]);
        return KEY_S[i] + (KEY_S[i + 1] - KEY_S[i]) * SEG_EASE[i](local);
      }
    }
    return 1;
  }

  // ---- timeline (ms) ----------------------------------------------------
  const FLIGHT_START = 250;
  const FLIGHT_MS = 3550;     // flight ends ~3.8s
  const NET_AT = 2750;        // nodes + particles + connections
  const TEXT_AT = 3050;       // title reveal
  const LOGO_AT = 3800;       // plane -> navbar logo, trail -> route line
  const PULSE_AT = 4300;      // AI activation pulse
  const FADE_AT = 4800;       // splash fades over the home screen
  const REMOVE_AT = 5450;

  let rafId = null;
  let startTime = null;

  function frame(now) {
    if (startTime === null) startTime = now;
    const t = Math.min(1, (now - startTime) / FLIGHT_MS);
    const dist = distanceAt(t) * totalLength;

    const point = flight.getPointAtLength(dist);
    const ahead = flight.getPointAtLength(Math.min(totalLength, dist + 2));
    const angle = Math.atan2(ahead.y - point.y, ahead.x - point.x) * (180 / Math.PI);

    plane.setAttribute('transform', `translate(${point.x} ${point.y}) rotate(${angle})`);
    trail.style.strokeDashoffset = `${totalLength - dist}`;

    if (t < 1) rafId = requestAnimationFrame(frame);
  }

  const timers = [
    setTimeout(() => { rafId = requestAnimationFrame(frame); }, FLIGHT_START),
    setTimeout(() => splash.classList.add('phase-net'), NET_AT),
    setTimeout(() => splash.classList.add('phase-text'), TEXT_AT),
    setTimeout(() => splash.classList.add('phase-logo'), LOGO_AT),
    setTimeout(() => splash.classList.add('phase-pulse'), PULSE_AT),
    setTimeout(() => splash.classList.add('phase-out'), FADE_AT),
    setTimeout(dismiss, REMOVE_AT),
  ];

  function dismiss() {
    timers.forEach(clearTimeout);
    if (rafId) cancelAnimationFrame(rafId);
    splash.remove();
  }

  // click anywhere (or the Skip pill) ends the show early
  splash.addEventListener('click', () => {
    splash.classList.add('phase-out');
    setTimeout(dismiss, 380);
  });

  // scatter floating AI particles
  const PARTICLE_SPOTS = [
    [12, 22], [22, 70], [38, 14], [62, 80], [74, 18], [86, 58], [90, 32], [8, 48],
  ];
  PARTICLE_SPOTS.forEach(([x, y], index) => {
    const dot = document.createElement('span');
    dot.className = 'splash-particle';
    dot.style.left = `${x}%`;
    dot.style.top = `${y}%`;
    dot.style.setProperty('--pd', `${index * 0.28}s`);
    splash.appendChild(dot);
  });
})();
