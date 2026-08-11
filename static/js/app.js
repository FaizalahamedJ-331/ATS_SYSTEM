/* ==========================================================================
   TalentPulse ATS — front-end interactions
   ========================================================================== */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  /* --- CSRF helper ------------------------------------------------------ */
  function csrfToken() {
    const meta = $('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  /* --- Toasts ----------------------------------------------------------- */
  function toast(text, level) {
    const root = $("#toast-root");
    if (!root) return;
    const icons = { success: "✓", error: "✕", warning: "!", info: "i" };
    const el = document.createElement("div");
    el.className = `toast toast-${level || "info"}`;
    el.innerHTML = `<span class="toast-icon">${icons[level] || "i"}</span><span>${text}</span>`;
    root.appendChild(el);
    setTimeout(() => {
      el.classList.add("out");
      el.addEventListener("animationend", () => el.remove());
    }, 4200);
  }

  function bootstrapMessages() {
    const script = $("#django-messages");
    if (!script) return;
    try {
      const messages = JSON.parse(script.textContent);
      const map = { info: "info", success: "success", warning: "warning", error: "error" };
      messages.forEach((m) => {
        setTimeout(() => toast(m.text, map[m.level] || "info"), 120);
      });
    } catch (e) {
      /* ignore */
    }
  }

  /* --- Theme ------------------------------------------------------------ */
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("tp-theme", theme); } catch (e) { /* ignore */ }
  }

  function initTheme() {
    let saved = null;
    try { saved = localStorage.getItem("tp-theme"); } catch (e) { /* ignore */ }
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    applyTheme(saved || (prefersDark ? "dark" : "light"));
    const btn = $("#themeToggle");
    if (btn) {
      btn.addEventListener("click", () => {
        const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
        applyTheme(next);
        toast(next === "dark" ? "Dark mode enabled" : "Light mode enabled", "info");
      });
    }
  }

  /* --- Sidebar (mobile) ------------------------------------------------- */
  function initSidebar() {
    const btn = $("#sidebarToggle");
    const sidebar = $("#sidebar");
    if (!btn || !sidebar) return;
    btn.addEventListener("click", () => sidebar.classList.toggle("open"));
    document.addEventListener("click", (e) => {
      if (!sidebar.contains(e.target) && !btn.contains(e.target)) sidebar.classList.remove("open");
    });
  }

  /* --- Modals ----------------------------------------------------------- */
  function initModals() {
    $$("[data-modal-open]").forEach((trigger) => {
      trigger.addEventListener("click", () => {
        const target = document.getElementById(trigger.getAttribute("data-modal-open"));
        if (target) target.classList.add("open");
      });
    });
    $$("[data-modal-close]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const overlay = btn.closest(".modal-overlay");
        if (overlay) overlay.classList.remove("open");
      });
    });
    $$(".modal-overlay").forEach((overlay) => {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) overlay.classList.remove("open");
      });
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") $$(".modal-overlay.open").forEach((o) => o.classList.remove("open"));
    });
  }

  /* --- Charts ----------------------------------------------------------- */
  function chartColors() {
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    return {
      grid: dark ? "rgba(255,255,255,0.06)" : "rgba(23,26,43,0.06)",
      text: dark ? "#aab0cc" : "#8a8fa8",
      indigo: "#4f46e5",
      violet: "#7c3aed",
      green: "#10b981",
      amber: "#f59e0b",
      red: "#ef4444",
      blue: "#0ea5e9",
      cyan: "#06b6d4",
    };
  }

  function dataFrom(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  function initCharts() {
    if (typeof Chart === "undefined") return;
    const c = chartColors();
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.color = c.text;

    const make = (id, build) => {
      const canvas = document.getElementById(id);
      if (!canvas) return;
      const data = dataFrom("data-" + id);
      if (!data) return;
      const ctx = canvas.getContext("2d");
      new Chart(ctx, build(data, c, canvas));
    };

    make("chart-applications", (d, c2) => ({
      type: "bar",
      data: { labels: d.labels, datasets: [{ data: d.data, backgroundColor: c2.indigo, borderRadius: 8, maxBarThickness: 34 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false }, ticks: { maxRotation: 0 } }, y: { beginAtZero: true, grid: { color: c2.grid }, ticks: { precision: 0 } } } },
    }));

    make("chart-pipeline", (d, c2) => ({
      type: "bar",
      data: { labels: d.labels, datasets: [{ data: d.data, backgroundColor: ["#0ea5e9", "#f59e0b", "#8b5cf6", "#06b6d4", "#10b981", "#ef4444"], borderRadius: 8, maxBarThickness: 40 }] },
      options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true, grid: { color: c2.grid }, ticks: { precision: 0 } }, y: { grid: { display: false } } } },
    }));

    make("chart-scores", (d, c2) => ({
      type: "bar",
      data: { labels: d.labels, datasets: [{ data: d.data, backgroundColor: ["#ef4444", "#f59e0b", "#fbbf24", "#34d399", "#10b981"], borderRadius: 8, maxBarThickness: 40 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false } }, y: { beginAtZero: true, grid: { color: c2.grid }, ticks: { precision: 0 } } } },
    }));

    make("chart-timeline", (d, c2) => ({
      type: "line",
      data: { labels: d.labels, datasets: [{ data: d.data, borderColor: c2.indigo, backgroundColor: "rgba(79,70,229,0.12)", fill: true, tension: 0.42, pointRadius: 3, pointBackgroundColor: c2.indigo, borderWidth: 2.5 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false } }, y: { beginAtZero: true, grid: { color: c2.grid }, ticks: { precision: 0 } } } },
    }));

    make("chart-sources", (d, c2) => ({
      type: "doughnut",
      data: { labels: d.labels, datasets: [{ data: d.data, backgroundColor: [c2.indigo, c2.violet, c2.green, c2.amber, c2.blue, c2.red, c2.cyan], borderWidth: 0, hoverOffset: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: "68%", plugins: { legend: { position: "bottom", labels: { usePointStyle: true, pointStyle: "circle", boxWidth: 8, padding: 14 } } } },
    }));
  }

  /* --- Kanban drag & drop ----------------------------------------------- */
  function initKanban() {
    const cards = $$(".kanban-card[draggable='true']");
    const cols = $$(".kanban-cards");
    let dragged = null;

    cards.forEach((card) => {
      card.addEventListener("dragstart", () => {
        dragged = card;
        card.classList.add("dragging");
      });
      card.addEventListener("dragend", () => {
        card.classList.remove("dragging");
        cols.forEach((col) => col.classList.remove("drop-active"));
        dragged = null;
      });
    });

    cols.forEach((col) => {
      col.addEventListener("dragover", (e) => {
        e.preventDefault();
        col.classList.add("drop-active");
      });
      col.addEventListener("dragleave", () => col.classList.remove("drop-active"));
      col.addEventListener("drop", (e) => {
        e.preventDefault();
        col.classList.remove("drop-active");
        if (!dragged) return;
        const status = col.getAttribute("data-status");
        if (!status) return;
        col.appendChild(dragged);
        const appId = dragged.getAttribute("data-app-id");
        if (!appId) return;
        fetch(`/applications/${appId}/status/`, {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": csrfToken(),
          },
          body: `status=${encodeURIComponent(status)}`,
        })
          .then((r) => r.json())
          .then((res) => {
            if (res.ok) toast(`Moved to ${res.status_label}`, "success");
            else toast("Could not update stage", "error");
          })
          .catch(() => toast("Network error", "error"));
        updateColumnCounts();
      });
    });
  }

  function updateColumnCounts() {
    $$(".kanban-col").forEach((col) => {
      const count = col.querySelector(".count");
      const cards = col.querySelectorAll(".kanban-card").length;
      if (count) count.textContent = cards;
    });
  }

  /* --- Live table search ------------------------------------------------ */
  function initTableSearch() {
    const input = $("#tableSearch");
    if (!input) return;
    const rows = $$("table[data-searchable] tbody tr");
    input.addEventListener("input", () => {
      const q = input.value.toLowerCase();
      rows.forEach((row) => {
        row.style.display = row.textContent.toLowerCase().includes(q) ? "" : "none";
      });
    });
  }

  /* --- File drop styling ------------------------------------------------ */
  function initFileDrop() {
    $$(".file-drop").forEach((drop) => {
      const input = drop.querySelector("input[type='file']");
      if (!input) return;
      drop.addEventListener("click", () => input.click());
      drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("dragover"); });
      drop.addEventListener("dragleave", () => drop.classList.remove("dragover"));
      drop.addEventListener("drop", (e) => {
        e.preventDefault();
        drop.classList.remove("dragover");
        if (e.dataTransfer.files.length) input.files = e.dataTransfer.files;
      });
      input.addEventListener("change", () => {
        if (input.files.length) {
          drop.querySelector(".file-name").textContent = input.files[0].name;
          drop.classList.add("has-file");
        }
      });
    });
  }

  /* --- Kick off --------------------------------------------------------- */
  document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initSidebar();
    initModals();
    initCharts();
    initKanban();
    initTableSearch();
    initFileDrop();
    bootstrapMessages();
  });
})();
