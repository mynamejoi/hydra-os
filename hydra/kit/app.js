/* Hydra-OS's kit: the one script every page loads, last in its body, from Home's server at /kit/app.js.
   It paints the sky for the hour, turns the glass light or dark, and runs what a page can do: answer a question,
   save an entry or a goal with Undo, hand Claude a request, tell Claude where the person is, and reload when the
   page has been rebuilt. It talks only to Home's server on this Mac, and a page opened with no server still reads:
   its saves say "Not saved." */
(() => {
  'use strict';
  const root = document.documentElement, body = document.body, st = root.style;
  const q = new URLSearchParams(location.search);
  const $ = (s, el) => (el || document).querySelector(s), $$ = (s, el) => [...(el || document).querySelectorAll(s)];
  const APP = body.dataset.app || '';
  const meta = n => { const m = $(`meta[name="${n}"]`); return m ? m.content : ''; };
  const keep = {
    get(k) { try { return JSON.parse(sessionStorage.getItem(k)); } catch (e) { return null; } },
    set(k, v) { try { v == null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  };

  /* The clock and the sun. The sky always keeps the real time; only the glass and the type change with the appearance.
     For checks only: ?t=HH:MM pins the time, ?d=YYYY-MM-DD the day, ?tz= the minutes west of Greenwich,
     ?at=lat,lon the place, and ?theme=light|dark the glass. */
  const clamp = x => Math.max(0, Math.min(1, x)), ss = (a, b, x) => { const u = clamp((x - a) / (b - a)); return u * u * (3 - 2 * u); };
  const hm = s => { const [h, m] = s.split(':').map(Number); return h * 60 + (m || 0); };
  const pv = /^\d{1,2}:\d{2}$/.test(q.get('t') || '') ? hm(q.get('t')) : null;
  const nowMin = () => { if (pv != null) return pv; const d = new Date(); return d.getHours() * 60 + d.getMinutes(); };
  const today = () => { const m = /^(\d{4})-(\d\d)-(\d\d)$/.exec(q.get('d') || ''); return m ? new Date(+m[1], +m[2] - 1, +m[3], 12) : new Date(); };
  /* The place is the one Claude saved in you.json, which every page carries as it was when the page was built. The
     newest-built page's place, or its having none, is kept for the others, so a page built before the place was set or
     cleared doesn't make the sky jump. Without one the sky goes by this Mac's time zone: the middle of the zone, at a
     middle latitude, south when the zone's summer falls in January. Sunrise is then right to within the hour. */
  const place = (() => {
    const at = /^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$/.exec(q.get('at') || '');
    if (at) return { lat: +at[1], lon: +at[2] };
    let lat = parseFloat(body.dataset.lat), lon = parseFloat(body.dataset.lon);
    const mine = Date.parse(meta('built-at')) || 0;
    let kept = null; try { kept = JSON.parse(localStorage.getItem('hydra-place')); } catch (e) {}
    if (kept && typeof kept.built === 'number' && kept.built > mine) { lat = kept.lat; lon = kept.lon; }
    else try { localStorage.setItem('hydra-place', JSON.stringify({ lat: Number.isFinite(lat) ? lat : null, lon: Number.isFinite(lon) ? lon : null, built: mine })); } catch (e) {}
    if (Number.isFinite(lat) && Number.isFinite(lon)) return { lat, lon };
    const y = new Date().getFullYear(), jan = new Date(y, 0, 1).getTimezoneOffset(), jul = new Date(y, 6, 1).getTimezoneOffset();
    return { lat: jan < jul ? -37 : 40, lon: -Math.max(jan, jul) / 4 };
  })();
  const RAD = Math.PI / 180;
  const sunOn = d => {
    const tz = /^-?\d+$/.test(q.get('tz') || '') ? +q.get('tz') : d.getTimezoneOffset();
    const N = Math.floor((d - new Date(d.getFullYear(), 0, 0)) / 864e5);
    const decl = -23.44 * Math.cos(2 * Math.PI / 365 * (N + 10)) * RAD, B = 2 * Math.PI * (N - 81) / 364;
    const eq = 9.87 * Math.sin(2 * B) - 7.53 * Math.cos(B) - 1.5 * Math.sin(B), noon = 720 - 4 * place.lon - eq - tz;
    const sl = Math.sin(place.lat * RAD) * Math.sin(decl), cl = Math.cos(place.lat * RAD) * Math.cos(decl);
    const H = Math.acos(Math.max(-1, Math.min(1, (Math.sin(-0.833 * RAD) - sl) / cl))) / RAD * 4;
    return { rise: noon - H, set: noon + H, noon, el: t => Math.asin(sl + cl * Math.cos((t - noon) / 4 * RAD)) / RAD };
  };
  /* Colours blend in OKLab, so a sky between two moments stays clean instead of going grey. */
  const lin = c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4, gam = c => c <= .0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - .055;
  const toLab = h => { const [r, g, b] = [1, 3, 5].map(i => lin(parseInt(h.slice(i, i + 2), 16) / 255)), l = Math.cbrt(.4122214708 * r + .5363325363 * g + .0514459929 * b), m = Math.cbrt(.2119034982 * r + .6806995451 * g + .1073969566 * b), s = Math.cbrt(.0883024619 * r + .2817188376 * g + .6299787005 * b); return [.2104542553 * l + .793617785 * m - .0040720468 * s, 1.9779984951 * l - 2.428592205 * m + .4505937099 * s, .0259040371 * l + .7827717662 * m - .808675766 * s]; };
  const toHex = ([L, a, b]) => { const l = (L + .3963377774 * a + .2158037573 * b) ** 3, m = (L - .1055613458 * a - .0638541728 * b) ** 3, s = (L - .0894841775 * a - 1.291485548 * b) ** 3; return '#' + [4.0767416621 * l - 3.3077115913 * m + .2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - .3413193965 * s, -.0041960863 * l - .7034186147 * m + 1.707614701 * s].map(c => Math.round(255 * Math.max(0, Math.min(1, gam(c)))).toString(16).padStart(2, '0')).join(''); };
  const mix = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);
  /* The palette: four stops from the top of the sky to the horizon, keyed to the sun's height in degrees, from full
     night at 14 below the horizon, through twilight, sunrise or sunset and the golden hour, to noon. Mornings run
     pinker, evenings more gold. Between two keys the sky is a plain blend, so it never steps. By day each stop sits
     15% closer to a gentler blue, eased in as the sun climbs its first 12 degrees. */
  const GENTLE = ['#3d7ac4', '#5a96da', '#8fbfee', '#cbe3f7'].map(toLab);
  const K = (e, ...c) => [e, c.map((h, j) => mix(toLab(h), GENTLE[j], .15 * ss(0, 12, e)))];
  const NIGHT = ['#050a1c', '#0a1330', '#111e47', '#1a2b5c'], DAY = ['#144c9c', '#2068bc', '#5a9ce0', '#b4d6f3'], NOON = ['#0f4a9e', '#1a63ba', '#4a93de', '#9cc9f1'];
  const AM = [K(-14, ...NIGHT), K(-8, '#090f2a', '#131c48', '#2a2a62', '#4c3d74'), K(-4, '#0e1738', '#232c66', '#5a4a8c', '#a8789c'), K(-.8, '#1c2c6c', '#4a4f98', '#c58fa8', '#f8cdb0'), K(5, '#1b3f8c', '#3f63b0', '#b3a6d2', '#f8d6bc'), K(12, '#18499a', '#3069b9', '#93b2e0', '#f2dccc'), K(24, '#15509f', '#2a6fc0', '#72abe5', '#dee5ee'), K(36, ...DAY), K(60, ...NOON)];
  const PM = [K(-14, ...NIGHT), K(-8, '#080e26', '#101a42', '#22265a', '#3d3468'), K(-4, '#0d1536', '#1f2760', '#4a3c82', '#8f5a86'), K(-.8, '#1a2866', '#3d4390', '#b5688a', '#f2a56c'), K(4, '#1b3c88', '#3f5aa6', '#c08fb4', '#f7b878'), K(10, '#1c4490', '#3a66b0', '#b7b0d0', '#f5cf9a'), K(22, '#174a98', '#2767b8', '#74a6de', '#d2dcea'), K(34, ...DAY), K(60, ...NOON)];
  const skyStops = (sun, t) => {
    const e = sun.el(t), ks = (t - sun.noon + 1440) % 1440 > 720 ? AM : PM;
    let i = 1; while (i < ks.length - 1 && ks[i][0] < e) i++;
    const a = ks[i - 1], b = ks[i], u = clamp((e - a[0]) / (b[0] - a[0]));
    return a[1].map((s, j) => toHex(mix(s, b[1][j], u)));
  };
  /* Appearance: Follow the sun unless the person chose Light, Dark or System (yours/settings.json). The page carries
     the choice it was built with; the poll brings a newer one within a second, and it's remembered for the next page. */
  const explicit = /^(light|dark)$/.test(q.get('theme') || '') ? q.get('theme') : '';
  const MODES = ['sun', 'light', 'dark', 'system'], sysDark = matchMedia('(prefers-color-scheme: dark)');
  let mode = (() => { let m = null; try { m = localStorage.getItem('hydra-appearance'); } catch (e) {} return MODES.includes(m) ? m : MODES.includes(body.dataset.appearance) ? body.dataset.appearance : 'sun'; })();
  const skyEl = $('.sky'), SUN = ['#ff9a58', '#ffd9a3', '#fffbea'].map(toLab), painted = [];
  const paintSky = () => {
    const sun = sunOn(today()), t = nowMin(), e = sun.el(t);
    if (skyEl) {
      const c = skyStops(sun, t), g = `${c[0]},${c[1]} var(--p1),${c[2]} var(--p2),${c[3]}`;
      skyEl.style.backgroundImage = `linear-gradient(${g})`; skyEl.style.backgroundImage = `linear-gradient(in oklab,${g})`;
    }
    /* The sun crosses from sunrise to sunset, reddens as it nears the horizon, then sinks and fades. The moon comes
       in once the sky is dark, by then a little way up its own path from sunset to sunrise. */
    const f = clamp((t - sun.rise) / (sun.set - sun.rise)), nf = clamp((t - sun.set + 1440) % 1440 / (1440 - (sun.set - sun.rise)));
    const V = { sx: f, sy: Math.sin(Math.PI * f), so: ss(-1.6, 1.2, e), sk: ss(2.5, -2, e), sg: 1 + .7 * (1 - ss(0, 14, e)), mx: nf, my: Math.sin(Math.PI * nf), mo: ss(-5, -9, e) * ss(0, .05, nf) * ss(1, .95, nf), staro: ss(-5, -13, e) * .42 };
    for (const k in V) st.setProperty('--' + k, V[k].toFixed(4));
    st.setProperty('--sunc', toHex(mix(mix(SUN[0], SUN[1], ss(-1, 7, e)), SUN[2], ss(7, 30, e))));
    /* An app's colour glows low in the sky, a little stronger as the light goes. Home has none. */
    if (APP && APP !== 'home') st.setProperty('--glo', (.16 + .4 * ss(14, -5, e)).toFixed(3));
    /* Light or dark follows the sky, not the clock: the glass turns in the middle of dusk and of dawn, when the sun is 4 degrees under the horizon. */
    root.dataset.theme = explicit || (mode === 'light' || mode === 'dark' ? mode : mode === 'system' ? (sysDark.matches ? 'dark' : 'light') : e < -4 ? 'dark' : 'light');
    const now = { t, e, sun };
    painted.forEach(fn => fn(now));
    return now;
  };
  /* The footer's "Updated today at 11:16 pm." is the build's own day, said as the reader's today, yesterday or the day. */
  const updated = $('[data-updated]');
  if (updated) painted.push(() => {
    const b = new Date(updated.dataset.updated + 'T12:00:00'), t = today(), n = Math.round((new Date(t.getFullYear(), t.getMonth(), t.getDate(), 12) - b) / 864e5);
    const day = n === 0 ? 'today' : n === 1 ? 'yesterday' : `${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][b.getDay()]} ${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][b.getMonth()]} ${b.getDate()}`;
    if (isFinite(n)) updated.textContent = updated.textContent.replace(/^Updated .*? at /, `Updated ${day} at `);
  });
  const setMode = m => { if (!MODES.includes(m) || m === mode) return; mode = m; try { localStorage.setItem('hydra-appearance', m); } catch (e) {} paintSky(); };
  sysDark.addEventListener('change', () => { if (mode === 'system') paintSky(); });
  setInterval(paintSky, 60000);
  /* The theme's colours ease only after the first paint. */
  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.add('eased')));

  /* Talking to Home's server. Every answer is {ok, said}; anything else, or no answer inside 40 seconds, is a save that didn't happen. */
  const LIVE = location.protocol === 'http:' || location.protocol === 'https:';
  const send = (method, path, payload) => {
    if (!LIVE) return Promise.resolve({ ok: false, said: '' });
    const stop = new AbortController(), timer = setTimeout(() => stop.abort(), 40000);
    const init = { method, signal: stop.signal, credentials: 'same-origin', cache: 'no-store' };
    if (payload !== undefined) { init.headers = { 'Content-Type': 'application/json' }; init.body = JSON.stringify(payload); }
    return fetch(path, init).then(r => r.json()).then(a => a && typeof a === 'object' ? a : null, () => null).then(a => { clearTimeout(timer); return a; });
  };
  const act = (app, action, fields, token) => send('POST', `/api/act/${encodeURIComponent(app)}/${encodeURIComponent(action)}`, token ? { fields, token } : { fields })
    .then(a => a && typeof a.ok === 'boolean' ? { ok: a.ok, said: typeof a.said === 'string' ? a.said : '', undo: a.undo && typeof a.undo === 'object' ? a.undo : null,
                                                  token: typeof a.token === 'string' ? a.token : '', repair: a.repair === true } : { ok: false, said: '', undo: null, token: '', repair: false });
  const notSaved = a => 'Not saved.' + (a.said ? ' ' + a.said : '');
  /* An answer Repair can mend ("repair": true) puts a Repair button beside its line, handing Claude the repair of the page
     it's about, or of Hydra-OS itself on Home's own pages. Any answer that doesn't ask for it takes the button away. */
  const mend = (line, a, app) => {
    if (!line || !line.parentElement) return;
    const next = line.nextElementSibling, had = next && next.classList.contains('rpr') ? next : null;
    if (!a || a.repair !== true) { if (had) had.remove(); return; }
    if (had) return;
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'cta rpr'; b.dataset.connect = ''; b.dataset.kind = 'repair';
    b.dataset.app = ['home', 'help', 'privacy', 'shop'].includes(app) ? '' : String(app || ''); b.textContent = 'Repair';
    line.after(b);
  };
  const flash = (el, text, ms) => { el.textContent = text; clearTimeout(el._t); if (ms) el._t = setTimeout(() => { if (el.textContent === text) el.textContent = ''; }, ms); };
  let busy = 0, holding = 0;  // holding: an item's Undo, or a read-back's Confirm, is showing, so the page doesn't reload under it
  const during = p => { busy++; const done = () => { busy--; }; p.then(done, done); return p; };

  /* On a phone a field's example is a shorter one, so it shows whole. */
  if (matchMedia('(max-width:480px)').matches) $$('input[data-short]').forEach(i => { i.placeholder = i.dataset.short; });

  /* A field: Return saves it, and Save shows once there's something to save. */
  const field = (inp, save) => {
    const go = inp.parentElement.querySelector('.save');
    const sync = () => { if (go) go.hidden = !inp.value.trim(); };
    inp.addEventListener('input', e => { if (e.isTrusted) delete inp.dataset.back; sync(); });
    inp.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); save(); } });
    if (go) go.addEventListener('click', save);
    sync();
    return sync;
  };
  const line = inp => inp.value.trim().replace(/\s+/g, ' ');

  /* Claude asks. A typed answer saves on Return; a pick saves on its tap. Either shows its saved line
     with Undo, and the answered question stays in place. What was typed is kept for this visit only, in this
     browser, so Undo can hand it back: the record's own copy never comes to a page that didn't write it. */
  $$('.ask').forEach(ask => {
    const app = ask.dataset.app, id = ask.dataset.q, kind = ask.dataset.kind || 'words', key = `hydra-said:${app}:${id}`;
    const msg = $('.msg', ask), ans = $('.ans', ask), undo = $('.undo', ask);
    let last = keep.get('hydra-last:' + app + ':' + id);
    const remember = l => { last = l; keep.set('hydra-last:' + app + ':' + id, l); };
    const takeBack = () => {
      const f = last && last.undo ? last.undo : { question: id, ...(last && last.pick ? { pick: last.pick } : {}) };
      undo.disabled = true;
      return during(act(app, 'unanswer', f)).then(a => { undo.disabled = false; mend(msg, a, app); if (!a.ok) flash(msg, 'Not put back.' + (a.said ? ' ' + a.said : '')); return a.ok; });
    };
    if (kind === 'words') {
      const inp = $('input', ask), fld = $('.fld', ask), said = $('.said', ask);
      if (!ans.hidden && !said.textContent && keep.get(key)) said.textContent = keep.get(key);
      const save = () => {
        const text = line(inp); if (!text || inp.disabled) return;
        inp.disabled = true; ask.setAttribute('aria-busy', 'true'); flash(msg, '');
        during(act(app, 'answer', { question: id, words: text })).then(a => {
          inp.disabled = false; ask.removeAttribute('aria-busy'); mend(msg, a, app);
          if (!a.ok) { flash(msg, notSaved(a)); inp.focus(); return; }
          keep.set(key, text); remember({ undo: a.undo, at: Date.now() });
          inp.value = ''; sync(); fld.hidden = true; ans.hidden = false; said.textContent = text; undo.focus();  /* shown, then filled, so its live region says it */
        });
      };
      const sync = field(inp, save);
      undo.addEventListener('click', () => takeBack().then(ok => {
        if (!ok) return;
        const text = keep.get(key) || ''; keep.set(key, null); remember(null);
        ans.hidden = true; fld.hidden = false; said.textContent = ''; inp.value = text; inp.dataset.back = '1'; sync(); inp.focus(); flash(msg, 'Put back.', 2000);
      }));
    } else {
      const picks = $$('.pk', ask), one = kind === 'one', attr = one ? 'aria-checked' : 'aria-pressed', only = ask.dataset.only || '';
      const on = p => p.getAttribute(attr) === 'true', set = (p, v) => p.setAttribute(attr, String(v));
      const sv = $('.sv', ask), show = () => { sv.hidden = !picks.some(on); };
      /* One of a set moves with the arrow keys and is picked with Space or Return, so moving never saves. */
      const rove = () => { if (!one) return; const cur = picks.find(on) || picks[0]; picks.forEach(p => { p.tabIndex = p === cur ? 0 : -1; }); };
      picks.forEach((p, i) => {
        p.addEventListener('click', () => {
          if (p.getAttribute('aria-busy') === 'true' || (one && on(p))) return;
          const want = one ? true : !on(p), f = { question: id, pick: p.dataset.pick };
          if (!one) f.on = want ? 'yes' : 'no';
          p.setAttribute('aria-busy', 'true'); flash(msg, '');
          during(act(app, 'answer', f)).then(a => {
            p.removeAttribute('aria-busy'); mend(msg, a, app);
            if (!a.ok) { flash(msg, notSaved(a)); return; }
            const was = picks.filter(on).map(x => x.dataset.pick);
            if (one) picks.forEach(x => set(x, x === p));
            else { set(p, want); if (want) picks.forEach(x => { if (x !== p && (p.dataset.pick === only || x.dataset.pick === only)) set(x, false); }); }
            remember({ undo: a.undo, pick: p.dataset.pick, was, at: Date.now() });
            rove(); show(); undo.focus();
          });
        });
        if (one) p.addEventListener('keydown', e => {
          const d = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0;
          if (d) { e.preventDefault(); picks[(i + d + picks.length) % picks.length].focus(); }
        });
      });
      undo.addEventListener('click', () => takeBack().then(ok => {
        if (!ok) return;
        const was = last && last.was ? last.was : []; picks.forEach(x => set(x, was.includes(x.dataset.pick)));
        const back = picks.find(x => last && x.dataset.pick === last.pick) || picks[0]; remember(null);
        rove(); show(); back.focus(); flash(msg, 'Put back.', 2000);
      }));
      rove(); show();
    }
    /* Escape leaves Undo, back to the question. */
    undo.addEventListener('keydown', e => { if (e.key === 'Escape') { const to = $('input:not([hidden]),.pk[tabindex="0"],.pk', ask); if (to && !to.closest('[hidden]')) to.focus(); else undo.blur(); } });
  });

  /* An entry: one line, saved through the action its section names, with any fixed fields beside the typed words.
     What the app says back shows under it, with Undo for ten seconds. The goals band's field is one of these. */
  const pending = () => (keep.get('hydra-undo') || []).filter(u => Date.now() - u.at < 10000);
  $$('.ent').forEach(ent => {
    const app = ent.dataset.app, action = ent.dataset.act, back = ent.dataset.undo || '', key = ent.id || `${app}:${action}`;
    const inp = $('input', ent), stat = $('.svl span', ent), undo = $('.svl .undo', ent);
    let fixed = {}; try { fixed = JSON.parse(ent.dataset.fixed || '{}') || {}; } catch (e) {}
    /* An undo runs with the save's own undo answer when it gives one, else with those of the save's fields that the undo takes. */
    const takes = (ent.dataset.takes || '').split(' ').filter(Boolean);
    let mine = null, timer = 0;
    const offer = u => {
      mine = u; stat.textContent = u.said; undo.hidden = !back; clearTimeout(timer);
      timer = setTimeout(() => { if (document.activeElement === undo) inp.focus(); undo.hidden = true; mine = null; }, Math.max(0, 10000 - (Date.now() - u.at)));
    };
    const save = () => {
      const text = line(inp); if (!text || inp.disabled) return;
      inp.disabled = true; ent.setAttribute('aria-busy', 'true');
      during(act(app, action, { ...fixed, [ent.dataset.field || 'words']: text })).then(a => {
        inp.disabled = false; ent.removeAttribute('aria-busy'); mend(stat, a, app);
        if (!a.ok) { stat.textContent = notSaved(a); undo.hidden = true; inp.focus(); return; }
        const own = Object.fromEntries(Object.entries({ ...fixed, [ent.dataset.field || 'words']: text }).filter(([k]) => takes.includes(k)));
        const u = { key, said: a.said || 'Saved.', fields: a.undo || own, text, at: Date.now() };
        keep.set('hydra-undo', [...pending().filter(x => x.key !== key), u]);
        inp.value = ''; sync(); offer(u); ent.dispatchEvent(new CustomEvent('hydra:saved'));
        if (back) undo.focus(); else inp.focus();
      });
    };
    const sync = field(inp, save);
    undo.addEventListener('click', () => {
      if (!mine) return; const u = mine; undo.disabled = true;
      during(act(app, back, u.fields)).then(a => {
        undo.disabled = false; mend(stat, a, app);
        if (!a.ok) { stat.textContent = 'Not put back.' + (a.said ? ' ' + a.said : ''); return; }
        keep.set('hydra-undo', pending().filter(x => x.key !== key)); clearTimeout(timer); mine = null;
        undo.hidden = true; inp.value = u.text; inp.dataset.back = '1'; sync(); flash(stat, 'Put back.', 2000);
        ent.dispatchEvent(new CustomEvent('hydra:undone'));
        if (!inp.closest('[hidden]')) inp.focus();
      });
    });
    const was = pending().find(x => x.key === key); if (was) offer(was);
  });

  /* Goals' page. A goal's name in the list shows its detail and hides the rest; the address keeps the pick (?g=), so
     a reload and a link land on it. On a phone the detail sits under the list, so a pick brings it into view. */
  const goalPicks = $$('button.gn[data-pick]');
  if (goalPicks.length) {
    const still = matchMedia('(prefers-reduced-motion:reduce)'), narrow = matchMedia('(max-width:839px)');
    const pickGoal = (id, user) => {
      const d = document.getElementById('d-' + id); if (!d || !d.matches('.detail[data-goal]')) return;
      $$('.detail[data-goal]').forEach(x => { x.hidden = x !== d; });
      goalPicks.forEach(b => { const on = b.dataset.pick === id; b.setAttribute('aria-pressed', String(on)); b.closest('.gr').classList.toggle('sel', on); });
      if (!user) return;
      try { const u = new URL(location.href); u.searchParams.set('g', id); history.replaceState(history.state, '', u); } catch (e) {}
      if (narrow.matches) d.scrollIntoView({ behavior: still.matches ? 'auto' : 'smooth', block: 'start' });
    };
    goalPicks.forEach(b => b.addEventListener('click', () => pickGoal(b.dataset.pick, true)));
    if (q.get('g')) pickGoal(q.get('g'), false);
  }
  /* Change target or date: the line opens in place of the one it changes, holding it as it stands, selected. Return
     saves it through Goals' own action; Cancel or Escape close it. The saved line and its Undo show under the target. */
  $$('.tb[data-edit]').forEach(b => {
    const ent = document.getElementById(b.dataset.edit), meta = b.closest('.meta'); if (!ent || !meta) return;
    const box = $('.edit', ent), inp = box && $('input', box); if (!inp) return;
    const close = focus => { box.hidden = true; meta.hidden = false; if (focus) b.focus(); };
    b.addEventListener('click', () => { meta.hidden = true; box.hidden = false; inp.value = ent.dataset.value || ''; inp.dispatchEvent(new Event('input')); inp.focus(); inp.select(); });
    $('[data-cancel]', box).addEventListener('click', () => close(true));
    box.addEventListener('keydown', e => { if (e.key === 'Escape') { e.preventDefault(); close(true); } });
    ent.addEventListener('hydra:saved', () => close(false));
    ent.addEventListener('hydra:undone', () => close(true));
  });

  /* A file's drop place. Dropping a file there, or choosing one with its button, sends it from disk as
     the body of POST /api/upload/<app>, its name in X-Hydra-File-Name, never read into the page. One file at a time:
     while it goes in, the place says "Sending your file" and takes no other; then it shows Home's server's own line.
     A file dropped anywhere else on the page is ignored, so the window never opens it. */
  const drops = $$('[data-drop]');
  if (drops.length) {
    ['dragover', 'drop'].forEach(type => document.addEventListener(type, e => { if (!e.target.closest || !e.target.closest('[data-drop]')) e.preventDefault(); }));
    const list = kinds => kinds.map(k => '.' + k).join(', ').replace(/, ([^,]*)$/, ' or $1');
    drops.forEach(zone => {
      const app = zone.dataset.drop, kinds = (zone.dataset.accepts || '').split(',').filter(Boolean);
      const btn = $('[data-choose]', zone), input = $('input[type=file]', zone), say = $('.dmsg', zone);
      let sending = false;
      const done = (text, ok) => { sending = false; zone.removeAttribute('aria-busy'); btn.disabled = false; zone.classList.toggle('filed', !!ok); say.textContent = text; };
      const send = file => {
        if (sending || !file) return;
        const ext = ((/\.([A-Za-z0-9]+)$/.exec(file.name) || [])[1] || '').toLowerCase();
        if (kinds.length && !kinds.includes(ext)) { say.textContent = `${zone.dataset.title || 'This page'} takes a ${list(kinds)} file.`; return; }
        if (!file.size) { say.textContent = 'That file is empty.'; return; }
        sending = true; zone.setAttribute('aria-busy', 'true'); btn.disabled = true; zone.classList.remove('filed'); say.textContent = 'Sending your file';
        if (!LIVE) { done("That file couldn't be sent. Drop it again.", false); return; }
        during(fetch(`/api/upload/${encodeURIComponent(app)}`, { method: 'POST', body: file, credentials: 'same-origin', cache: 'no-store',
          headers: { 'X-Hydra-File-Name': encodeURIComponent(file.name), 'Content-Type': 'application/octet-stream' } })
          .then(r => r.json()).then(a => a && typeof a.said === 'string' ? a : null, () => null))
          .then(a => done(a && a.said ? a.said : "That file couldn't be sent. Drop it again.", a && a.ok), () => done("That file couldn't be sent. Drop it again.", false));
      };
      zone.addEventListener('dragover', e => { if (e.dataTransfer && [...e.dataTransfer.types].includes('Files')) { e.preventDefault(); e.dataTransfer.dropEffect = sending ? 'none' : 'copy'; zone.classList.add('over'); } });
      zone.addEventListener('dragleave', e => { if (!zone.contains(e.relatedTarget)) zone.classList.remove('over'); });
      zone.addEventListener('drop', e => {
        e.preventDefault(); zone.classList.remove('over'); if (sending) return;
        const files = e.dataTransfer ? e.dataTransfer.files : null;
        if (files && files.length > 1) say.textContent = 'Drop one file at a time.'; else if (files && files.length) send(files[0]);
      });
      btn.addEventListener('click', () => { if (!sending) input.click(); });
      input.addEventListener('change', () => { const f = input.files && input.files[0]; input.value = ''; send(f); });
    });
    /* Home's tile for an app whose one way in is a file opens its page at #drop: the place comes into view with its
       button ready. The address then lets go of #drop, so a reload in place keeps where the person is. */
    const land = () => {
      if (location.hash !== '#drop') return;
      try { history.replaceState(history.state, '', location.pathname + location.search); } catch (e) {}
      const btn = drops[0].querySelector('[data-choose]');
      drops[0].scrollIntoView({ block: 'center' });
      if (btn) btn.focus({ preventScroll: true });
    };
    land(); addEventListener('hashchange', land);
  }

  /* One click anywhere does the small things: an example fills its field, a Connect files its request, a glyph count holds its note open. */
  let tipT = 0;
  const tip = (el, text) => { $$('.tip').forEach(t => t.remove()); const t = document.createElement('span'); t.className = 'tip'; t.setAttribute('role', 'status'); t.textContent = text; el.append(t); clearTimeout(tipT); tipT = setTimeout(() => t.remove(), 2600); };
  const pins = $$('button.bd');
  document.addEventListener('click', e => {
    const f = e.target.closest('[data-fill]'), c = e.target.closest('[data-connect]'), b = e.target.closest('button.bd');
    if (f) { const i = $(f.dataset.fill); if (i) { i.value = f.textContent; i.dispatchEvent(new Event('input', { bubbles: true })); i.focus(); } }
    /* A tap can't type into Claude's panel. It files the request, and the note says what to do next. */
    if (c && !c.disabled) {
      const r = { kind: c.dataset.kind || 'connect', app: 'app' in c.dataset ? c.dataset.app : APP }; if (c.dataset.service) r.service = c.dataset.service;
      c.disabled = true;
      const NOT = { connect: 'Not sent. Tell Claude what you use.', 'add-app': "Not sent. Tell Claude what you'd like here.", repair: 'Not sent. Try Repair again in a moment.', remove: 'Not sent. Try again in a moment.', review: 'Not sent. Tell Claude to turn on the morning review.',
                    'helpers-on': "Not sent. Tell Claude to turn Hydra-OS's background helpers on.", setup: 'Not sent. Ask Claude to set it up, in the chat beside this page.',
                    update: 'Not sent. Ask Claude to update Hydra-OS, in the chat beside this page.', 'helpers-off': "Not sent. Tell Claude to turn Hydra-OS's background helpers off.", about: 'Not sent. Ask Claude about it, in the chat beside this page.' };
      send('POST', '/api/request', r).then(a => { c.disabled = false; tip(c, a && a.ok ? 'Now say go to Claude' : NOT[r.kind] || NOT.connect); });
    }
    pins.forEach(p => { if (p !== b) p.classList.remove('open'); });
    if (b) b.classList.toggle('open');
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { pins.forEach(p => p.classList.remove('open')); $$('.tip').forEach(t => t.remove()); } });

  /* Telling Claude where the person is: a tap on a block, or on an item in it, sends their ids, at most one a second. Nothing is outlined for it. */
  let sent = 0;
  document.addEventListener('click', e => {
    if (!LIVE || !APP || ['help', 'privacy', 'shop'].includes(APP) || e.target.closest('a,button,input,label,select,summary')) return;  /* Home's own pages aren't an app's */
    const block = e.target.closest('[data-block]'); if (!block) return;
    const item = e.target.closest('[data-item]'), now = Date.now(); if (now - sent < 1000) return; sent = now;
    send('POST', '/api/focus', { app: APP, block: block.dataset.block, item: item && block.contains(item) ? item.dataset.item : '' });
  });

  /* Claude's pointer: the block it names wears the outline and its words until it lets go. */
  let shown = '';
  const point = p => {
    const mine = p && p.app === APP && (!p.until || Date.parse(p.until) > Date.now()) ? p : null, sig = mine ? JSON.stringify([mine.block, mine.items, mine.say]) : '';
    if (sig === shown) return; shown = sig;
    $$('.pointed').forEach(x => x.classList.remove('pointed')); $$('.pnote').forEach(x => x.remove());
    if (!mine) return;
    const block = $(`[data-block="${CSS.escape(String(mine.block || ''))}"]`); if (!block) return;
    block.classList.add('pointed');
    const n = document.createElement('span'); n.className = 'pnote'; n.setAttribute('role', 'status'); n.textContent = typeof mine.say === 'string' && mine.say ? mine.say.slice(0, 60) : 'Claude is talking about this';
    block.append(n);
    const r = block.getBoundingClientRect(); if (r.top < 0 || r.bottom > innerHeight) block.scrollIntoView({ block: 'center', behavior: matchMedia('(prefers-reduced-motion:reduce)').matches ? 'auto' : 'smooth' });
  };

  /* A button that saves on its tap, as Goals' "Set it aside" does, and an item's own buttons:
     its app's action with its fixed fields, then what the app said in the button's place, with Undo for
     ten seconds, focus staying in the item. A read-back action (data-confirm) first shows the app's read-back with
     Confirm and Cancel: Confirm saves with the token the check gave, and Cancel sends nothing. */
  const hold = el => { if (!el.hasAttribute('tabindex')) el.tabIndex = -1; el.focus(); };
  $$('button[data-act]').forEach(b => {
    if (b.closest('.ent, .ask')) return;
    const box = b.parentElement, was = [...box.childNodes];
    let fixed = {}; try { fixed = JSON.parse(b.dataset.fixed || '{}'); } catch (e) {}
    /* What the app said, in the button's place, with Undo for ten seconds; the page waits to reload until Undo has gone,
       so the item and its Undo stay put, then shows what the save built. */
    const saved = a => {
      const said = document.createElement('span'), undo = document.createElement('button');
      said.setAttribute('role', 'status'); said.textContent = a.said || 'Saved.';
      undo.type = 'button'; undo.className = 'undo'; undo.textContent = 'Undo';
      const back = a.undo || (b.dataset.undo ? fixed : null);
      box.replaceChildren(said, ...(back ? [undo] : []));
      if (!back) { hold(said); return; }
      holding++; undo.focus();
      let held = true;
      const let_go = () => { if (held) { held = false; holding--; } };
      const gone = setTimeout(() => { const here = document.activeElement === undo; undo.remove(); if (here) hold(said); let_go(); }, 10000);
      undo.addEventListener('click', () => {
        clearTimeout(gone); undo.disabled = true;
        during(act(b.dataset.app, b.dataset.undo || 'undo', back)).then(r => { said.textContent = r && r.ok ? 'Put back.' : notSaved(r || {}); undo.remove(); mend(said, r, b.dataset.app); hold(said); let_go(); });
      });
    };
    b.addEventListener('click', () => {
      if (b.disabled) return;
      b.disabled = true;
      during(act(b.dataset.app, b.dataset.act, fixed)).then(a => {
        b.disabled = false; mend(b, a, b.dataset.app);
        if (!a || !a.ok) { tip(b, notSaved(a || {})); return; }
        if (b.dataset.confirm !== 'read-back') { saved(a); return; }
        if (!a.token) { tip(b, notSaved({ said: "It couldn't be checked. Try again in a moment." })); return; }
        const said = document.createElement('span'), yes = document.createElement('button'), no = document.createElement('button');
        said.setAttribute('role', 'status'); said.textContent = a.said;
        yes.type = 'button'; yes.className = 'cta'; yes.textContent = 'Confirm';
        no.type = 'button'; no.className = 'alt'; no.textContent = 'Cancel';
        box.replaceChildren(said, yes, no); yes.focus(); holding++;
        no.addEventListener('click', () => { holding--; box.replaceChildren(...was); b.focus(); });
        yes.addEventListener('click', () => {
          if (yes.disabled) return;
          yes.disabled = no.disabled = true;
          during(act(b.dataset.app, b.dataset.act, fixed, a.token)).then(r => {
            holding--;
            if (r && r.ok) { saved(r); return; }
            box.replaceChildren(...was); b.focus(); tip(b, notSaved(r || {})); mend(b, r, b.dataset.app);
          });
        });
      });
    });
  });

  /* A link that leaves the page: Home's server opens it in the person's own browser, never inside the
     pane, where Claude can read what a page shows, and the link says what happened. */
  $$('a[data-open]').forEach(a => a.addEventListener('click', e => {
    e.preventDefault();
    if (!LIVE) { tip(a, "That link opens from Hydra-OS's own pages."); return; }
    send('POST', '/api/open', { link: a.getAttribute('href') }).then(r => tip(a, r && typeof r.said === 'string' && r.said ? r.said : "That link didn't open. Try again in a moment."));
  }));

  /* The layout-changed bar: the page drawn in the layout Claude proposed,
     its changed blocks outlined; Keep makes it the person's own, Undo sets it aside, and either way the page builds again
     and opens in place. */
  const lbar = $('.lbar[data-yours]');
  if (lbar) {
    (lbar.dataset.blocks || '').split(' ').filter(Boolean).forEach(id => { const b = $(`[data-block="${CSS.escape(id)}"]`); if (b) b.classList.add('changed'); });
    const said = $('.said', lbar), app = lbar.dataset.yours;
    const choose = (verb, btn) => {
      if (btn.disabled) return;
      btn.disabled = true;
      during(send('POST', `/api/yours/${encodeURIComponent(app)}/${verb}`, {})).then(a => {
        btn.disabled = false;
        said.textContent = a && a.ok ? (typeof a.said === 'string' ? a.said : '') : notSaved(a || {}); mend(said, a, app);
      });
    };
    $('[data-yours-keep]', lbar).addEventListener('click', e => choose('keep', e.currentTarget));
    $('[data-yours-drop]', lbar).addEventListener('click', e => choose('drop', e.currentTarget));
  }

  /* A page's first-visit hints: each shows until the person has left the page once, remembered
     in this browser. A reload in place isn't leaving. */
  let reloading = false;
  $$('[data-hint]').forEach(h => {
    const k = 'hydra-hint:' + h.dataset.hint;
    let seen = true; try { seen = localStorage.getItem(k) === 'seen'; } catch (e) {}
    if (seen) return;
    h.hidden = false;
    addEventListener('pagehide', () => { if (!reloading) try { localStorage.setItem(k, 'seen'); } catch (e) {} });
  });

  /* An open page asks once a second while it's in front. A newer build reloads it in place, keeping where it was
     scrolled and what had the focus; it waits while something is being typed or saved. Words that Undo handed back
     to a field aren't being typed: they ride through the reload, in this browser alone, and are back in the field after it. */
  const builtAt = Date.parse(meta('built-at')) || 0;
  let misses = 0, wait = 0, heard = [];
  const typing = () => { const a = document.activeElement; return !!a && a.matches('input') && !!a.value && !a.dataset.back; };
  const poll = () => {
    if (!LIVE || !APP || document.visibilityState !== 'visible') return;
    if (wait > 0) { wait--; return; }
    /* The poll names its page, so Home's server knows the page in front: `home` on Home. */
    send('GET', '/api/panel?page=' + encodeURIComponent(APP)).then(p => {
      if (!p) { misses++; wait = misses > 2 ? 9 : 0; return; }
      misses = 0;
      if (typeof p.appearance === 'string') setMode(p.appearance);
      point(p.pointer);
      heard.forEach(fn => fn(p));
      const b = p.built && Date.parse(p.built[APP]);
      if (b && b > builtAt && !busy && !holding && !typing() && keep.get('hydra-reloaded') !== p.built[APP]) {
        keep.set('hydra-reloaded', p.built[APP]);
        const a = document.activeElement;
        keep.set('hydra-keep', { path: location.pathname, y: scrollY, id: a && a.id || '', top: !!a && a === $('h1'), back: a && a.dataset.back ? a.value : null, at: Date.now() });
        reloading = true; location.reload();
      }
    });
  };
  if (LIVE && APP) { setInterval(poll, 1000); document.addEventListener('visibilitychange', poll); }
  { const k = keep.get('hydra-keep'); keep.set('hydra-keep', null);
    if (k && k.path === location.pathname && Date.now() - k.at < 15000) {
      scrollTo(0, k.y); const el = k.id ? document.getElementById(k.id) : k.top ? $('h1') : null;  /* the page's heading, where a sheet gave focus back */
      if (el && k.top && !el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1');
      if (el && !el.closest('[hidden]')) { if (typeof k.back === 'string' && el.matches('input')) { el.value = k.back; el.dataset.back = '1'; el.dispatchEvent(new Event('input', { bubbles: true })); } el.focus({ preventScroll: true }); }
    } }

  paintSky();
  /* What a page's own script may use: Home's is plugins/hydra/home/home.js. */
  /* Tips, not a tour: the page's own, in order. The first one
     whose part is on the page, with data where it waits for data, shows once its part is in view: one line on a small
     solid bubble pointing at it. One at a time and at most one a visit (none within 30 minutes of the last, on any
     page), never while a sheet is up, and each once: the page keeps it as seen as soon as it shows, and Home's server
     once it's closed or the page goes (POST /api/tips/seen), since a seen tip builds the page again and Home opens in
     place without it. x or Escape closes it. Home inside another page's frame shows none. */
  const inWindow = () => { try { return LIVE && window.top === window; } catch (e) { return false; } };
  const atFoot = el => document.body.insertBefore(el, $('body > script'));  /* the kit's script stays the body's last element */

  /* A sheet: Home's welcome, What's new, or
     a page's connect ask, one at a time over the page dimmed behind it, which can't be reached while it's up. Focus
     starts in it, Tab goes round its own controls, and focus comes back to the page when it goes. It comes in with
     opacity and a scale from .98, 300 ms; with reduced motion it only fades, 200 ms. The page hears it go through a
     "hydra:sheet" event. A connect ask is kept as seen by the page as soon as it shows, and by Home's server once it's
     answered or the page goes. */
  const sheet = $('.sheet[data-sheet]');
  if (sheet && inWindow()) (() => {
    const kind = sheet.dataset.sheet, app = sheet.dataset.app || APP, ask = kind === 'ask' && sheet.dataset.tip;
    const mine = `hydra-tips:${app}`, had = (() => { try { return JSON.parse(localStorage.getItem(mine)) || []; } catch (e) { return []; } })();
    if (ask && Array.isArray(had) && had.includes(ask)) return;  /* asked once already, here */
    const box = $('.sh', sheet), field = $('input', box), said = $('.said', box), go = $('[data-sheet-go]', box), later = $('[data-sheet-later]', box);
    const still = matchMedia('(prefers-reduced-motion:reduce)'), was = document.activeElement;
    atFoot(sheet);  /* out of the page it holds back */
    const behind = [...document.body.children].filter(e => e !== sheet && e.tagName !== 'SCRIPT');
    let told = false;
    const tell = () => {
      if (told || !ask) return; told = true;
      try { fetch('/api/tips/seen', { method: 'POST', credentials: 'same-origin', cache: 'no-store', keepalive: true, headers: { 'Content-Type': 'application/json' },
                                      body: JSON.stringify({ app, tip: ask }) }).catch(() => {}); } catch (e) {}
    };
    const controls = () => $$('input, button, a[href]', box).filter(e => !e.disabled && e.getClientRects().length);
    const keys = e => {
      if (e.key === 'Tab') { const o = controls(), k = o.indexOf(document.activeElement); e.preventDefault(); if (o.length) o[(k + (e.shiftKey ? -1 : 1) + o.length) % o.length].focus(); }
      else if (e.key === 'Escape') { const b = later || (sheet.dataset.esc === 'go' ? go : null); if (b) { e.preventDefault(); b.click(); } }
      else if (e.key === 'Enter' && e.target === field && !e.isComposing) { e.preventDefault(); go.click(); }
    };
    const close = detail => {
      document.removeEventListener('keydown', keys, true); tell();
      sheet.classList.remove('on'); behind.forEach(e => { e.inert = false; });
      setTimeout(() => { sheet.hidden = true; }, still.matches ? 200 : 300);
      const back = was && was !== document.body && document.contains(was) ? was : $('h1');
      if (back) { if (!back.matches('a[href], button, input, textarea, select, [tabindex]')) back.setAttribute('tabindex', '-1'); back.focus({ preventScroll: true }); }
      document.dispatchEvent(new CustomEvent('hydra:sheet', { detail: Object.assign({ kind }, detail) }));
    };
    const busy = on => { go.disabled = on; if (later) later.disabled = on; };
    go.addEventListener('click', () => {
      if (go.disabled) return;
      if (kind === 'welcome') {  /* the name, saved on the page with no Claude turn; an empty field is fine */
        const name = field ? field.value.trim() : '';
        busy(true);
        send('POST', '/api/name', { name }).then(a => {
          busy(false);
          if (a && a.ok) { close({ name }); return; }
          said.textContent = a && typeof a.said === 'string' && a.said ? a.said : 'Not saved. Try again in a moment.';
          if (field) field.focus();
        });
      } else if (kind === 'ask') {  /* the page's own Connect: the same request, and its note beside it */
        close({ connect: true });
        const own = $$(`[data-connect][data-app="${CSS.escape(app)}"]`).find(e => e.getClientRects().length);
        if (own) own.click(); else send('POST', '/api/request', { kind: 'connect', app });
      } else { send('POST', '/api/whats-new', {}); close({}); }
    });
    if (later) later.addEventListener('click', () => close({}));
    if (ask) { try { localStorage.setItem(mine, JSON.stringify([...(Array.isArray(had) ? had : []), ask])); } catch (e) {} addEventListener('pagehide', tell); }
    behind.forEach(e => { e.inert = true; });
    document.addEventListener('keydown', keys, true);
    sheet.hidden = false; void sheet.offsetWidth; sheet.classList.add('on');
    (field || go).focus({ preventScroll: true });
  })();
  const tipList = $('ol.tips[data-app]');
  if (tipList && inWindow()) (() => {
    const app = tipList.dataset.app, mine = `hydra-tips:${app}`, GAP = 30 * 60 * 1000;
    const read = (k, d) => { try { const v = JSON.parse(localStorage.getItem(k)); return v == null ? d : v; } catch (e) { return d; } };
    const write = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
    if (Date.now() - Number(read('hydra-tip-at', 0)) < GAP) return;
    const had = read(mine, []), seen = Array.isArray(had) ? had : [];
    const shown = e => !!e && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden' && Number(getComputedStyle(e).opacity) > 0;
    const filled = b => !b.matches('.new, .quiet') && !$('.es, .new, .g0l:empty', b);  /* drawn, not its empty state */
    const PART = { block: b => $('h2', b) || b, acts: b => $('.act0, .lact, .acts', b), field: b => $('input, textarea', b), drop: b => $('[data-drop]', b) };
    const part = t => {
      const b = t.dataset.for ? $(`[data-block="${CSS.escape(t.dataset.for)}"]`) : null;
      if (t.dataset.for && (!shown(b) || (t.dataset.when === 'data' && !filled(b)))) return null;
      const a = t.dataset.sel ? $$(t.dataset.sel).find(shown) : b && (PART[t.dataset.at] || PART.block)(b);
      return shown(a) ? a : null;
    };
    const next = $$('li[data-tip]', tipList).filter(t => !seen.includes(t.dataset.tip)).map(t => [t, part(t)]).find(([, a]) => a);
    if (!next) return;
    const [t, a] = next;
    let bubble = null, told = false;
    const tell = () => {  /* once: on close, or as the page goes, so it's heard even then */
      if (told) return; told = true;
      try { fetch('/api/tips/seen', { method: 'POST', credentials: 'same-origin', cache: 'no-store', keepalive: true, headers: { 'Content-Type': 'application/json' },
                                      body: JSON.stringify({ app, tip: t.dataset.tip }) }).catch(() => {}); } catch (e) {}
    };
    const place = () => {
      if (!bubble) return;
      const r = a.getBoundingClientRect(), w = bubble.offsetWidth, h = bubble.offsetHeight;
      const left = Math.max(16, Math.min(r.left, innerWidth - w - 16)), below = r.bottom + 12 + h <= innerHeight || r.top - 12 - h < 0;
      bubble.classList.toggle('up', !below);
      bubble.style.left = `${Math.round(left + scrollX)}px`;
      bubble.style.top = `${Math.round((below ? r.bottom + 12 : r.top - 12 - h) + scrollY)}px`;
      bubble.style.setProperty('--ax', `${Math.round(Math.max(12, Math.min(w - 24, r.left + Math.min(r.width / 2, 20) - left - 6)))}px`);
    };
    const keys = e => { if (e.key === 'Escape' && bubble) { e.preventDefault(); close(); } };
    const close = () => {
      if (!bubble) return;
      const b = bubble; bubble = null; b.classList.remove('on'); setTimeout(() => b.remove(), 200); tell();
      removeEventListener('resize', place); document.removeEventListener('keydown', keys);
    };
    const show = () => {
      if (bubble || $('.sheet:not([hidden])')) return;  /* never over a sheet: the next visit has it */
      write('hydra-tip-at', Date.now()); write(mine, [...seen, t.dataset.tip]); addEventListener('pagehide', tell);
      bubble = document.createElement('div'); bubble.className = 'tipb'; bubble.dataset.tip = t.dataset.tip; bubble.setAttribute('role', 'status');
      const line = document.createElement('p'), x = document.createElement('button');
      x.type = 'button'; x.className = 'tipx'; x.setAttribute('aria-label', 'Close tip'); x.textContent = '×'; x.addEventListener('click', close);
      bubble.append(line, x); atFoot(bubble);
      line.textContent = t.textContent; place();  /* the line goes in once the bubble's there, so it's read out */
      requestAnimationFrame(() => { if (bubble) bubble.classList.add('on'); });
      addEventListener('resize', place); document.addEventListener('keydown', keys);
    };
    const io = new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) { io.disconnect(); show(); } }, { threshold: 0.6 });
    io.observe(a);
  })();

  window.HydraKit = { $, $$, ss, clamp, nowMin, today, paintSky, onPaint: fn => { painted.push(fn); paintSky(); }, onPanel: fn => heard.push(fn), send, act, tip, notSaved, mend, keep, live: LIVE };
})();
