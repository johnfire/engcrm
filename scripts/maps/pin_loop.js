// Google Maps pin loop for the "Cold call candidates" list (see docs/maps-pinning.md).
//
// Runs in the browser on google.com/maps, signed in to Chris's own Google account. Load it
// with eval, then call window.__pinLoop(items) with the items scripts/maps/pin_queue.py
// prints. Each item is matched in one of two ways:
//   - with lat/lon (the CRM knows where it is): the Maps place must be within maxDist
//     metres (default 500) and its name must match;
//   - without (an imported lead): searched by name + address; the place must be within
//     150 km of home, show the item's postcode (or, without one, its website or town),
//     and its name must match.
// Name match: the normalised words overlap by Jaccard >= 0.6, or the item's `expect`
// regex matches the Maps title. Closed places are never saved, an already-saved place is
// never toggled off, and every save is confirmed by re-opening the Save menu. The Save menu
// is always opened fresh for the place on screen (a menu left open is never read), and a
// tick counts only when the Save button also says "Saved".
// Results go to sessionStorage '__pins' (statuses: saved, already, closed, too_far,
// plz_mismatch, loc_mismatch, name_mismatch, no_match, no_card, no_menu, unverified,
// error); window.__pinResults() returns them as JSON for scripts/maps/apply_pins.py.
(() => {
  const KEY = '__pins';
  const LIST = /Cold call candidates/;
  const NOT_LIST = /visited/;
  const HOME = [48.1588074, 10.8309762];
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const q = s => document.querySelector(s);
  const hav = (a, b, c, d) => {
    const p = Math.PI / 180;
    const x = Math.sin((c - a) * p / 2) ** 2 + Math.cos(a * p) * Math.cos(c * p) * Math.sin((d - b) * p / 2) ** 2;
    return 12742000 * Math.asin(Math.sqrt(x));
  };
  const byLocation = it => it.lat != null && it.lon != null;
  const norm = s => (s || '').toLowerCase()
    .replace(/\b(gmbh|co|kg|ag|ug|mbh|gbr|inh|und|e\.k|ek|ev|e\.v)\b\.?/g, ' ')
    .replace(/[^a-z0-9äöüß]+/g, ' ').trim();
  const toks = s => new Set(norm(s).split(' ').filter(t => t.length >= 3));
  const jaccardOk = (a, b) => {
    const A = toks(a), B = toks(b); let n = 0;
    A.forEach(t => { if (B.has(t)) n++; });
    const u = A.size + B.size - n;
    return !!u && n / u >= 0.6;
  };
  // An imported lead (no coordinates) is also accepted when the Maps title contains every word
  // of its core name ('FRISTO SE' in 'FRISTO SE Zentrale Buchloe'); its postcode must still match.
  const containsAll = (core, title) => {
    const want = toks(core), have = toks(title);
    return want.size > 0 && [...want].some(t => t.length >= 4) && [...want].every(t => have.has(t));
  };
  const nameOk = (it, title) => it.expect ? new RegExp(it.expect, 'i').test(title)
    : jaccardOk(it.name, title) || (!!it.alias && jaccardOk(it.alias, title))
      || (!byLocation(it) && containsAll(it.alias || it.name, title));
  const coords = url => {
    const la = (url.match(/!3d(-?[\d.]+)/) || [])[1], lo = (url.match(/!4d(-?[\d.]+)/) || [])[1];
    return la ? [parseFloat(la), parseFloat(lo)] : null;
  };
  const cardUp = () => !!q('button[data-item-id="address"]');
  const setSearch = text => {
    const box = q('input[name="q"]');
    if (!box) throw new Error('no search box');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(box, text);
    box.dispatchEvent(new Event('input', {bubbles: true}));
    // Enter, not the Search button: in the current layout a click leaves the old results.
    box.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));
  };
  // "Results" (a list's heading) and "Sponsored" (an ad block) are h1s too; neither is a place.
  const NOT_TITLE = /^(Results|Sponsored)?$/;
  // The place card's title: the h1 in the place's own panel ([role=main], labelled with the
  // place name), never just the first h1 on the page, which can be the list's "Results".
  const placeTitle = () => {
    const panel = [...document.querySelectorAll('[role=main]')]
      .find(m => m.ariaLabel && !NOT_TITLE.test(m.ariaLabel.trim()));
    const own = panel && panel.querySelector('h1');
    const text = own && own.innerText.trim();
    if (text && !NOT_TITLE.test(text)) return text;
    return [...document.querySelectorAll('h1')].map(h => h.innerText.trim()).find(t => !NOT_TITLE.test(t)) || null;
  };
  const listUp = () => !!document.querySelector('a.hfpxzc');
  // What the page shows: a place card (with its title), a results list, or nothing usable yet.
  const pageState = () => cardUp() && placeTitle() ? 'card:' + placeTitle() : (listUp() && !cardUp() ? 'list' : null);
  // Wait (up to 15 s) until the page shows a new card or list and has held it for two polls,
  // so a passing in-between state (list heading under a loading card) is never read. Two
  // companies at one Maps place keep the same card: after the wait, a changed URL is accepted.
  // A results list is this search's only once the URL carries the search: the previous
  // search's list can resurface first (5 Nov 2026: "Ernst Höbel" was matched against the
  // SPITZKE results still on screen).
  const urlHasQuery = query => {
    const path = decodeURIComponent(location.pathname).replace(/\+/g, ' ').toLowerCase();
    const word = [...toks(query)].find(t => t.length >= 4) || [...toks(query)][0];
    return !word || path.includes(word);
  };
  const settle = async (beforeUrl, beforeState, query = null) => {
    let last = null;
    const current = () => {
      const s = pageState();
      return s === 'list' && query && !urlHasQuery(query) ? null : s;
    };
    for (let i = 0; i < 30; i++) {
      await sleep(500);
      const now = current();
      if (now && now !== beforeState && now === last) return true;
      last = now;
    }
    return location.href !== beforeUrl && !!current();
  };
  const menuItems = () => [...document.querySelectorAll('[role=menuitemradio]')].filter(e => e.offsetParent);
  const radio = () => menuItems().find(e => LIST.test(e.innerText) && !NOT_LIST.test(e.innerText));
  const saveButton = () => q('button[data-value="Save"], button[data-value^="Saved"]');
  // Escape must go to the focused element inside the menu: sent to document it is ignored and
  // the menu stays open — and a menu left open is read for the NEXT place (5 Nov 2026: one
  // ticked menu made ~95 places read as "already pinned"). Returns true once no menu shows.
  const closeMenu = async () => {
    for (let i = 0; i < 4 && menuItems().length; i++) {
      (document.activeElement || document.body)
        .dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true}));
      await sleep(400);
    }
    return !menuItems().length;
  };
  // Always a freshly opened menu for the place on screen: never one that was already open.
  const openMenu = async () => {
    if (!await closeMenu()) return null;
    const btn = saveButton();
    if (!btn) return null;
    btn.click();
    for (let i = 0; i < 8; i++) { await sleep(400); const m = radio(); if (m) return m; }
    return null;
  };
  // A place on no list shows "Save", one on any list "Saved (…)": a ticked menu entry under a
  // plain "Save" button cannot be true.
  const onSomeList = () => /^Saved/.test((saveButton() || {}).getAttribute?.('data-value') || '');
  const results = () => JSON.parse(sessionStorage.getItem(KEY) || '{}');
  const store = r => { const res = results(); res[r.id] = r; sessionStorage.setItem(KEY, JSON.stringify(res)); };
  const placeCheck = (it, r, c) => {
    if (byLocation(it)) return (!c || r.dist > (it.maxDist || 500)) ? 'too_far' : null;
    if (!c || hav(HOME[0], HOME[1], c[0], c[1]) > 150000) return 'too_far';
    if (it.plz) return (r.address || '').includes(it.plz) ? null : 'plz_mismatch';
    const siteOk = it.site && (r.website || '').toLowerCase().includes(it.site);
    const townOk = it.city && (r.address || '').toLowerCase().includes(it.city.toLowerCase().split(' ')[0]);
    return (siteOk || townOk) ? null : 'loc_mismatch';
  };
  const pickFromList = (it) => {
    const links = [...document.querySelectorAll('a.hfpxzc')]
      .map(a => ({a, t: a.getAttribute('aria-label') || '', c: coords(a.href)})).filter(x => x.c);
    const near = x => byLocation(it) ? hav(it.lat, it.lon, x.c[0], x.c[1]) <= (it.maxDist || 500)
                                     : hav(HOME[0], HOME[1], x.c[0], x.c[1]) <= 150000;
    const ranked = links.filter(x => near(x) && nameOk(it, x.t));
    if (byLocation(it)) ranked.sort((x, y) => hav(it.lat, it.lon, x.c[0], x.c[1]) - hav(it.lat, it.lon, y.c[0], y.c[1]));
    return {ranked, links};
  };
  const readCard = (it, r) => {
    const url = location.href, c = coords(url);
    r.title = placeTitle() || document.title.replace(/ - Google Maps$/, '');
    r.key = (url.match(/!1s(0x[0-9a-f]+:0x[0-9a-f]+)/) || [])[1] || null;
    r.lat = c ? c[0] : null; r.lon = c ? c[1] : null;
    r.address = ((q('button[data-item-id="address"]') || {}).ariaLabel || '').replace(/^Address:\s*/, '').trim() || null;
    r.phone = ((q('button[data-item-id^="phone"]') || {}).ariaLabel || '').replace(/^Phone:\s*/, '').trim() || null;
    r.website = (q('a[data-item-id="authority"]') || {}).href || null;
    r.dist = c && byLocation(it) ? Math.round(hav(it.lat, it.lon, c[0], c[1])) : null;
    r.closed = (document.body.innerText.slice(0, 3000).match(/(Permanently|Temporarily) closed/i) || [null])[0];
    return c;
  };
  const save = async (r) => {
    const savedBefore = onSomeList();
    const m = await openMenu();
    if (!m) return 'no_menu';
    if (m.getAttribute('aria-checked') === 'true') {
      await closeMenu();
      return savedBefore ? 'already' : 'unverified';
    }
    m.click(); await sleep(3000);
    await closeMenu();
    const m2 = await openMenu();
    const status = (m2 && m2.getAttribute('aria-checked') === 'true' && onSomeList()) ? 'saved' : 'unverified';
    await closeMenu();
    return status;
  };
  window.__pinLoop = async (items) => {
    for (const it of items) {
      const done = results()[it.id];
      if (done && done.status !== 'unverified') continue;
      const r = {id: it.id, crm: it.name, status: 'error'};
      try {
        const where = byLocation(it) ? (it.city ? ' ' + it.city : '') : ' ' + (it.addr || it.city || '');
        const beforeUrl = location.href, beforeState = pageState();
        const query = (it.alias || it.name) + where;
        await closeMenu();
        setSearch(query);
        if (!await settle(beforeUrl, beforeState, query)) { r.status = 'no_card'; store(r); continue; }
        if (pageState() === 'list') {
          const {ranked, links} = pickFromList(it);
          if (!ranked.length) { r.status = 'no_match'; r.results = links.slice(0, 3).map(x => x.t); store(r); continue; }
          const listUrl = location.href;
          ranked[0].a.click();
          await settle(listUrl, 'list');
        }
        if (!cardUp() || !placeTitle()) { r.status = 'no_card'; store(r); continue; }
        const c = readCard(it, r);
        r.status = placeCheck(it, r, c) || (!nameOk(it, r.title) ? 'name_mismatch' : (r.closed ? 'closed' : await save(r)));
      } catch (e) { r.status = 'error'; r.err = String(e).slice(0, 100); }
      store(r);
    }
    return Object.keys(results()).length;
  };
  window.__pinResults = () => JSON.stringify(Object.values(results()));
  return 'pin loop ready';
})();
