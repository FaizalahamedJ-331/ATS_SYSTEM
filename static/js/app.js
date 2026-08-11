/* ==========================================================================
   TalentPulse ATS — front-end interactions
   ========================================================================== */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  /* --- Escape user content for safe innerHTML --------------------------- */
  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

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
        // A "hired" tag means the server just marked someone hired (from any
        // redirect path) — the message text carries the candidate's name.
        if ((m.level || "").split(" ").includes("hired")) {
          document.dispatchEvent(new CustomEvent("candidate-hired", { detail: m.text }));
          return;
        }
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

    make("chart-radar", (d, c2) => ({
      type: "radar",
      data: {
        labels: d.labels,
        datasets: [{
          data: d.data,
          backgroundColor: "rgba(79,70,229,0.18)",
          borderColor: c2.indigo,
          borderWidth: 2.5,
          pointBackgroundColor: c2.indigo,
          pointRadius: 4,
          pointHoverRadius: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          r: {
            beginAtZero: true,
            max: 100,
            ticks: { stepSize: 25, color: c2.text, backdropColor: "transparent", font: { size: 10 } },
            grid: { color: c2.grid },
            angleLines: { color: c2.grid },
            pointLabels: { color: c2.text, font: { size: 11, weight: "600" } },
          },
        },
      },
    }));

    make("chart-sources", (d, c2) => ({
      type: "doughnut",
      data: { labels: d.labels, datasets: [{ data: d.data, backgroundColor: [c2.indigo, c2.violet, c2.green, c2.amber, c2.blue, c2.red, c2.cyan], borderWidth: 0, hoverOffset: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: "68%", plugins: { legend: { position: "bottom", labels: { usePointStyle: true, pointStyle: "circle", boxWidth: 8, padding: 14 } } } },
    }));
  }

  /* --- Confetti celebration (dependency-free) ----------------------------- */
  let confettiRaf = null;
  function confettiBurst() {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    // Kill any in-flight burst first so two rapid hires can't double-draw
    cancelAnimationFrame(confettiRaf);
    const old = document.getElementById("confettiCanvas");
    if (old) old.remove();

    const canvas = document.createElement("canvas");
    canvas.id = "confettiCanvas";
    canvas.setAttribute("aria-hidden", "true");
    document.body.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    canvas.style.width = window.innerWidth + "px";
    canvas.style.height = window.innerHeight + "px";

    const COLORS = ["#4f46e5", "#7c3aed", "#10b981", "#f59e0b", "#0ea5e9", "#ef4444", "#06b6d4"];
    const pieces = Array.from({ length: 160 }, () => ({
      x: window.innerWidth / 2 + (Math.random() - 0.5) * 160,
      y: window.innerHeight * 0.32 + (Math.random() - 0.5) * 120,
      vx: (Math.random() - 0.5) * 13,
      vy: -Math.random() * 13 - 4,
      size: 6 + Math.random() * 6,
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
      rotation: Math.random() * Math.PI * 2,
      spin: (Math.random() - 0.5) * 0.25,
      shape: Math.random() > 0.5 ? "rect" : "circle",
      flutter: Math.random() * 0.04 + 0.01,
      phase: Math.random() * Math.PI * 2,
      life: 1,
    }));

    const gravity = 0.24;
    const friction = 0.985;

    function frame() {
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      let alive = false;
      pieces.forEach((p) => {
        p.vy += gravity;
        p.vx *= friction;
        p.x += p.vx + Math.sin(Date.now() * 0.004 + p.phase) * 1.6;
        p.y += p.vy;
        p.rotation += p.spin;
        p.life -= 0.0045;
        if (p.life <= 0 || p.y > window.innerHeight + 30) return;
        alive = true;

        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rotation);
        ctx.globalAlpha = Math.max(0, Math.min(1, p.life));
        ctx.fillStyle = p.color;
        if (p.shape === "rect") {
          ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
        } else {
          ctx.beginPath();
          ctx.arc(0, 0, p.size / 2.4, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
      });
      if (alive) {
        confettiRaf = requestAnimationFrame(frame);
      } else {
        ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
        canvas.remove();
        confettiRaf = null;
      }
    }
    confettiRaf = requestAnimationFrame(frame);
  }

  function celebrateHire(candidateName) {
    confettiBurst();
    toast(`🎉 ${candidateName} was hired — congratulations!`, "success");
  }

  /* Central hire event: any code path that confirms a hire (kanban drag,
     "Mark as hired" button, redirect with a hired-tagged message) dispatches
     this, and the single listener below fires the celebration. */
  function initHireCelebration() {
    document.addEventListener("candidate-hired", (e) => {
      celebrateHire(e.detail || "Candidate");
    });
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
            if (res.ok) {
              if (res.hired) {
                const nameEl = dragged.querySelector(".kc-name");
                document.dispatchEvent(new CustomEvent("candidate-hired", {
                  detail: nameEl ? nameEl.textContent.trim() : "Candidate",
                }));
              } else {
                toast(`Moved to ${res.status_label}`, "success");
              }
            } else {
              toast("Could not update stage", "error");
            }
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

  /* --- Animated counters ------------------------------------------------ */
  function initCounters() {
    const els = $$("[data-count]");
    if (!els.length) return;
    const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const animate = (el) => {
      const target = parseFloat(el.getAttribute("data-count"));
      const decimals = parseInt(el.getAttribute("data-decimals") || "0", 10);
      if (!Number.isFinite(target)) return;
      el.textContent = "0";
      const duration = 900;
      const start = performance.now();
      function frame(now) {
        const p = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - p, 3);
        el.textContent = (target * eased).toFixed(decimals);
        if (p < 1) requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    };
    if (reduce) {
      els.forEach((el) => {
        const target = parseFloat(el.getAttribute("data-count"));
        if (Number.isFinite(target)) {
          el.textContent = target.toFixed(parseInt(el.getAttribute("data-decimals") || "0", 10));
        }
      });
      return;
    }
    els.forEach(animate);
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

  /* --- Navigation progress bar ------------------------------------------- */
  const progress = $("#navProgress");
  let progressTimer = null;
  function startProgress() {
    if (!progress) return;
    progress.classList.add("show");
    progress.style.width = "0%";
    requestAnimationFrame(() => { progress.style.width = "78%"; });
  }
  function finishProgress() {
    if (!progress) return;
    progress.style.width = "100%";
    clearTimeout(progressTimer);
    progressTimer = setTimeout(() => {
      progress.classList.remove("show");
      progress.style.width = "0%";
    }, 350);
  }
  function initNavProgress() {
    const isInternal = (a) => {
      const href = a.getAttribute("href") || "";
      if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("javascript:")) return false;
      if (a.target === "_blank") return false;
      if (a.closest("form")) return false;
      if (a.getAttribute("download") != null) return false;
      if (a.hasAttribute("data-modal-open")) return false;
      try {
        return new URL(a.href, location.href).origin === location.origin;
      } catch (err) {
        return false;
      }
    };

    document.addEventListener("click", (e) => {
      const a = e.target.closest ? e.target.closest("a[href]") : null;
      if (!a || !isInternal(a)) return;
      const url = new URL(a.href, location.href);
      if (url.pathname === location.pathname && url.search === location.search) return;

      // Same-origin navigation: wrap in the View Transitions API when available
      // so the browser cross-fades between pages (graceful fallback otherwise).
      if (document.startViewTransition && !e.defaultPrevented && e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) {
        e.preventDefault();
        startProgress();
        document.startViewTransition(() => {
          window.location.href = a.href;
        });
      } else {
        startProgress();
      }
    });

    // Hide on back/forward cache restore
    window.addEventListener("pageshow", (e) => {
      if (e.persisted) finishProgress();
    });
  }

  /* --- Command palette (⌘K) ---------------------------------------------- */
  function initPalette() {
    const overlay = $("#palette");
    const input = $("#paletteInput");
    const results = $("#paletteResults");
    const trigger = $("#cmdTrigger");
    if (!overlay || !input || !results) return;

    let items = [];
    let active = -1;
    let fetchTimer = null;
    let controller = null;

    const open = () => {
      overlay.hidden = false;
      input.value = "";
      abortSearch();
      setTimeout(() => input.focus(), 30);
      search("");
    };
    const close = () => {
      overlay.hidden = true;
      if (controller) controller.abort();
      if (trigger) trigger.focus();
    };

    const abortSearch = () => {
      if (controller) {
        controller.abort();
        controller = null;
      }
      results.innerHTML = "";
      items = [];
      active = -1;
    };

    function render() {
      if (!items.length) {
        results.innerHTML = `<div class="palette-empty">No results for “${escapeHtml(input.value.trim())}”</div>`;
        active = -1;
        return;
      }
      results.innerHTML = items
        .map(
          (it, i) =>
            `<div class="palette-item ${i === active ? "active" : ""}" data-index="${i}">
              <span class="palette-ic ${it.meta}">${it.meta === "candidate" ? escapeHtml(it.initials || "C") : it.meta === "job" ? "J" : it.meta === "action" ? "→" : ""}</span>
              <span class="palette-label">${escapeHtml(it.label)}</span>
              <span class="palette-hint">${escapeHtml(it.hint || "")}</span>
            </div>`
        )
        .join("");
    }

    function search(q) {
      if (controller) controller.abort();
      controller = new AbortController();
      // Show a shimmer while the results are in flight
      results.innerHTML =
        `<div class="palette-skeleton">${Array.from({ length: 4 })
          .map(() => `<div class="sk"><span class="sk sk-circle"></span><span class="sk sk-line"></span><span class="sk sk-line sm"></span></div>`)
          .join("")}</div>`;
      const url = `/search/?q=${encodeURIComponent(q)}`;
      fetch(url, { signal: controller.signal, headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then((r) => r.json())
        .then((data) => {
          if (controller === null) return; // closed while in flight
          items = [];
          data.actions.forEach((a) => items.push({ ...a, meta: "action" }));
          data.candidates.forEach((c) => items.push({ ...c, meta: "candidate" }));
          data.jobs.forEach((j) => items.push({ ...j, meta: "job" }));
          active = items.length ? 0 : -1;
          render();
        })
        .catch(() => {
          if (controller) {
            controller = null;
            results.innerHTML = "";
          }
        });
    }

    function go(index) {
      const it = items[index];
      if (!it) return;
      // Match the View Transitions behaviour used by regular nav links.
      if (document.startViewTransition) {
        document.startViewTransition(() => { window.location.href = it.url; });
      } else {
        window.location.href = it.url;
      }
    }

    function move(delta) {
      if (!items.length) return;
      active = (active + delta + items.length) % items.length;
      render();
      const el = results.querySelector(`[data-index="${active}"]`);
      if (el) el.scrollIntoView({ block: "nearest" });
    }

    function keydown(e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        overlay.hidden ? open() : close();
        return;
      }
      if (overlay.hidden) return;
      if (e.key === "Escape") { e.preventDefault(); close(); return; }
      if (e.key === "ArrowDown") { e.preventDefault(); move(1); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); move(-1); return; }
      if (e.key === "Enter") { e.preventDefault(); go(active); return; }
    }

    input.addEventListener("input", () => {
      clearTimeout(fetchTimer);
      const q = input.value.trim();
      fetchTimer = setTimeout(() => search(q), 120);
    });

    results.addEventListener("click", (e) => {
      const item = e.target.closest(".palette-item");
      if (item) go(parseInt(item.getAttribute("data-index"), 10));
    });

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close();
    });
    if (trigger) trigger.addEventListener("click", () => (overlay.hidden ? open() : close()));

    document.addEventListener("keydown", keydown);
  }

  /* --- Pin / unpin candidates -------------------------------------------- */
  function initPins() {
    document.addEventListener("click", (e) => {
      const btn = e.target.closest ? e.target.closest("[data-pin-btn]") : null;
      if (!btn) return;
      e.preventDefault();
      const pk = btn.getAttribute("data-candidate-pk");
      if (!pk) return;
      fetch(`/candidates/${pk}/pin/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "X-CSRFToken": csrfToken(),
        },
        body: "",
      })
        .then((r) => r.json())
        .then((res) => {
          if (!res.ok) { toast("Could not update pin", "error"); return; }
          toast(res.pinned ? "Pinned to top" : "Unpinned", res.pinned ? "success" : "info");
          // Update all matching buttons on this page
          $$(`[data-pin-btn][data-candidate-pk="${pk}"]`).forEach((b) => {
            b.classList.toggle("active", res.pinned);
            const svg = b.querySelector("svg");
            if (svg) svg.setAttribute("fill", res.pinned ? "currentColor" : "none");
          });
          const row = $(`[data-candidate-row="${pk}"]`);
          if (row) row.classList.toggle("row-pinned", res.pinned);
        })
        .catch(() => toast("Network error", "error"));
    });
  }

  /* --- Live activity feed (auto-refresh) ---------------------------------- */
  function initActivityFeed() {
    const feed = $("#activityFeed");
    if (!feed) return;
    const url = feed.getAttribute("data-activity-url");
    if (!url) return;

    // Respect users on slow/limited connections
    const conn = navigator.connection || {};
    if (conn.saveData || conn.effectiveType === "2g" || conn.effectiveType === "slow-2g") return;

    // Seed from the server-rendered items; cap the set so a long-lived tab
    // never accumulates every event id ever seen.
    const knownIds = new Set(
      $$(".activity-item", feed).map((el) => el.getAttribute("data-event-id"))
    );
    let inFlight = false;
    let lastFingerprint = "";
    let lastToastAt = 0;

    const fingerprint = (events) =>
      events.slice(0, 10).map((e) => e.id).join(",");

    const itemHtml = (e) =>
      `<div class="activity-item ${knownIds.has(String(e.id)) ? "" : "activity-new"}" data-event-id="${e.id}">
        <span class="activity-ic kind-${escapeHtml(e.kind)}">${e.icon}</span>
        <div style="min-width: 0;">
          <div class="activity-text">${escapeHtml(e.text)}</div>
          <div class="activity-meta">${escapeHtml(e.meta)}</div>
        </div>
      </div>`;

    const refresh = async () => {
      if (inFlight || document.hidden) return;
      inFlight = true;
      try {
        const res = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
        if (!res.ok) return;
        const data = await res.json();
        const events = data.events || [];
        if (!events.length) return;

        const fp = fingerprint(events);
        const newCount = events.filter((e) => !knownIds.has(String(e.id))).length;

        // Skip DOM churn when nothing changed since the last poll
        if (fp !== lastFingerprint) {
          lastFingerprint = fp;
          feed.innerHTML = events.map(itemHtml).join("");
          events.forEach((e) => knownIds.add(String(e.id)));
          // Trim the set to the most recent 50 ids to keep it bounded
          if (knownIds.size > 50) {
            const recent = events.map((e) => String(e.id));
            knownIds.forEach((id) => {
              if (!recent.includes(id)) knownIds.delete(id);
            });
          }
        }

        // Throttle the toast so a parked dashboard isn't spammed
        if (newCount > 0 && Date.now() - lastToastAt > 20000) {
          lastToastAt = Date.now();
          toast(`${newCount} new activit${newCount === 1 ? "y" : "ies"}`, "info");
        }
      } catch (err) {
        /* network hiccup — try again next tick */
      } finally {
        inFlight = false;
      }
    };

    setInterval(refresh, 30000);

    // Refresh immediately when the tab becomes visible again
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) refresh();
    });
  }

  /* --- Page-load skeletons -------------------------------------------------- */
  function initPageSkeleton() {
    const html = document.documentElement;
    if (!html.classList.contains("page-loading")) return;
    if (!document.getElementById("realContent")) {
      html.classList.remove("page-loading");
      html.classList.add("page-ready");
      return;
    }

    const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let revealed = false;
    const reveal = () => {
      if (revealed) return;
      revealed = true;
      // Phase 1: fade the skeleton out while the real content fades in.
      html.classList.remove("page-loading");
      html.classList.add("page-leaving");
      // Phase 2 (after the 0.3s CSS fade): fully detach the skeleton.
      setTimeout(() => {
        html.classList.remove("page-leaving");
        html.classList.add("page-ready");
      }, 320);
    };

    // Back/forward cache: content is already painted — skip the skeleton
    window.addEventListener("pageshow", (e) => {
      if (e.persisted) reveal();
    });

    const started = performance.now();
    const finish = () => {
      // Reduced-motion users skip the forced beat entirely.
      const delay = reduceMotion ? 0 : Math.max(0, 340 - (performance.now() - started));
      setTimeout(reveal, delay);
    };

    if (document.readyState === "complete") {
      finish();
    } else {
      // Reveal once the window has loaded, but cap at ~900ms so slow
      // external assets (fonts / CDN) can't hold the skeleton forever.
      window.addEventListener("load", finish, { once: true });
      setTimeout(finish, 900);
    }
  }

  /* --- Live clock --------------------------------------------------------- */
  function initLiveClock() {
    const el = $("#liveClockText");
    if (!el) return;
    const tick = () => {
      const now = new Date();
      const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      const date = now.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
      el.textContent = `${date} · ${time}`;
    };
    tick();
    setInterval(tick, 1000);
  }

  /* --- Instant navigation: prefetch on hover/touch ---------------------- */
  function initPrefetch() {
    // Respect users on slow/limited connections
    const conn = navigator.connection || {};
    if (conn.saveData || conn.effectiveType === "2g" || conn.effectiveType === "slow-2g") return;
    if (window.matchMedia && window.matchMedia("(prefers-reduced-data: reduce)").matches) return;

    const cache = new Set();

    const prefetch = (url) => {
      if (cache.has(url)) return;
      cache.add(url);
      const link = document.createElement("link");
      link.rel = "prefetch";
      link.href = url;
      document.head.appendChild(link);
    };

    const handler = (e) => {
      if (e.defaultPrevented) return;
      const a = e.target.closest ? e.target.closest("a[href]") : null;
      if (!a) return;
      const href = a.getAttribute("href");
      if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("javascript:")) return;
      if (a.target === "_blank") return;
      if (a.closest("form")) return; // skip POST links (logout)
      try {
        const url = new URL(a.href, location.href);
        if (url.origin !== location.origin) return;
        prefetch(url.href);
      } catch (err) {
        /* ignore */
      }
    };

    document.addEventListener("pointerover", handler, { passive: true });
    document.addEventListener("pointerdown", handler, { passive: true });
    document.addEventListener("touchstart", handler, { passive: true });
  }

  /* --- Kick off --------------------------------------------------------- */
  document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initSidebar();
    initModals();
    initCharts();
    initCounters();
    initKanban();
    initTableSearch();
    initFileDrop();
    initPrefetch();
    initNavProgress();
    initPalette();
    initPins();
    initLiveClock();
    initActivityFeed();
    initPageSkeleton();
    initHireCelebration();
    bootstrapMessages();
  });
})();
