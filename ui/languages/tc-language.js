/* Local i18next wrapper. Translation data never authorizes an action. */
(() => {
  'use strict';
  const STORAGE = 'tonecommand.language.v1';
  const LIMIT = 2 * 1024 * 1024;
  let catalog = null, selected = 'en', imported = null;
  const registered = [];
  const attrs = ['title', 'placeholder', 'aria-label'];
  const engine = window.i18next?.createInstance();
  if (engine) engine.init({lng: 'en', fallbackLng: 'en', initAsync: false,
    keySeparator: false, nsSeparator: false, returnNull: false,
    resources: {en: {translation: {}}},
    interpolation: {escapeValue: false}, saveMissing: false});

  function text(key, values = {}) {
    return engine ? engine.t(key, values) : key.replace(/\{\{(\w+)\}\}/g,
      (_, name) => String(values[name] ?? '{{' + name + '}}'));
  }
  function placeholders(value) {
    return [...value.matchAll(/\{\{(\w+)\}\}/g)].map(m => m[1]).sort().join('|');
  }
  function validate(pack) {
    if (!catalog) throw new Error('The English catalog is unavailable. Keep using English.');
    if (!pack || Object.getPrototypeOf(pack) !== Object.prototype || pack.schema !== 1
        || typeof pack.locale !== 'string' || !/^[a-z]{2,3}(?:-[A-Z]{2})?$/.test(pack.locale)
        || pack.locale === 'en' || typeof pack.name !== 'string' || !pack.name.trim()
        || pack.name.length > 60 || pack.catalog_version !== catalog.catalog_version
        || pack.catalog_sha256 !== catalog.catalog_sha256
        || !pack.translations || Object.getPrototypeOf(pack.translations) !== Object.prototype)
      throw new Error('Invalid or incompatible language pack. Download the matching release.');
    const entries = Object.entries(pack.translations);
    if (!entries.length) throw new Error('This is an empty translator template, not a translated pack.');
    for (const [key, value] of entries) {
      if (!Object.hasOwn(catalog.translations, key) || typeof value !== 'string'
          || !value.trim() || value.length > 12000 || /\$t\(/.test(value)
          || (catalog.protected_keys.includes(key) && value !== key)
          || placeholders(value) !== placeholders(key))
        throw new Error('A translation has an unknown key or changed placeholders. Pack not installed.');
    }
    return pack;
  }
  // Bind initial shipped markup only. Never scan a later user/AI/device response.
  function capture(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode, parent = node.parentElement;
      if (!parent || parent.closest('script,style,textarea,code,pre,[data-no-translate]')) continue;
      const value = node.nodeValue, key = value.trim();
      if (!key || !/[A-Za-z]/.test(key)) continue;
      if (parent.tagName === 'OPTION' && !parent.hasAttribute('value'))
        parent.setAttribute('value', parent.value); // Label changes must never alter a wire enum.
      registered.push({node, key, prefix: value.slice(0, value.indexOf(key)),
        suffix: value.slice(value.indexOf(key) + key.length), last: value});
    }
    root.querySelectorAll('*').forEach(node => {
      if (node.closest('[data-no-translate]')) return;
      for (const attr of attrs) if (node.hasAttribute(attr)) {
        const key = node.getAttribute(attr);
        registered.push({node, attr, key, last: key});
      }
    });
  }
  function apply() {
    for (const entry of registered) {
      if (!entry.node.isConnected) continue;
      const current = entry.attr ? entry.node.getAttribute(entry.attr) : entry.node.nodeValue;
      if (current !== entry.last) continue; // A live reading/plan now owns this node.
      if (!catalog || !Object.hasOwn(catalog.translations, entry.key)) continue;
      const translated = text(entry.key);
      entry.last = entry.attr ? translated : entry.prefix + translated + entry.suffix;
      if (entry.attr) entry.node.setAttribute(entry.attr, entry.last);
      else entry.node.nodeValue = entry.last;
    }
    document.documentElement.lang = selected;
    window.dispatchEvent(new CustomEvent('tc-language-changed', {detail: {locale: selected}}));
  }
  async function choose(locale) {
    if (locale !== 'en' && (!imported || imported.locale !== locale))
      throw new Error('Import this language pack first.');
    selected = locale;
    if (engine) await engine.changeLanguage(locale);
    apply();
    try { localStorage.setItem(STORAGE, JSON.stringify({locale: selected, pack: imported})); }
    catch { /* Session-only choice when browser storage is unavailable. */ }
  }
  function mount() {
    const dialog = document.createElement('dialog');
    dialog.id = 'tc-language-dialog';
    dialog.style.cssText = 'max-width:560px;width:85vw;background:#101923;color:#eee;border:1px solid #40dfff;padding:24px;max-height:80vh;overflow:auto';
    dialog.innerHTML = '<h2>Interface language</h2><p>English is the base language. Missing translations stay English. User text, AI replies, Fractal names and technical identifiers are not translated.</p>'
      + '<label>Language <select aria-label="Interface language"><option value="en">English</option></select></label>'
      + '<p><label>Import language pack (.json) <input type="file" accept=".json,application/json"></label></p>'
      + '<p><a href="/language/en.json" download="en.json">Download English catalog</a> | '
      + '<a href="/language/template.json" download="template.json">Translator template</a> | '
      + '<a href="https://github.com/Axelman8/ToneCommand/releases" target="_blank" rel="noopener noreferrer">GitHub language packs</a></p>'
      + '<p role="status"></p><button type="button">Close</button>';
    document.body.append(dialog);
    const select = dialog.querySelector('select'), status = dialog.querySelector('[role=status]');
    const refresh = () => {
      select.replaceChildren(new Option('English', 'en'));
      if (imported) select.append(new Option(imported.name, imported.locale));
      select.value = selected;
    };
    dialog.querySelector('button').onclick = () => dialog.close();
    select.onchange = async () => {
      try { await choose(select.value); status.textContent = text('Interface language changed. Existing plans and unsent input are unchanged.'); }
      catch (error) { status.textContent = error.message; }
    };
    dialog.querySelector('input').onchange = async event => {
      const file = event.target.files[0];
      if (!file) return;
      try {
        if (file.size > LIMIT) throw new Error('Language packs must be at most 2 MiB.');
        const candidate = validate(JSON.parse(await file.text()));
        const translations = Object.fromEntries(Object.entries(candidate.translations));
        if (!engine) throw new Error('The local translation engine is unavailable. Keep using English.');
        engine.addResourceBundle(candidate.locale, 'translation', translations, false, true);
        imported = candidate;
        await choose(candidate.locale); refresh();
        status.textContent = text('Language pack imported. Missing entries use English.');
      } catch (error) { status.textContent = error.message; refresh(); }
      event.target.value = '';
    };
    const trigger = document.createElement('button');
    trigger.type = 'button'; trigger.className = 'pill'; trigger.textContent = 'LANGUAGE';
    trigger.setAttribute('aria-label', 'Interface language');
    trigger.onclick = () => { refresh(); dialog.showModal(); };
    const settings = document.getElementById('drawer-settings');
    const header = document.querySelector('#hwbar .status, header, nav');
    (settings || header || document.body).append(trigger);
    capture(dialog); capture(trigger);
  }
  capture(document.body);
  mount();
  const ready = (async () => {
    try {
      const response = await fetch('/language/en.json');
      if (!response.ok) throw new Error('English catalog unavailable');
      const value = await response.json();
      if (value.schema !== 1 || value.locale !== 'en' || !value.translations)
        throw new Error('Invalid English catalog');
      catalog = value;
      engine?.addResourceBundle('en', 'translation', catalog.translations, false, true);
      try {
        const saved = JSON.parse(localStorage.getItem(STORAGE) || 'null');
        if (saved?.pack) {
          imported = validate(saved.pack);
          engine?.addResourceBundle(imported.locale, 'translation', imported.translations, false, true);
          if (saved.locale === imported.locale) selected = imported.locale;
        }
      } catch { imported = null; selected = 'en'; }
      if (engine) await engine.changeLanguage(selected);
      apply();
    } catch { selected = 'en'; /* English source remains fully usable offline. */ }
  })();
  window.TCLanguage = Object.freeze({t: text, ready, validate,
    get locale() { return selected; }, get catalog() { return catalog; }});
})();
