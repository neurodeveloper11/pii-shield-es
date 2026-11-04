/* DataShield · herramienta de la web: anonimiza archivos DENTRO del navegador con Pyodide.
   El archivo nunca se envía a un servidor: Pyodide (Python en WebAssembly) y el código de
   DataShield se descargan desde este mismo sitio y se ejecutan localmente. */
(function () {
  "use strict";

  var root = document.documentElement;
  var input = document.getElementById("file-input");
  var drop = document.getElementById("drop");
  if (!input || !drop) return;

  var statusEl = document.getElementById("tool-status");
  var resultEl = document.getElementById("tool-result");
  var titleEl = document.getElementById("tool-title");
  var countsEl = document.getElementById("tool-counts");
  var warnEl = document.getElementById("tool-warn");
  var downloadEl = document.getElementById("tool-download");
  var tableEl = document.getElementById("tool-table");
  var pasteIn = document.getElementById("paste-in");
  var pasteGo = document.getElementById("paste-go");
  var pasteOut = document.getElementById("paste-out");

  var SUPPORTED = [".docx", ".xlsx", ".csv", ".tsv", ".txt", ".md"];
  var MIME = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".md": "text/markdown",
  };
  var MAX_BYTES = 50 * 1024 * 1024;

  var T = {
    es: {
      loading: "Cargando el motor de anonimización (solo la primera vez, unos 14 MB)…",
      processing: "Procesando «{name}» en tu navegador…",
      done: "Listo: {n} datos personales reemplazados en «{name}».",
      none: "No se encontraron datos personales en «{name}». Revísalo de todas formas.",
      unsupported: "Formato no soportado. Usa .docx, .xlsx, .csv, .txt o .md.",
      tooBig: "El archivo supera 50 MB. Para archivos grandes usa la terminal: datashield anonimizar -f archivo.",
      legacy: "Ese es un formato antiguo (.doc/.xls). Ábrelo y guárdalo como .docx o .xlsx.",
      error: "No se pudo procesar el archivo: {msg}",
      meta: "Metadatos borrados: {list}.",
      pasteEmpty: "Pega un texto primero.",
    },
    en: {
      loading: "Loading the anonymization engine (first time only, about 14 MB)…",
      processing: "Processing “{name}” in your browser…",
      done: "Done: {n} personal data items replaced in “{name}”.",
      none: "No personal data found in “{name}”. Review it anyway.",
      unsupported: "Unsupported format. Use .docx, .xlsx, .csv, .txt or .md.",
      tooBig: "The file is over 50 MB. For large files use the CLI: datashield anonimizar -f file.",
      legacy: "That is a legacy format (.doc/.xls). Open it and save it as .docx or .xlsx.",
      error: "Could not process the file: {msg}",
      meta: "Metadata removed: {list}.",
      pasteEmpty: "Paste some text first.",
    },
  };

  function t(key, vars) {
    var lang = root.getAttribute("data-lang") === "en" ? "en" : "es";
    var s = T[lang][key];
    Object.keys(vars || {}).forEach(function (k) {
      s = s.split("{" + k + "}").join(vars[k]);
    });
    return s;
  }

  function status(msg, kind) {
    statusEl.textContent = msg || "";
    statusEl.className = "tool-status" + (kind ? " is-" + kind : "");
  }

  function ext(name) {
    var i = name.lastIndexOf(".");
    return i >= 0 ? name.slice(i).toLowerCase() : "";
  }

  function mode() {
    var checked = document.querySelector('input[name="modo"]:checked');
    return checked ? checked.value : "etiqueta";
  }

  /* ---------- carga perezosa de Pyodide + DataShield ---------- */
  var engine = null;

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = function () {
        reject(new Error("no se pudo cargar " + src));
      };
      document.head.appendChild(s);
    });
  }

  function loadEngine() {
    if (engine) return engine;
    engine = (async function () {
      var base = new URL(".", window.location.href);
      await loadScript(new URL("vendor/pyodide/pyodide.js", base).href);
      var py = await window.loadPyodide({ indexURL: new URL("vendor/pyodide/", base).href });
      var manifest = await (await fetch(new URL("py/manifest.json", base))).json();
      py.FS.mkdirTree("/app/datashield_es");
      for (var i = 0; i < manifest.files.length; i++) {
        var name = manifest.files[i];
        var code = await (await fetch(new URL("py/datashield_es/" + name, base))).text();
        py.FS.writeFile("/app/datashield_es/" + name, code);
      }
      py.runPython(
        "import sys\nsys.path.insert(0, '/app')\n" +
          "import json\nfrom datashield_es import PseudonymTable, anonymize\n" +
          "from datashield_es.files import anonymize_bytes, default_output_path\n"
      );
      return py;
    })();
    engine.catch(function () {
      engine = null;
    });
    return engine;
  }

  /* ---------- procesamiento ---------- */
  var lastUrls = [];

  function offer(link, bytes, filename, mime) {
    var url = URL.createObjectURL(new Blob([bytes], { type: mime }));
    lastUrls.push(url);
    link.href = url;
    link.setAttribute("download", filename);
    link.hidden = false;
  }

  function showReport(report, filename) {
    countsEl.innerHTML = "";
    warnEl.innerHTML = "";
    Object.keys(report.conteo).forEach(function (tipo) {
      var li = document.createElement("li");
      li.textContent = tipo + " · " + report.conteo[tipo];
      countsEl.appendChild(li);
    });
    var warnings = report.advertencias.slice();
    if (report.metadatos_limpiados.length) {
      warnings.unshift(t("meta", { list: report.metadatos_limpiados.join(", ") }));
    }
    warnings.forEach(function (w) {
      var li = document.createElement("li");
      li.textContent = w;
      warnEl.appendChild(li);
    });
    titleEl.textContent = report.total
      ? t("done", { n: report.total, name: filename })
      : t("none", { name: filename });
  }

  async function processFile(file) {
    lastUrls.forEach(URL.revokeObjectURL);
    lastUrls = [];
    resultEl.hidden = true;
    var e = ext(file.name);
    if (e === ".doc" || e === ".xls") return status(t("legacy"), "error");
    if (SUPPORTED.indexOf(e) < 0) return status(t("unsupported"), "error");
    if (file.size > MAX_BYTES) return status(t("tooBig"), "error");
    try {
      if (!window.loadPyodide) status(t("loading"), "busy");
      var py = await loadEngine();
      status(t("processing", { name: file.name }), "busy");
      await new Promise(function (r) {
        setTimeout(r, 30);
      });
      var data = new Uint8Array(await file.arrayBuffer());
      py.globals.set("data_js", data);
      py.globals.set("nombre_js", file.name);
      py.globals.set("modo_js", mode());
      py.globals.set("meta_js", document.getElementById("opt-meta").checked);
      py.runPython(
        "tabla = PseudonymTable() if modo_js == 'seudonimo' else None\n" +
          "out_bytes, rep = anonymize_bytes(bytes(data_js.to_py()), nombre_js, modo_js, " +
          "tabla=tabla, limpiar_metadatos=bool(meta_js))\n" +
          "rep_json = json.dumps(rep.to_dict(), ensure_ascii=False)\n" +
          "tabla_json = tabla.to_json() if tabla is not None else ''\n" +
          "salida_nombre = default_output_path(nombre_js).name\n"
      );
      var outProxy = py.globals.get("out_bytes");
      var outBytes = outProxy.toJs();
      outProxy.destroy();
      var report = JSON.parse(py.globals.get("rep_json"));
      var outName = py.globals.get("salida_nombre");
      var tableJson = py.globals.get("tabla_json");
      py.runPython("del data_js, out_bytes, tabla");
      offer(downloadEl, outBytes, outName, MIME[e] || "application/octet-stream");
      if (tableJson) {
        offer(tableEl, tableJson, outName.replace(/\.[^.]+$/, "") + ".tabla.json", "application/json");
      } else {
        tableEl.hidden = true;
        tableEl.removeAttribute("download");
      }
      showReport(report, file.name);
      resultEl.hidden = false;
      status("");
    } catch (err) {
      var msg = String((err && err.message) || err).split("\n").filter(Boolean).pop();
      status(t("error", { msg: msg }), "error");
    }
  }

  input.addEventListener("change", function () {
    if (input.files && input.files[0]) processFile(input.files[0]);
    input.value = "";
  });
  ["dragenter", "dragover"].forEach(function (name) {
    drop.addEventListener(name, function (ev) {
      ev.preventDefault();
      drop.classList.add("is-over");
    });
  });
  ["dragleave", "drop"].forEach(function (name) {
    drop.addEventListener(name, function (ev) {
      ev.preventDefault();
      drop.classList.remove("is-over");
    });
  });
  drop.addEventListener("drop", function (ev) {
    var files = ev.dataTransfer && ev.dataTransfer.files;
    if (files && files[0]) processFile(files[0]);
  });

  /* ---------- texto pegado ---------- */
  if (pasteGo) {
    pasteGo.addEventListener("click", async function () {
      var text = pasteIn.value;
      if (!text.trim()) return status(t("pasteEmpty"), "error");
      try {
        if (!window.loadPyodide) status(t("loading"), "busy");
        var py = await loadEngine();
        py.globals.set("texto_js", text);
        py.globals.set("modo_js", mode());
        pasteOut.textContent = py.runPython("anonymize(texto_js, modo_js)");
        pasteOut.hidden = false;
        status("");
      } catch (err) {
        status(t("error", { msg: String((err && err.message) || err) }), "error");
      }
    });
  }
})();
