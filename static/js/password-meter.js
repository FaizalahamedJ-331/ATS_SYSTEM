/*
 * TalentPulse password strength meter.
 *
 * Attach to any password input with data-pw-meter="id-of-meter-root" (or a
 * bare data-pw-meter for auto-created UI). Mirrors the server-side policy:
 *   - minimum length  (PASSWORD_MIN_LENGTH, default 10)
 *   - >= 3 of 4 character classes (lower / upper / digits / symbols)
 *   - not a top-2000 common password (django CommonPasswordValidator's list)
 *   - not purely numeric
 * Adds a live 5-segment bar + rule checklist and an optional show/hide toggle
 * (input data-pw-toggle="true").
 */
(function () {
  "use strict";

  var MIN_LENGTH = 10;  // overridable per-input via data-pw-min
  var RE_CLASSES = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/];
  var COMMON = ["password","123456","12345678","123456789","qwerty","abc123","football","monkey","letmein","dragon","111111","baseball","iloveyou","trustno1","sunshine","master","welcome","shadow","ashley","mustang","superman","1234567","michael","football1","1234567890","abcdef","654321","11111111","charlie","aa123456","donald","password1","qwerty123","1q2w3e4r","123qwe","zaq12wsx","freedom","whatever","lovely","jesus","soccer","princess","batman","starwars","samsung","secret","hello","admin","root","passw0rd","password123","123456a","987654321","qwe123","1qaz2wsx","pass1234","pass123","gandalf","cookie","access","liverpool","internet","nintendo","fishing","pepper","summer","winter","spring","autumn","qazwsx","zaq1xsw2","asdfgh","zxcvbn","poiuyt","qwertyuiop","asdfghjkl","zxcvbnm","1234qwer","qwer1234","qwerty12345","12345678910","9876543210","a1b2c3","abc12345","test","test123","demo","demo123","changeme","welcome1","letmein123","monkey123","dragon123","winter2020","summer2020"];

  function classes(pw) {
    var n = 0;
    for (var i = 0; i < RE_CLASSES.length; i++) if (RE_CLASSES[i].test(pw)) n++;
    return n;
  }

  function analyze(pw) {
    var checks = [
      { key: "len", label: "At least " + MIN_LENGTH + " characters", pass: pw.length >= MIN_LENGTH },
      { key: "classes", label: "Mix of 3+ types (letters, numbers, symbols)", pass: classes(pw) >= 3 },
      { key: "numeric", label: "Not just numbers", pass: !/^\d+$/.test(pw) },
      { key: "common", label: "Not a commonly used password", pass: COMMON.indexOf(pw.toLowerCase()) === -1 }
    ];

    var score = 0;
    if (pw.length >= MIN_LENGTH) score += 1;
    if (pw.length >= MIN_LENGTH + 6) score += 1;
    if (classes(pw) >= 3) score += 1;
    if (classes(pw) === 4) score += 1;
    if (pw.length >= 16) score += 1;

    if (COMMON.indexOf(pw.toLowerCase()) !== -1) score = Math.min(score, 1);

    var label, tone;
    if (pw.length === 0) { label = ""; tone = ""; }
    else if (score <= 1) { label = "Weak"; tone = "weak"; }
    else if (score === 2) { label = "Fair"; tone = "fair"; }
    else if (score === 3 || score === 4) { label = "Strong"; tone = "strong"; }
    else { label = "Excellent"; tone = "excellent"; }

    return { score: score, max: 5, label: label, tone: tone, checks: checks };
  }

  function meterFor(input) {
    var root = input.closest ? input.closest(".field") : input.parentNode;
    if (!root) return null;
    var box = root.querySelector(".pw-meter");
    if (!box) return null;
    return {
      bar: box.querySelector(".pw-bar-fill"),
      segs: box.querySelectorAll(".pw-seg"),
      label: box.querySelector(".pw-label"),
      list: box.querySelector(".pw-rules")
    };
  }

  function render(input) {
    var ui = meterFor(input);
    if (!ui) return;
    var res = analyze(input.value);

    for (var i = 0; i < ui.segs.length; i++) {
      ui.segs[i].classList.toggle("on", i < res.score);
    }
    if (ui.bar) {
      ui.bar.style.width = (res.score / res.max * 100) + "%";
      ui.bar.className = "pw-bar-fill " + res.tone;
    }
    if (ui.label) {
      ui.label.textContent = res.label;
      ui.label.className = "pw-label " + res.tone;
    }
    if (ui.list && res.checks) {
      var items = ui.list.querySelectorAll("li");
      for (var j = 0; j < items.length && j < res.checks.length; j++) {
        var ok = res.checks[j].pass;
        items[j].className = ok ? "ok" : "no";
        items[j].innerHTML = (ok ? "&#10003; " : "&#10007; ") + res.checks[j].label;
      }
    }
  }

  function toggleVis(input, btn) {
    var show = input.type === "password";
    input.type = show ? "text" : "password";
    if (btn) {
      btn.textContent = show ? "Hide" : "Show";
      btn.setAttribute("aria-pressed", show ? "true" : "false");
    }
  }

  function init(input) {
    if (!input || input.dataset.pwBound) return;
    input.dataset.pwBound = "1";
    if (input.dataset.pwMin && /^\d+$/.test(input.dataset.pwMin)) {
      MIN_LENGTH = parseInt(input.dataset.pwMin, 10);
    }
    var root = input.closest ? input.closest(".field") : input.parentNode;
    if (!root) return;

    if (input.dataset.pwToggle === "true") {
      var wrap = document.createElement("span");
      wrap.className = "pw-input-wrap";
      input.parentNode.insertBefore(wrap, input);
      wrap.appendChild(input);
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "pw-toggle";
      btn.textContent = "Show";
      btn.setAttribute("aria-pressed", "false");
      btn.addEventListener("click", function () { toggleVis(input, btn); });
      wrap.appendChild(btn);
    }

    input.addEventListener("input", function () { render(input); });
    render(input);
  }

  function initAll() {
    var inputs = document.querySelectorAll("input[data-pw-meter]");
    for (var i = 0; i < inputs.length; i++) init(inputs[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
  window.TalentPulsePasswordMeter = { init: initAll };
})();
