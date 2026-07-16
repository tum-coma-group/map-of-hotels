// Static hotel map. Reads window.HOTELS (from hotels.js), plots clustered
// markers on a Leaflet/OpenStreetMap map, and renders a searchable sidebar.
// No login, no uploads, no backend.

const $ = (id) => document.getElementById(id);
const el = {
  searchInput: $("search-input"),
  hotelList: $("hotel-list"),
  hotelCount: $("hotel-count"),
  map: $("map"),
};

// Detail fields shown in the popup, in order. [key, label].
const FIELD_LABELS = [
  ["adresse", "Adresse"],
  ["plz", "PLZ"],
  ["stadt", "Stadt"],
  ["email", "E-Mail"],
  ["telefon", "Telefon"],
  ["ez", "EZ (inkl. Frühstück)"],
  ["dz", "DZ (inkl. Frühstück)"],
  ["stornierung", "Stornierung bis"],
  ["buchungscode", "Buchungscode"],
  ["gueltig_bis", "Rate gültig bis"],
  ["bemerkung", "Bemerkung"],
  ["nachhaltigkeit", "Nachhaltigkeits-Zertifikat"],
];

// Sort by city, then hotel name (German locale for umlauts).
const hotels = (window.HOTELS || [])
  .slice()
  .sort((a, b) =>
    (a.stadt || "").localeCompare(b.stadt || "", "de") ||
    (a.hotel || "").localeCompare(b.hotel || "", "de")
  );

let map = null;
let clusterGroup = null;
const markers = []; // index-aligned with `hotels`

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function isPrice(v) {
  return /^\d+([.,]\d+)?$/.test(String(v).trim());
}

function popupHtml(hotel) {
  const rows = FIELD_LABELS.filter(([key]) => hotel[key])
    .map(([key, label]) => {
      const raw = String(hotel[key]);
      let value = escapeHtml(raw);
      if (key === "email") {
        value = `<a href="mailto:${escapeHtml(raw)}">${escapeHtml(raw)}</a>`;
      } else if (key === "telefon") {
        const tel = raw.replace(/[^\d+]/g, "");
        value = `<a href="tel:${escapeHtml(tel)}">${escapeHtml(raw)}</a>`;
      } else if ((key === "ez" || key === "dz") && isPrice(raw)) {
        value = escapeHtml(raw) + " €";
      }
      return `<div class="iw-row"><span class="iw-key">${escapeHtml(label)}</span>${value}</div>`;
    })
    .join("");
  return `<div class="iw"><div class="iw-name">${escapeHtml(hotel.hotel)}</div>${rows}</div>`;
}

function initMap() {
  map = L.map(el.map, { scrollWheelZoom: true }).setView([51.0, 10.0], 6);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  clusterGroup = L.markerClusterGroup({ showCoverageOnHover: false });

  hotels.forEach((hotel, idx) => {
    const marker = L.marker([hotel.lat, hotel.lng], { title: hotel.hotel });
    marker.bindPopup(popupHtml(hotel), { maxWidth: 320 });
    marker.on("click", () => setActive(idx));
    markers[idx] = marker;
    clusterGroup.addLayer(marker);
  });

  map.addLayer(clusterGroup);
  if (markers.length) {
    map.fitBounds(clusterGroup.getBounds(), { padding: [40, 40] });
  }
}

function buildSidebar() {
  el.hotelList.innerHTML = "";
  const frag = document.createDocumentFragment();
  hotels.forEach((h, idx) => {
    const li = document.createElement("li");
    li.className = "hotel-item";
    li.dataset.idx = String(idx);
    li.innerHTML = `<div class="name"></div><div class="addr"></div>`;
    li.querySelector(".name").textContent = h.hotel;
    li.querySelector(".addr").textContent = `${h.stadt} · ${h.adresse}`;
    li.addEventListener("click", () => focusHotel(idx));
    frag.appendChild(li);
  });
  el.hotelList.appendChild(frag);
}

function focusHotel(idx) {
  const hotel = hotels[idx];
  const marker = markers[idx];
  if (!hotel || !marker) return;
  setActive(idx);
  map.flyTo([hotel.lat, hotel.lng], Math.max(map.getZoom(), 14), { duration: 0.5 });
  // Open the popup once the cluster has expanded to reveal the marker.
  clusterGroup.zoomToShowLayer(marker, () => marker.openPopup());
}

function setActive(idx) {
  for (const li of el.hotelList.querySelectorAll(".hotel-item")) {
    const active = Number(li.dataset.idx) === idx;
    li.classList.toggle("active", active);
    if (active) li.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function applyFilter() {
  const q = el.searchInput.value.trim().toLowerCase();
  let shown = 0;
  clusterGroup.clearLayers();
  const visibleMarkers = [];

  hotels.forEach((h, idx) => {
    const match =
      !q ||
      Object.values(h).some(
        (v) => v != null && String(v).toLowerCase().includes(q)
      );
    const li = el.hotelList.querySelector(`.hotel-item[data-idx="${idx}"]`);
    if (li) li.classList.toggle("hidden", !match);
    if (match) {
      shown++;
      visibleMarkers.push(markers[idx]);
    }
  });

  clusterGroup.addLayers(visibleMarkers);
  el.hotelCount.textContent = q
    ? `${shown} von ${hotels.length} Hotels`
    : `${hotels.length} Hotels`;
}

function init() {
  if (!hotels.length) {
    el.hotelCount.textContent = "Keine Hoteldaten geladen.";
    return;
  }
  initMap();
  buildSidebar();
  applyFilter();
  el.searchInput.addEventListener("input", applyFilter);
}

init();
