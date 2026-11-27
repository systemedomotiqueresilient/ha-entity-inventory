// Entity Inventory : panneau latéral (administrateurs uniquement), 0.10.0.
// Générer, télécharger et copier l'inventaire, sans Samba.
// JavaScript sans dépendance ni compilation. Tout texte venant du serveur est
// inséré avec textContent, jamais en HTML.

// Doit être identique à VERSION (const.py) : un test le vérifie
const PANEL_VERSION = "0.10.0";
// Au-delà, certaines IA refusent un collage : mieux vaut joindre le fichier
const COPY_WARN_BYTES = 150 * 1024;

const TEXTS = {
  fr: {
    title: "Entity Inventory",
    intro: "L'inventaire décrit la structure de votre Home Assistant (étages, pièces, appareils, entités, packages) sans aucun état. Donnez-le à votre IA pour qu'elle écrive des automatisations avec les bons noms d'entités.",
    generateTitle: "Générer",
    scopeHint: "Rien de choisi : inventaire complet. Sinon, seulement ce qui correspond (une pièce OU une autre ; une pièce ET un domaine). Sur ordinateur, Ctrl + clic (⌘ + clic sur Mac) pour en choisir plusieurs.",
    floors: "Étages",
    areas: "Pièces",
    labels: "Étiquettes",
    domains: "Domaines",
    generate: "Générer l'inventaire",
    clear: "Tout désélectionner",
    working: "Génération en cours…",
    done: "Inventaire écrit : {path} ({size}). {devices} appareils, {entities} entités.",
    broken: "Packages cassés : ils citent des entités qui n'existent plus. Signalez-le à votre IA, elle saura les corriger :",
    openPk: "Ouvrir Package Keeper",
    files: "Fichiers d'inventaire",
    noFile: "Aucun fichier pour l'instant : générez l'inventaire.",
    download: "Télécharger",
    copy: "Copier",
    copied: "Copié dans le presse-papiers ({size}). Collez-le dans la conversation avec votre IA.",
    copyBig: "Ce fichier fait {size}. Certaines IA refusent un collage aussi long : si c'est le cas, téléchargez-le plutôt et joignez-le à la conversation. Copier quand même ?",
    copyFailed: "Copie impossible dans ce navigateur. Utilisez Télécharger.",
    howTitle: "Comment s'en servir",
    how: "1. Générez l'inventaire. 2. Téléchargez-le et joignez le fichier à votre conversation avec l'IA (ou copiez-le et collez-le). 3. Demandez votre automatisation. Pour une question sur une seule pièce, un inventaire ciblé suffit et coûte moins cher à l'IA.",
    folder: "Dossier : {dir}",
    outdated: "Entity Inventory a été mis à jour ({old} → {new}) : rechargez la page pour utiliser la nouvelle version du panneau.",
    reloadPage: "Recharger la page",
    error: "Erreur : {msg}",
  },
  en: {
    title: "Entity Inventory",
    intro: "The inventory describes the structure of your Home Assistant (floors, areas, devices, entities, packages) without any state. Give it to your AI so it writes automations with the right entity names.",
    generateTitle: "Generate",
    scopeHint: "Nothing selected: full inventory. Otherwise, only what matches (one area OR another; an area AND a domain). On a computer, Ctrl + click (⌘ + click on a Mac) to pick several.",
    floors: "Floors",
    areas: "Areas",
    labels: "Labels",
    domains: "Domains",
    generate: "Generate the inventory",
    clear: "Clear selection",
    working: "Generating…",
    done: "Inventory written: {path} ({size}). {devices} devices, {entities} entities.",
    broken: "Broken packages: they cite entities that no longer exist. Tell your AI, it can fix them:",
    openPk: "Open Package Keeper",
    files: "Inventory files",
    noFile: "No file yet: generate the inventory.",
    download: "Download",
    copy: "Copy",
    copied: "Copied to the clipboard ({size}). Paste it into your conversation with the AI.",
    copyBig: "This file is {size}. Some AIs refuse such a long paste: if so, download it instead and attach it to the conversation. Copy anyway?",
    copyFailed: "Copy is not possible in this browser. Use Download.",
    howTitle: "How to use it",
    how: "1. Generate the inventory. 2. Download it and attach the file to your conversation with the AI (or copy and paste it). 3. Ask for your automation. For a question about a single area, a targeted inventory is enough and costs the AI less.",
    folder: "Folder: {dir}",
    outdated: "Entity Inventory was updated ({old} → {new}): reload the page to use the new version of the panel.",
    reloadPage: "Reload the page",
    error: "Error: {msg}",
  },
};

const STYLE = `
  :host { display: block; height: 100%; overflow: auto; background: var(--primary-background-color); color: var(--primary-text-color); font-family: var(--paper-font-body1_-_font-family, sans-serif); }
  .top { display: flex; align-items: center; gap: 12px; height: var(--header-height, 56px); padding: 0 16px; background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, white); font-size: 20px; }
  .top .version { font-size: 14px; opacity: .7; }
  .wrap { display: grid; grid-template-columns: 1fr minmax(260px, 380px); gap: 16px; padding: 16px; box-sizing: border-box; max-width: 1200px; }
  @media (max-width: 800px) { .wrap { grid-template-columns: 1fr; } }
  .card { background: var(--card-background-color); border-radius: 12px; padding: 16px; box-shadow: var(--ha-card-box-shadow, none); border: 1px solid var(--divider-color); }
  h2 { font-size: 18px; margin: 0 0 8px; font-weight: 500; }
  .muted { color: var(--secondary-text-color); font-size: 13px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 12px 0; }
  label { display: block; font-size: 13px; color: var(--secondary-text-color); margin-bottom: 4px; }
  select { font: inherit; width: 100%; padding: 4px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
  .bar { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
  button, a.button { font: inherit; padding: 8px 14px; border-radius: 8px; border: none; cursor: pointer; background: var(--primary-color); color: var(--text-primary-color, white); text-decoration: none; display: inline-block; }
  button.flat, a.flat { background: transparent; color: var(--primary-color); border: 1px solid var(--divider-color); }
  button:disabled { opacity: .5; cursor: default; }
  .msg { padding: 10px 12px; border-radius: 8px; margin: 8px 0; font-size: 14px; }
  .msg.ok { background: rgba(67,160,71,.12); }
  .msg.warn { background: rgba(255,152,0,.15); }
  .msg.err { background: rgba(219,68,55,.15); }
  ul { list-style: none; padding: 0; margin: 0; }
  li { padding: 8px 0; border-bottom: 1px solid var(--divider-color); }
  li .n { font-family: var(--code-font-family, monospace); font-size: 13px; word-break: break-all; }
  pre { white-space: pre-wrap; font-family: var(--code-font-family, monospace); font-size: 12px; margin: 6px 0 0; }
`;

class EntityInventoryPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._state = { overview: null, selection: { floors: [], areas: [], labels: [], domains: [] }, result: null, message: null, busy: false };
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._init();
  }
  set narrow(_value) {}
  set panel(_value) {}

  get t() {
    const lang = (this._hass?.language || "en").startsWith("fr") ? "fr" : "en";
    return TEXTS[lang];
  }

  _fmt(text, values = {}) {
    return text.replace(/\{(\w+)\}/g, (_, key) => values[key] ?? "");
  }

  _size(bytes) {
    const fr = this.t === TEXTS.fr;
    if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} ${fr ? "Mo" : "MB"}`;
    return `${Math.max(1, Math.round(bytes / 1024))} ${fr ? "Ko" : "KB"}`;
  }

  _el(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === "onclick") el.addEventListener("click", value);
      else if (key === "text") el.textContent = value;
      else if (value === true) el.setAttribute(key, "");
      else if (value !== false && value != null) el.setAttribute(key, value);
    }
    for (const child of children) if (child) el.append(child);
    return el;
  }

  async _ws(type, data = {}) {
    return this._hass.callWS({ type: `entity_inventory/${type}`, ...data });
  }

  async _init() {
    this.shadowRoot.innerHTML = "";
    this.shadowRoot.append(this._el("style", { text: STYLE }));
    this._root = this._el("div");
    this.shadowRoot.append(this._root);
    this._hass.connection?.addEventListener?.("ready", () => this._refresh());
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && this.isConnected) this._refresh();
    });
    await this._refresh();
  }

  async _refresh() {
    try {
      this._state.overview = await this._ws("overview");
      this._checkVersion(this._state.overview.version);
    } catch (err) {
      this._state.message = { kind: "err", text: this._fmt(this.t.error, { msg: err.message }) };
    }
    this._render();
  }

  // Même mécanisme que Package Keeper : après une mise à jour, le navigateur
  // garde l'ancien panneau tant que la page n'est pas rechargée.
  _checkVersion(serverVersion) {
    if (!serverVersion || serverVersion === PANEL_VERSION) {
      this._state.outdated = null;
      return;
    }
    const key = `entity-inventory-reloaded-${serverVersion}`;
    let alreadyTried = true;
    try {
      alreadyTried = sessionStorage.getItem(key) === "1";
      if (!alreadyTried) sessionStorage.setItem(key, "1");
    } catch (_err) {
      alreadyTried = true;
    }
    if (!alreadyTried) {
      window.location.reload();
      return;
    }
    this._state.outdated = serverVersion;
  }

  async _generate() {
    const s = this._state;
    s.busy = true;
    s.message = { kind: "ok", text: this.t.working };
    this._render();
    try {
      const scope = {};
      for (const [key, values] of Object.entries(s.selection)) if (values.length) scope[key] = values;
      s.result = await this._ws("generate", scope);
      s.message = null;
      s.overview = await this._ws("overview");
    } catch (err) {
      s.result = null;
      s.message = { kind: "err", text: this._fmt(this.t.error, { msg: err.message }) };
    } finally {
      s.busy = false;
      this._render();
    }
  }

  // Les adresses signées expirent au bout de 5 minutes : on en redemande une
  async _freshUrl(name) {
    const overview = await this._ws("overview");
    this._state.overview = overview;
    return overview.files.find((f) => f.name === name);
  }

  async _download(name) {
    try {
      const file = await this._freshUrl(name);
      if (!file) return;
      const link = this._el("a", { href: file.url, download: file.name });
      this.shadowRoot.append(link);
      link.click();
      link.remove();
    } catch (err) {
      this._state.message = { kind: "err", text: this._fmt(this.t.error, { msg: err.message }) };
      this._render();
    }
  }

  async _copy(name) {
    const t = this.t;
    try {
      const file = await this._freshUrl(name);
      if (!file) return;
      if (file.size > COPY_WARN_BYTES && !confirm(this._fmt(t.copyBig, { size: this._size(file.size) }))) return;
      const response = await fetch(file.url, { credentials: "same-origin" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const text = await response.text();
      if (!(await this._writeClipboard(text))) {
        this._state.message = { kind: "err", text: t.copyFailed };
      } else {
        this._state.message = { kind: "ok", text: this._fmt(t.copied, { size: this._size(file.size) }) };
      }
    } catch (err) {
      this._state.message = { kind: "err", text: this._fmt(t.error, { msg: err.message }) };
    }
    this._render();
  }

  async _writeClipboard(text) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (_err) {
      // repli ci-dessous (http local, navigateur ancien)
    }
    const area = this._el("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    this.shadowRoot.append(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (_err) {
      ok = false;
    }
    area.remove();
    return ok;
  }

  _select(key, label, items) {
    const s = this._state;
    const select = this._el("select", { multiple: true, size: Math.min(6, Math.max(3, items.length)), "aria-label": label });
    for (const item of items) {
      const option = this._el("option", { value: item.id, text: item.name });
      option.selected = s.selection[key].includes(item.id);
      select.append(option);
    }
    select.addEventListener("change", () => {
      s.selection[key] = [...select.selectedOptions].map((o) => o.value);
    });
    return this._el("div", {}, this._el("label", { text: label }), select);
  }

  _renderResult() {
    const t = this.t;
    const s = this._state;
    const box = this._el("div");
    if (s.message) box.append(this._el("div", { class: `msg ${s.message.kind}`, text: s.message.text }));
    const r = s.result;
    if (!r) return box;
    box.append(this._el("div", { class: "msg ok", text: this._fmt(t.done, { path: r.path, size: this._size(r.size_bytes), devices: r.devices ?? 0, entities: r.entities ?? 0 }) }));
    const broken = Object.entries(r.broken_packages || {});
    if (broken.length) {
      const warn = this._el("div", { class: "msg warn", text: t.broken });
      warn.append(this._el("pre", { text: broken.map(([name, ids]) => `• ${name} : ${ids.join(", ")}`).join("\n") }));
      if (s.overview?.package_keeper) warn.append(this._el("a", { href: "/package-keeper", class: "button flat", text: t.openPk }));
      box.append(warn);
    }
    box.append(this._el("div", { class: "bar" },
      this._el("button", { text: t.download, onclick: () => this._download(r.name) }),
      this._el("button", { class: "flat", text: t.copy, onclick: () => this._copy(r.name) })));
    return box;
  }

  _render() {
    if (!this._root) return;
    const t = this.t;
    const s = this._state;
    const o = s.overview;
    this._root.innerHTML = "";
    this._root.append(this._el("div", { class: "top" },
      this._el("span", { text: t.title }),
      this._el("span", { class: "version", text: `v${PANEL_VERSION}` })));
    if (s.outdated) {
      this._root.append(this._el("div", { class: "msg warn" },
        this._el("span", { text: `${this._fmt(t.outdated, { old: PANEL_VERSION, new: s.outdated })} ` }),
        this._el("button", { text: t.reloadPage, onclick: () => window.location.reload() })));
    }
    const wrap = this._el("div", { class: "wrap" });
    this._root.append(wrap);

    const main = this._el("div", { class: "card" },
      this._el("h2", { text: t.generateTitle }),
      this._el("p", { class: "muted", text: t.intro }),
      this._el("p", { class: "muted", text: t.scopeHint }));
    if (o) {
      const grid = this._el("div", { class: "grid" });
      for (const key of ["floors", "areas", "labels", "domains"]) {
        if (o.choices[key]?.length) grid.append(this._select(key, t[key], o.choices[key]));
      }
      main.append(grid);
    }
    main.append(this._el("div", { class: "bar" },
      this._el("button", { text: t.generate, disabled: s.busy || !o, onclick: () => this._generate() }),
      this._el("button", { class: "flat", text: t.clear, disabled: s.busy, onclick: () => {
        s.selection = { floors: [], areas: [], labels: [], domains: [] };
        this._render();
      } })));
    main.append(this._renderResult());
    wrap.append(main);

    const side = this._el("div", { class: "card" }, this._el("h2", { text: t.files }));
    if (o) side.append(this._el("div", { class: "muted", text: this._fmt(t.folder, { dir: o.output_path.replace(/\/[^/]*$/, "") }) }));
    if (!o?.files?.length) {
      side.append(this._el("p", { class: "muted", text: t.noFile }));
    } else {
      const list = this._el("ul");
      for (const file of o.files) {
        const date = new Date(file.modified * 1000).toLocaleString(this._hass.language || undefined);
        list.append(this._el("li", {},
          this._el("div", { class: "n", text: file.name }),
          this._el("div", { class: "muted", text: `${this._size(file.size)} · ${date}` }),
          this._el("div", { class: "bar" },
            this._el("button", { class: "flat", text: t.download, onclick: () => this._download(file.name) }),
            this._el("button", { class: "flat", text: t.copy, onclick: () => this._copy(file.name) }))));
      }
      side.append(list);
    }
    side.append(this._el("h2", { text: t.howTitle }), this._el("p", { class: "muted", text: t.how }));
    wrap.append(side);
  }
}

if (!customElements.get("entity-inventory-panel")) {
  customElements.define("entity-inventory-panel", EntityInventoryPanel);
}
