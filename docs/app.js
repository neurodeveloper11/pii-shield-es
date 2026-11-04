/* pii-shield-es · interacciones mínimas (tema, idioma, pestañas, copiar). Sin dependencias. */
(function () {
  "use strict";

  var root = document.documentElement;

  function read(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }
  function write(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (e) {
      /* almacenamiento bloqueado: la preferencia solo dura la sesión */
    }
  }

  /* ---------- idioma ---------- */
  var TITLES = {
    es: "pii-shield-es · Anonimiza datos personales en español, 100 % local",
    en: "pii-shield-es · Anonymize personal data in Spanish text, 100% local",
  };

  function setLang(lang, persist) {
    if (lang !== "es" && lang !== "en") lang = "es";
    root.setAttribute("data-lang", lang);
    root.setAttribute("lang", lang);
    document.title = TITLES[lang];
    document.querySelectorAll("[data-set-lang]").forEach(function (btn) {
      btn.setAttribute("aria-pressed", String(btn.getAttribute("data-set-lang") === lang));
    });
    if (persist) write("pii-lang", lang);
  }

  var savedLang = read("pii-lang");
  var browserLang = (navigator.language || "es").slice(0, 2).toLowerCase();
  setLang(savedLang || (browserLang === "en" ? "en" : "es"), false);

  document.querySelectorAll("[data-set-lang]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      setLang(btn.getAttribute("data-set-lang"), true);
    });
  });

  /* ---------- tema ---------- */
  function currentTheme() {
    var explicit = root.getAttribute("data-theme");
    if (explicit) return explicit;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function applyTheme(theme, persist) {
    root.setAttribute("data-theme", theme);
    var btn = document.getElementById("theme-toggle");
    if (btn) btn.setAttribute("aria-pressed", String(theme === "dark"));
    if (persist) write("pii-theme", theme);
  }

  var savedTheme = read("pii-theme");
  if (savedTheme === "light" || savedTheme === "dark") {
    applyTheme(savedTheme, false);
  } else {
    var themeBtn = document.getElementById("theme-toggle");
    if (themeBtn) themeBtn.setAttribute("aria-pressed", String(currentTheme() === "dark"));
  }

  var toggle = document.getElementById("theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      applyTheme(currentTheme() === "dark" ? "light" : "dark", true);
    });
  }

  /* ---------- pestañas del ejemplo ---------- */
  var tabs = document.querySelectorAll('[role="tab"][data-target]');
  function selectTab(tab) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", String(on));
      t.setAttribute("tabindex", on ? "0" : "-1");
      var panel = document.getElementById(t.getAttribute("data-target"));
      if (panel) panel.hidden = !on;
    });
  }
  tabs.forEach(function (tab, i) {
    tab.addEventListener("click", function () {
      selectTab(tab);
    });
    tab.addEventListener("keydown", function (ev) {
      var next = null;
      if (ev.key === "ArrowRight") next = tabs[(i + 1) % tabs.length];
      if (ev.key === "ArrowLeft") next = tabs[(i - 1 + tabs.length) % tabs.length];
      if (next) {
        ev.preventDefault();
        selectTab(next);
        next.focus();
      }
    });
  });

  /* ---------- copiar ---------- */
  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var source = document.getElementById(btn.getAttribute("data-copy"));
      if (!source) return;
      var text = source.textContent.replace(/\s+$/, "");
      var done = function () {
        var original = btn.getAttribute("data-label") || btn.textContent;
        btn.setAttribute("data-label", original);
        btn.textContent = root.getAttribute("data-lang") === "en" ? "Copied" : "Copiado";
        window.setTimeout(function () {
          btn.textContent = original;
        }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {});
      } else {
        var area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.className = "visually-hidden";
        document.body.appendChild(area);
        area.select();
        try {
          document.execCommand("copy");
          done();
        } catch (e) {
          /* sin permiso para copiar */
        }
        document.body.removeChild(area);
      }
    });
  });
})();
