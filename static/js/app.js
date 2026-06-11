// Saarthi frontend — stepper flow, autocomplete, SSE agent stream,
// animated verdict, and the Ask Saarthi chat.

(function () {
  const $ = (id) => document.getElementById(id);

  const state = {
    from: null,   // {name, address, lat, lon}
    to: null,
    mode: 'car',
    eventSource: null,
    countdownTimer: null,
  };

  // ---------- screen state machine ----------
  const SCREENS = ['state-loc', 'state-vehicle', 'state-time', 'state-progress', 'state-verdict'];
  function show(screenId) {
    SCREENS.forEach((id) => $(id).classList.toggle('show', id === screenId));
    $('panel').scrollTop = 0;
  }
  document.querySelectorAll('[data-back]').forEach((btn) =>
    btn.addEventListener('click', () => show(btn.dataset.back))
  );

  // ---------- mobile bottom sheet: drag + snap points ----------
  (function makeSheetDraggable() {
    const panel = $('panel');
    const grab = panel.querySelector('.grab');
    const isMobile = () => window.matchMedia('(max-width: 820px)').matches;
    const SNAPS = () => [0.28, 0.6, 0.88].map((f) => Math.round(window.innerHeight * f));

    let startY = 0;
    let startHeight = 0;

    grab.addEventListener('pointerdown', (e) => {
      if (!isMobile()) return;
      startY = e.clientY;
      startHeight = panel.getBoundingClientRect().height;
      panel.classList.add('dragging');
      grab.setPointerCapture(e.pointerId);
    });
    grab.addEventListener('pointermove', (e) => {
      if (!isMobile() || !panel.classList.contains('dragging')) return;
      const next = Math.min(window.innerHeight * 0.92,
        Math.max(110, startHeight + (startY - e.clientY)));
      panel.style.maxHeight = `${next}px`;
    });
    ['pointerup', 'pointercancel'].forEach((evt) =>
      grab.addEventListener(evt, () => {
        if (!isMobile() || !panel.classList.contains('dragging')) return;
        panel.classList.remove('dragging');
        panel.classList.add('snapping');
        const current = panel.getBoundingClientRect().height;
        const nearest = SNAPS().reduce((a, b) =>
          Math.abs(b - current) < Math.abs(a - current) ? b : a);
        panel.style.maxHeight = `${nearest}px`;
        setTimeout(() => panel.classList.remove('snapping'), 320);
      })
    );
  })();

  // ---------- arrive-by presets ----------
  function pad(n) { return String(n).padStart(2, '0'); }
  function toLocalValue(date) {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }
  function applyPreset(name) {
    const date = new Date();
    if (name === 'tomorrow930') { date.setDate(date.getDate() + 1); date.setHours(9, 30, 0, 0); }
    else if (name === 'plus2h') { date.setHours(date.getHours() + 2); date.setMinutes(Math.ceil(date.getMinutes() / 5) * 5, 0, 0); }
    else if (name === 'tonight7') {
      date.setHours(19, 0, 0, 0);
      if (date < new Date()) date.setDate(date.getDate() + 1); // 7 PM already passed
    }
    $('arrive-by').value = toLocalValue(date);
  }
  document.querySelectorAll('.preset').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.preset').forEach((b) => b.classList.remove('on'));
      btn.classList.add('on');
      applyPreset(btn.dataset.preset);
    });
  });
  applyPreset('tomorrow930');
  document.querySelector('[data-preset="tomorrow930"]').classList.add('on');
  $('arrive-by').addEventListener('input', () => {
    document.querySelectorAll('.preset').forEach((b) => b.classList.remove('on'));
  });

  // ---------- autocomplete (per-input, keyboard navigable) ----------
  function attachAutocomplete(input, box) {
    const kind = input.id === 'inp-from' ? 'from' : 'to';
    const row = input.closest('.loc-row');
    let debounce = null;
    let items = [];
    let hot = -1;

    function close() { box.innerHTML = ''; items = []; hot = -1; input.setAttribute('aria-expanded', 'false'); }

    function pick(item) {
      state[kind] = item;
      input.value = item.name;
      input.classList.add('ok');
      close();
      SaarthiMap.setPin(kind, item.lat, item.lon, item.name);
      $('btn-step1').disabled = !(state.from && state.to);
    }

    function highlight(index) {
      hot = index;
      box.querySelectorAll('.suggest-item').forEach((el, i) => el.classList.toggle('hot', i === hot));
    }

    function render() {
      box.innerHTML = '';
      items.forEach((item, index) => {
        const el = document.createElement('div');
        el.className = 'suggest-item';
        el.setAttribute('role', 'option');
        el.style.animationDelay = `${index * 35}ms`;
        el.innerHTML = `<i data-lucide="map-pin"></i>
          <div><div class="s-name"></div><div class="s-addr"></div></div>`;
        el.querySelector('.s-name').textContent = item.name;
        el.querySelector('.s-addr').textContent = item.address || '';
        el.addEventListener('mousedown', (e) => { e.preventDefault(); pick(item); });
        box.appendChild(el);
      });
      input.setAttribute('aria-expanded', items.length ? 'true' : 'false');
      lucide.createIcons();
    }

    input.addEventListener('input', () => {
      state[kind] = null;
      input.classList.remove('ok');
      $('btn-step1').disabled = true;
      clearTimeout(debounce);
      const query = input.value.trim();
      if (query.length < 2) { close(); row.classList.remove('loading'); return; }
      row.classList.add('loading');
      debounce = setTimeout(async () => {
        try {
          const response = await fetch(`/api/autocomplete?q=${encodeURIComponent(query)}`);
          const data = await response.json();
          items = data.suggestions || [];
          hot = -1;
          render();
        } catch { close(); }
        row.classList.remove('loading');
      }, 280);
    });

    input.addEventListener('keydown', (e) => {
      if (!items.length) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); highlight(Math.min(hot + 1, items.length - 1)); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); highlight(Math.max(hot - 1, 0)); }
      else if (e.key === 'Enter') { e.preventDefault(); pick(items[hot >= 0 ? hot : 0]); }
      else if (e.key === 'Escape') { close(); }
    });

    input.addEventListener('blur', () => setTimeout(close, 150));
  }
  attachAutocomplete($('inp-from'), $('suggest-from'));
  attachAutocomplete($('inp-to'), $('suggest-to'));

  // ---------- step 1 -> 2 ----------
  $('btn-step1').addEventListener('click', () => {
    if (!state.from || !state.to) return;
    $('route-sub').textContent = `${state.from.name} → ${state.to.name}`;
    show('state-vehicle');
  });

  // ---------- vehicle carousel (click + drag + wheel) ----------
  document.querySelectorAll('.v-card').forEach((card) => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.v-card').forEach((c) => c.classList.remove('active'));
      card.classList.add('active');
      state.mode = card.dataset.mode;
      card.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    });
  });
  (function makeDraggable(carousel) {
    let isDown = false, startX = 0, startScroll = 0, moved = false;
    carousel.addEventListener('pointerdown', (e) => {
      isDown = true; moved = false;
      startX = e.clientX; startScroll = carousel.scrollLeft;
    });
    carousel.addEventListener('pointermove', (e) => {
      if (!isDown) return;
      const dx = e.clientX - startX;
      if (Math.abs(dx) > 5) moved = true;
      carousel.scrollLeft = startScroll - dx;
    });
    ['pointerup', 'pointerleave'].forEach((evt) =>
      carousel.addEventListener(evt, () => { isDown = false; })
    );
    carousel.addEventListener('click', (e) => { if (moved) e.stopPropagation(); }, true);
    carousel.addEventListener('wheel', (e) => {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        e.preventDefault();
        carousel.scrollLeft += e.deltaY;
      }
    }, { passive: false });
  })($('v-carousel'));

  // ---------- step 2 -> 3 ----------
  const MODE_LABELS = { motorcycle: 'Bike', car: 'Car', taxi: 'Taxi', bus: 'Bus' };
  const MODE_ICONS = { motorcycle: 'bike', car: 'car-front', taxi: 'car-taxi-front', bus: 'bus-front' };

  $('btn-step2').addEventListener('click', () => {
    if (!state.from || !state.to) { show('state-loc'); return; }
    const chips = $('sum-chips');
    chips.innerHTML = '';
    [
      ['map-pin', state.from.name],
      ['flag', state.to.name],
      [MODE_ICONS[state.mode], MODE_LABELS[state.mode]],
    ].forEach(([icon, label]) => {
      const chip = document.createElement('span');
      chip.className = 'chip';
      chip.innerHTML = `<i data-lucide="${icon}"></i><span class="chip-label"></span>`;
      chip.querySelector('.chip-label').textContent = label;
      chips.appendChild(chip);
    });
    lucide.createIcons();
    show('state-time');
  });

  // ---------- analyze: SSE stream + cooking console ----------
  const TASK_ORDER = ['geocode', 'traffic', 'weather', 'festivals', 'events', 'advisories', 'verdict'];

  const COOK_LINES = [
    'Crunching live traffic on every route…',
    'Simulating parallel futures of your commute…',
    'Checking if rain wants to ruin your day…',
    'Sniffing out Bada Mangal bhandaras…',
    'Scanning Ekana for match-day chaos…',
    'Reading Lucknow Police’s mind…',
    'Teaching the AI about Lucknow traffic…',
    'Brewing your verdict…',
  ];
  let cookTimer = null;

  function startCooking() {
    let index = 0;
    clearInterval(cookTimer);
    $('cook-line').textContent = COOK_LINES[0];
    cookTimer = setInterval(() => {
      index = (index + 1) % COOK_LINES.length;
      const line = $('cook-line');
      line.style.opacity = 0;
      setTimeout(() => { line.textContent = COOK_LINES[index]; line.style.opacity = 1; }, 280);
    }, 2300);
  }
  function stopCooking() { clearInterval(cookTimer); cookTimer = null; }

  function updateCookBar() {
    const done = document.querySelectorAll('#task-list .task.done').length;
    $('cook-bar-fill').style.width = `${Math.round((done / TASK_ORDER.length) * 100)}%`;
  }

  function setTask(name, status, subText) {
    const task = document.querySelector(`[data-task="${name}"]`);
    if (!task) return;
    task.classList.remove('wait', 'busy', 'done');
    task.classList.add(status);
    if (subText) task.querySelector('.t-sub').textContent = subText;
    updateCookBar();
  }

  function resetTasks() {
    TASK_ORDER.forEach((name) => {
      const task = document.querySelector(`[data-task="${name}"]`);
      task.classList.remove('busy', 'done');
      task.classList.add('wait');
      task.querySelector('.t-sub').textContent = '';
    });
    setTask('geocode', 'busy');
    $('progress-error').innerHTML = '';
    $('cook-bar-fill').style.width = '4%';
    startCooking();
  }

  function advanceTasks(doneName, subText) {
    setTask(doneName, 'done', subText);
    const next = TASK_ORDER[TASK_ORDER.indexOf(doneName) + 1];
    if (next) setTask(next, 'busy');
  }

  function startAnalysis() {
    if (!$('arrive-by').value) return;
    if (!state.from || !state.to) { show('state-loc'); return; }
    if (state.eventSource) state.eventSource.close();

    resetTasks();
    show('state-progress');

    const params = new URLSearchParams({
      from: state.from.name,
      to: state.to.name,
      arrive_by: $('arrive-by').value,
      mode: state.mode,
      from_lat: state.from.lat, from_lon: state.from.lon,
      to_lat: state.to.lat, to_lon: state.to.lon,
    });

    const es = new EventSource(`/api/plan/stream?${params}`);
    state.eventSource = es;

    es.onmessage = (message) => {
      let data;
      try { data = JSON.parse(message.data); } catch { return; } // skip malformed frames
      if (data.type === 'tool_result') {
        advanceTasks(data.tool, data.summary);
      } else if (data.type === 'status' && (data.message || '').startsWith('Risk score')) {
        setTask('advisories', 'done');
        setTask('verdict', 'busy', data.message);
      } else if (data.type === 'verdict') {
        if (!data.data || !data.data.risk) {
          showError('Received an incomplete verdict — please try again.');
          return;
        }
        setTask('verdict', 'done');
        try {
          renderVerdict(data.data);
        } catch (renderError) {
          console.error('Verdict render failed:', renderError);
          showError('Could not display the verdict — please try again.');
        }
      } else if (data.type === 'error') {
        showError(data.message || 'Something went wrong — please try again.');
      } else if (data.type === 'done') {
        es.close(); state.eventSource = null;
      }
    };
    es.onerror = () => { showError('Connection lost — is the server running?'); };
  }

  $('btn-analyze').addEventListener('click', () => {
    if (!$('arrive-by').value) return;
    if (!state.from || !state.to) { show('state-loc'); return; }
    // button morphs into a loading state before the console takes over
    const analyzeBtn = $('btn-analyze');
    analyzeBtn.classList.add('loading');
    setTimeout(() => {
      analyzeBtn.classList.remove('loading');
      startAnalysis();
    }, 350);
  });

  $('btn-recheck').addEventListener('click', startAnalysis);

  function showError(text) {
    if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
    stopCooking();
    $('cook-line').textContent = 'Hit a snag.';
    const box = $('progress-error');
    box.innerHTML = `<div class="error-box"><i data-lucide="circle-alert"></i><span></span></div>
      <button class="btn-ghost" id="btn-err-back">← Try again</button>`;
    box.querySelector('span').textContent = text;
    lucide.createIcons();
    $('btn-err-back').addEventListener('click', () => show('state-loc'));
  }

  // ---------- verdict ----------
  const LEVEL_CLASS = { LOW: 'lv-low', MEDIUM: 'lv-med', HIGH: 'lv-high' };
  const LEVEL_GRADIENT = { LOW: 'url(#grad-low)', MEDIUM: 'url(#grad-medium)', HIGH: 'url(#grad-high)' };
  const FACTOR_ICONS = { car: 'car-front', rain: 'cloud-rain', temple: 'landmark', calendar: 'calendar', alert: 'siren' };
  const IMPACT_STYLE = { low: ['gray', 'lv-low', 'LOW'], medium: ['amber', 'lv-med', 'MED'], high: ['red', 'lv-high', 'HIGH'] };

  // weather factors get an icon matching the actual forecast
  function factorIcon(factor) {
    if (factor.type === 'weather' || factor.icon === 'rain') {
      const detail = (factor.detail || '').toLowerCase();
      if (detail.includes('thunder')) return 'cloud-lightning';
      if (detail.includes('drizzle')) return 'cloud-drizzle';
      if (detail.includes('fog')) return 'cloud-fog';
      if (detail.includes('no significant rain') || detail.includes('clear')) return 'sun';
      return 'cloud-rain';
    }
    return FACTOR_ICONS[factor.icon] || 'siren';
  }

  function countUp(el, target, durationMs) {
    const start = performance.now();
    function frame(now) {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = Math.round(target * eased);
      if (t < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  function renderVerdict(verdict) {
    stopCooking();
    show('state-verdict');

    // gauge — gradient stroke, arc sweep + score count-up in sync
    const score = verdict.risk.score;
    const level = verdict.risk.level;
    const arc = $('gauge-arc');
    arc.style.stroke = LEVEL_GRADIENT[level] || LEVEL_GRADIENT.MEDIUM;
    arc.style.strokeDashoffset = '270';
    requestAnimationFrame(() => {
      arc.style.strokeDashoffset = String(270 * (1 - score / 100));
    });
    countUp($('gauge-score'), score, 1000);
    const levelEl = $('gauge-level');
    levelEl.textContent = `${level} RISK`;
    levelEl.className = `gauge-level ${LEVEL_CLASS[level] || 'lv-med'}`;

    // leave-by block
    $('leave-time').textContent = verdict.recommended_departure || '--:--';
    $('leave-eta').textContent = verdict.eta
      ? `ETA ${verdict.eta} · deadline ${verdict.arrive_by}` : '';
    startCountdown(verdict);

    $('verdict-summary').textContent = verdict.summary || '';

    // factors — staggered entrance
    const factors = $('factors');
    factors.innerHTML = '';
    (verdict.factors || []).forEach((factor, index) => {
      const [iconBg, tagClass, tagText] = IMPACT_STYLE[factor.impact] || IMPACT_STYLE.low;
      const row = document.createElement('div');
      row.className = 'factor';
      row.style.animationDelay = `${index * 90}ms`;
      row.innerHTML = `
        <div class="f-icon ${iconBg}"><i data-lucide="${factorIcon(factor)}"></i></div>
        <div class="f-text"></div>
        <span class="f-tag ${tagClass}">${tagText}</span>`;
      row.querySelector('.f-text').textContent = factor.detail;
      factors.appendChild(row);
    });
    if (!factors.children.length) {
      factors.innerHTML = `<div class="factor">
        <div class="f-icon gray"><i data-lucide="circle-check"></i></div>
        <div class="f-text">No significant risk factors found — smooth ride expected.</div></div>`;
    }

    // departure curve — bars grow in with stagger
    const curve = $('curve');
    curve.innerHTML = '';
    const entries = verdict.departure_curve || [];
    const maxTravel = Math.max(...entries.map((entry) => entry.travel_min), 1);
    entries.forEach((entry, index) => {
      const isRec = entry.depart === verdict.recommended_departure;
      const color = entry.on_time
        ? (entry.margin_min >= 5 ? 'var(--green)' : 'var(--amber)')
        : 'var(--crimson)';
      const width = Math.max(8, Math.round((entry.travel_min / maxTravel) * 100));
      const label = entry.on_time
        ? `→ ${entry.eta}${isRec ? ' ★' : ` · ${Math.round(entry.travel_min)} min`}`
        : `→ ${entry.eta} · LATE`;
      const row = document.createElement('div');
      row.className = `curve-row${isRec ? ' rec' : ''}`;
      row.innerHTML = `
        <span class="c-dep">${entry.depart}</span>
        <span class="c-track"><span class="c-bar" style="--w:${width}%;background:${color}"></span></span>
        <span class="c-eta">${label}</span>`;
      curve.appendChild(row);
      setTimeout(() => row.classList.add('grown'), 150 + index * 120);
    });

    // tips
    const tips = $('tips');
    tips.innerHTML = '';
    (verdict.tips || []).forEach((tipText) => {
      const tip = document.createElement('div');
      tip.className = 'tip';
      tip.innerHTML = '<i data-lucide="lightbulb"></i><span></span>';
      tip.querySelector('span').textContent = tipText;
      tips.appendChild(tip);
    });

    $('provider-note').textContent = `Verdict synthesized by: ${verdict.llm_provider}`;

    // route context pill over the map
    if (verdict.origin && verdict.destination) {
      $('route-pill-text').textContent = `${verdict.origin.name} → ${verdict.destination.name}`;
      $('route-pill').classList.remove('hidden');
      SaarthiMap.drawRoute(verdict.origin, verdict.destination, verdict.route);
    }

    lucide.createIcons();
  }

  function startCountdown(verdict) {
    clearInterval(state.countdownTimer);
    const rec = (verdict.departure_curve || []).find(
      (entry) => entry.depart === verdict.recommended_departure
    );
    const countdownEl = $('countdown');
    if (!rec || !rec.depart_iso) { countdownEl.classList.add('hidden'); return; }

    function tick() {
      const minutes = Math.round((new Date(rec.depart_iso) - new Date()) / 60000);
      if (minutes <= 0) {
        $('countdown-text').textContent = 'leave now!';
      } else if (minutes < 90) {
        $('countdown-text').textContent = `in ${minutes} min`;
      } else {
        $('countdown-text').textContent = `in ${Math.floor(minutes / 60)}h ${minutes % 60}m`;
      }
      countdownEl.classList.remove('hidden');
    }
    tick();
    state.countdownTimer = setInterval(tick, 30000);
  }

  // ---------- restart ----------
  $('btn-restart').addEventListener('click', () => {
    clearInterval(state.countdownTimer);
    state.from = null; state.to = null;
    ['inp-from', 'inp-to'].forEach((id) => {
      $(id).value = ''; $(id).classList.remove('ok');
    });
    $('btn-step1').disabled = true;
    $('route-pill').classList.add('hidden');
    SaarthiMap.reset();
    show('state-loc');
  });

  // ==========================================================
  // ASK SAARTHI — chat with live tool streaming
  // ==========================================================
  const chat = { history: [], streaming: false, es: null };

  $('ask-open').addEventListener('click', () => {
    $('ask-modal').classList.remove('hidden');
    $('ask-input').focus();
  });
  $('ask-close').addEventListener('click', () => $('ask-modal').classList.add('hidden'));
  $('ask-modal').addEventListener('click', (event) => {
    if (event.target === $('ask-modal')) $('ask-modal').classList.add('hidden');
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') $('ask-modal').classList.add('hidden');
  });
  document.querySelectorAll('.suggest-chip').forEach((chip) =>
    chip.addEventListener('click', () => {
      $('ask-input').value = chip.textContent;
      sendChat();
    })
  );

  // minimal safe markdown: escape first, then **bold**, `code`, bullet lists
  function renderMarkdown(text) {
    const escaped = String(text)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const inline = escaped
      .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
    let html = '';
    let inList = false;
    inline.split('\n').forEach((line) => {
      const bullet = line.match(/^\s*[-*•]\s+(.*)/);
      if (bullet) {
        if (!inList) { html += '<ul>'; inList = true; }
        html += `<li>${bullet[1]}</li>`;
      } else {
        if (inList) { html += '</ul>'; inList = false; }
        if (line.trim()) html += `<p>${line}</p>`;
      }
    });
    if (inList) html += '</ul>';
    return html || '<p></p>';
  }

  const TOOL_LABELS = {
    geocode_place: 'finding the place',
    get_route: 'checking the route',
    compare_departures: 'simulating departures',
    get_weather: 'checking weather',
    get_festivals: 'checking festivals',
    get_events: 'checking events',
    get_police_advisories: 'checking advisories',
  };

  function addMessage(role, html) {
    $('chat-empty')?.remove();
    const msg = document.createElement('div');
    msg.className = `msg ${role}`;
    if (role === 'bot') {
      msg.innerHTML = `<span class="chat-avatar"><i data-lucide="sparkles"></i></span><div class="bubble">${html}</div>`;
    } else {
      msg.innerHTML = `<div class="bubble"></div>`;
      msg.querySelector('.bubble').textContent = html; // user text stays plain
    }
    $('chat-log').appendChild(msg);
    lucide.createIcons();
    $('chat-log').scrollTop = $('chat-log').scrollHeight;
    return msg;
  }

  function sendChat() {
    const input = $('ask-input');
    const question = input.value.trim();
    if (!question || chat.streaming) return;
    input.value = '';
    chat.streaming = true;
    $('ask-btn').disabled = true;

    addMessage('user', question);
    const working = addMessage('bot',
      `<div class="typing"><i></i><i></i><i></i></div><div class="tool-feed"></div>`);
    const bubble = working.querySelector('.bubble');
    const toolFeed = working.querySelector('.tool-feed');

    const params = new URLSearchParams({
      question,
      history: JSON.stringify(chat.history.slice(-8)),
    });
    const es = new EventSource(`/api/ask/stream?${params}`);
    chat.es = es;

    function finish() {
      es.close(); chat.es = null;
      chat.streaming = false;
      $('ask-btn').disabled = false;
    }

    es.onmessage = (message) => {
      let data;
      try { data = JSON.parse(message.data); } catch { return; }

      if (data.type === 'tool') {
        toolFeed.querySelectorAll('.tool-chip.running').forEach((c) => c.classList.remove('running'));
        const chipEl = document.createElement('span');
        chipEl.className = 'tool-chip running';
        chipEl.innerHTML = `<i data-lucide="loader-2"></i> ${TOOL_LABELS[data.name] || data.name}`;
        toolFeed.appendChild(chipEl);
        lucide.createIcons();
        $('chat-log').scrollTop = $('chat-log').scrollHeight;
      } else if (data.type === 'answer') {
        const toolsHtml = toolFeed.children.length
          ? `<div class="tool-feed">${toolFeed.innerHTML.replace(/running/g, '')}</div>` : '';
        const answerText = (data.text || '').trim()
          || 'Sorry, I could not get a complete answer. Please try again.';
        bubble.innerHTML = renderMarkdown(answerText) + toolsHtml +
          (data.provider ? `<div class="provider-tag">via ${data.provider}</div>` : '');
        lucide.createIcons();
        chat.history.push({ role: 'user', content: question });
        chat.history.push({ role: 'assistant', content: answerText });
        $('chat-log').scrollTop = $('chat-log').scrollHeight;
      } else if (data.type === 'error') {
        bubble.innerHTML = renderMarkdown(`Sorry — ${data.message || 'something went wrong.'}`);
        finish();
      } else if (data.type === 'done') {
        finish();
      }
    };
    es.onerror = () => {
      bubble.innerHTML = renderMarkdown('Connection lost — please try again.');
      finish();
    };
  }

  $('ask-btn').addEventListener('click', sendChat);
  $('ask-input').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') sendChat();
  });

  lucide.createIcons();
})();
