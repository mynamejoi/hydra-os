/* The Shop's buying states, after the kit's
   script. Each card keeps where it stands from Home's server (GET /api/shop): "In your rail", "<Page> 1.2 is ready" with
   Update, "Update Hydra-OS first." or "Adding <Page>…", and "Get <Page>" only while it's on sale, which opens the
   checkout in the person's own browser. A key pasted at the foot goes to Home's server at once, with no Add, and
   leaves the field (Return sends one typed by hand);
   while a page is being added or updated the page asks again each second, then says how it went. A page newly in the
   rail opens the Shop again, so the rail shows it, and what was said stays. */
(() => {
  'use strict';
  const kit = window.HydraKit;
  if (!kit || !kit.live) return;
  const { $, $$, send, tip, keep, mend } = kit;
  const cards = $$('.sc[data-page]'), foot = $('#shop-said'), key = $('#shop-key');
  const built = new Map(cards.map(c => [c.dataset.page, c.dataset.state]));
  const railed = s => s === 'in-rail' || s === 'update';
  const shown = v => String(v || '').replace(/^(\d+\.\d+)\.0$/, '$1');
  const LINE = { 'in-rail': () => 'In your rail', update: (c, p) => `${c.dataset.title} ${shown(p.version)} is ready`,
                 'needs-hydra': () => 'Update Hydra-OS first.',
                 adding: (c, p) => `${p.have ? 'Updating' : 'Adding'} ${c.dataset.title}\u2026` };  // said once, on the card
  let working = '', out = null;  // the page being added or updated ('?' until the server names it), and where its line goes

  { const was = keep.get('hydra-shop-said'); keep.set('hydra-shop-said', null); if (foot && typeof was === 'string') foot.textContent = was;
  }

  const draw = d => cards.forEach(c => {
    const p = d.pages.find(x => x && x.id === c.dataset.page); if (!p) return;
    let state = d.working === p.id ? 'adding' : p.state;
    if (built.get(p.id) === 'in-rail' && state !== 'update' && state !== 'adding') state = 'in-rail';  // installed with the rest
    const sale = state === 'available' && /^https:\/\//.test(p.checkout || '');
    c.dataset.state = state;
    c.setAttribute('aria-busy', String(state === 'adding'));
    $('[data-line]', c).textContent = LINE[state] ? LINE[state](c, p) : '';
    $('[data-get]', c).hidden = !sale;
    $('[data-update]', c).hidden = state !== 'update';
    $('[data-connect]', c).className = sale || state === 'update' ? 'alt' : 'cta';
  });

  const look = () => send('GET', '/api/shop').then(d => {
    if (!d || !Array.isArray(d.pages)) { if (working) setTimeout(look, 1000); return; }
    draw(d);
    if (d.working) { working = d.working; setTimeout(look, 1000); return; }
    if (!working) return;
    working = '';
    const said = typeof d.said === 'string' ? d.said : '';
    const fresh = d.pages.find(x => x && x.state === 'in-rail' && built.has(x.id) && !railed(built.get(x.id)));
    if (fresh && keep.get('hydra-shop-opened') !== fresh.id) {  // newly in the rail: the Shop again, so the rail shows it
      keep.set('hydra-shop-opened', fresh.id);
      keep.set('hydra-shop-said', said);
      keep.set('hydra-keep', { path: location.pathname, y: scrollY, id: '', back: null, at: Date.now() });
      location.reload();
      return;
    }
    (out || foot).textContent = said; mend(out || foot, d, '');  /* Repair beside it, when Hydra-OS's store needs it */
  });

  const start = (path, body, where) => send('POST', path, body).then(a => {
    out = where;
    mend(where, a, '');
    if (a && a.ok) { where.textContent = ''; working = body.id || '?'; look(); return; }  // the card says it's adding, once
    where.textContent = a && typeof a.said === 'string' && a.said ? a.said
      : path === '/api/shop/key' ? 'Not sent. Paste the key in the chat beside this page.' : 'Not sent. Try again in a moment.';
  });

  cards.forEach(c => {
    const get = $('[data-get]', c), update = $('[data-update]', c), said = $('[data-said]', c);
    get.addEventListener('click', () => send('POST', '/api/shop/checkout', { id: c.dataset.page })
      .then(a => tip(get, a && typeof a.said === 'string' && a.said ? a.said : "The checkout didn't open. Try again.")));
    update.addEventListener('click', () => { update.hidden = true; start('/api/shop/update', { id: c.dataset.page }, said); });
  });

  if (key && foot) {  /* a paste sends it as it lands, Return a typed one, and the field is cleared at once */
    let sending = false;
    const go = () => {
      const k = key.value.trim();
      if (!k || sending) return;
      sending = true; key.value = '';
      start('/api/shop/key', { key: k }, foot).then(() => { sending = false; });
    };
    key.addEventListener('paste', () => setTimeout(go, 0));
    key.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); go(); } });
  }
  look();
})();
