// Saarthi map layer — CARTO Positron tiles, crimson route with draw-in
// animation, custom pins, zoom + fit controls.
// Exposes window.SaarthiMap = { setPin, drawRoute, reset }

(function () {
  const LUCKNOW = [26.8467, 80.9462];

  const map = L.map('map', { zoomControl: false }).setView(LUCKNOW, 13);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    maxZoom: 19,
  }).addTo(map);

  L.control.zoom({ position: 'bottomright' }).addTo(map);

  let lastBounds = null;
  const FitControl = L.Control.extend({
    onAdd() {
      const btn = L.DomUtil.create('button', 'map-fit-btn');
      btn.innerHTML = '⌖';
      btn.title = 'Fit route';
      btn.setAttribute('aria-label', 'Fit route in view');
      L.DomEvent.on(btn, 'click', (event) => {
        L.DomEvent.stop(event);
        if (lastBounds) map.fitBounds(lastBounds, { padding: [70, 70] });
      });
      return btn;
    },
  });
  new FitControl({ position: 'bottomright' }).addTo(map);

  const pinIcon = (start) => L.divIcon({
    className: '',
    iconSize: [26, 26],
    iconAnchor: [13, 24],
    html: `<div class="pin-marker ${start ? 'pin-start' : ''}"><div class="pin-body"></div></div>`,
  });

  const pins = { from: null, to: null };
  let routeGroup = null;

  function setPin(kind, lat, lon, name) {
    if (pins[kind]) pins[kind].remove();
    pins[kind] = L.marker([lat, lon], { icon: pinIcon(kind === 'from') })
      .bindPopup(`<b>${kind === 'from' ? 'From' : 'To'}:</b> ${name}`)
      .addTo(map);

    if (pins.from && pins.to) {
      const bounds = L.latLngBounds(pins.from.getLatLng(), pins.to.getLatLng());
      lastBounds = bounds;
      map.fitBounds(bounds, { padding: [70, 70] });
    } else {
      map.setView([lat, lon], 14, { animate: true });
    }
  }

  // Animate an SVG polyline so the route "draws" itself along the path.
  function animateDraw(line, durationMs) {
    const path = line.getElement && line.getElement();
    if (!path || !path.getTotalLength) return;
    const length = path.getTotalLength();
    path.style.transition = 'none';
    path.style.strokeDasharray = `${length}`;
    path.style.strokeDashoffset = `${length}`;
    path.getBoundingClientRect(); // force reflow before transitioning
    path.style.transition = `stroke-dashoffset ${durationMs}ms ease-in-out`;
    path.style.strokeDashoffset = '0';
    setTimeout(() => { path.style.strokeDasharray = 'none'; }, durationMs + 120);
  }

  function drawRoute(origin, destination, route) {
    if (routeGroup) routeGroup.remove();
    const group = L.layerGroup();

    setPin('from', origin.lat, origin.lon, origin.name);
    setPin('to', destination.lat, destination.lon, destination.name);

    let bounds;
    if (route && route.points && route.points.length > 1) {
      const casing = L.polyline(route.points, { color: '#fff', weight: 10, opacity: 0.95 });
      casing.addTo(group);
      const line = L.polyline(route.points, { color: '#DC143C', weight: 5.5, opacity: 0.95 });
      line.addTo(group);
      bounds = line.getBounds();
      routeGroup = group.addTo(map);
      setTimeout(() => {
        animateDraw(casing, 1300);
        animateDraw(line, 1400);
      }, 250);
    } else {
      bounds = L.latLngBounds([origin.lat, origin.lon], [destination.lat, destination.lon]);
      routeGroup = group.addTo(map);
    }

    lastBounds = bounds;
    setTimeout(() => {
      map.invalidateSize();
      map.fitBounds(bounds, { padding: [70, 70] });
    }, 80);
  }

  function reset() {
    if (routeGroup) { routeGroup.remove(); routeGroup = null; }
    Object.keys(pins).forEach((kind) => {
      if (pins[kind]) { pins[kind].remove(); pins[kind] = null; }
    });
    lastBounds = null;
    map.setView(LUCKNOW, 13);
  }

  window.SaarthiMap = { setPin, drawRoute, reset };
})();
