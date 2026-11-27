/* Home's own script, after the kit's (/kit/app.js). The kit paints the sky and runs the saves; this is what only Home
   does: the greeting for the hour, the apps' grid, what lights with what, the one day read across every chart, and
   the slim goals bar that stays when the band has scrolled away. It talks to nothing but the kit. */
(() => {
  'use strict';
  const kit = window.HydraKit; if (!kit) return;
  const { $, $$ } = kit;
  /* The morning review's late line: while Home's server says the review is late, past
     09:30 with no run today, Home says so in the server's words at the top of the page, after any update line, and takes
     it away once the review has run. Off, not asked, due or done, it says nothing here: Help's row covers off. */
  { let line = null;
    kit.onPanel(p => {
      const r = p && p.review, said = r && r.state === 'late' && typeof r.said === 'string' ? r.said : '';
      if (said && !line) {
        const main = $('main'); if (!main) return;
        const after = $('main > [data-block=update]');
        line = document.createElement('p'); line.className = 't upd'; line.dataset.block = 'review'; line.setAttribute('role', 'status');
        main.insertBefore(line, after ? after.nextSibling : main.firstChild);
      }
      if (said) line.textContent = said;
      else if (line) { line.remove(); line = null; }
    });
  }

  /* The welcome sheet's name: the greeting takes it at once as the sheet goes, arriving with opacity and
     a scale from .98, 300 ms, or a fade with reduced motion. Home's server builds Home again with it too. */
  document.addEventListener('hydra:sheet', e => {
    const h = $('[data-greet]'); if (!h || !e.detail || e.detail.kind !== 'welcome') return;
    if (e.detail.name) h.dataset.name = e.detail.name;
    kit.paintSky(); h.classList.remove('arrive'); void h.offsetWidth; h.classList.add('arrive');
  });
  const web = $('.web'); if (!web) return;
  const NEW = web.classList.contains('new');
  const band = $('.gband', web), grid = $('.grid', web), add = $('.add', web), gbar = $('.gbar', web), gl5 = $('.gl5', web);
  const rows = $$('.g[data-g]', web), cards = $$('.card', web), engs = $$('.sp', web);
  const app = n => cards.find(c => c.dataset.app === n), feeds = c => (c.dataset.feeds || '').split(' ').filter(Boolean);
  const goal = g => rows.find(r => r.dataset.g === g), col = el => getComputedStyle(el).getPropertyValue('--c').trim();

  /* The greeting keeps to the day's own hours: evening from five, winding down in the hour and a half before lights
     out, and a nudge after it. With no lights out to go by, the nudge comes after midnight, so every state says the
     same at the same hour. */
  const greet = $('[data-greet]');
  if (greet) kit.onPaint(({ t }) => {
    const m = t < 300 ? t + 1440 : t, name = greet.dataset.name ? ', ' + greet.dataset.name : '', out = parseInt(greet.dataset.out, 10);
    const part = m < 720 ? 'Good morning' : m < 1020 ? 'Good afternoon' : 'Good evening';
    greet.textContent = m >= (out || 1440) ? `Still up${name}?` : out && m >= out - 90 ? `Winding down${name}.` : `${part}${name}.`;
  });

  /* Sunset on the date line, once their place is set: the kit's own sun for the page's place,
     so it always agrees with the sky. A day with no sunset there, near a pole, says none. */
  const more = $('[data-more]');
  if (more && 'sunset' in more.dataset) kit.onPaint(({ sun }) => {
    const m = Math.round(sun.set), h = Math.floor((m % 1440 + 1440) % 1440 / 60), mm = (m % 60 + 60) % 60, day = sun.set - sun.rise;
    const parts = [day > 0 && day < 1440 ? `Sunset ${h % 12 || 12}:${String(mm).padStart(2, '0')} ${h < 12 ? 'am' : 'pm'}` : '', more.dataset.lo ? `lights out ${more.dataset.lo}` : ''].filter(Boolean);
    if (parts.length) parts[0] = parts[0][0].toUpperCase() + parts[0].slice(1);
    more.textContent = parts.length ? ' \u00b7 ' + parts.join(', ') : '';  /* one dot at most */
  });

  /* The apps' grid: up to four across on a wide window, two on a tablet, one on a phone. Among those it takes the
     count that fills every row, or failing that leaves no card alone on the last one; if one must be, the add tile
     takes the whole row. */
  const wide = matchMedia('(min-width:840px)'), mid = matchMedia('(min-width:681px)');
  const colsFor = (n, M) => { const ok = [...Array(M + 1).keys()].slice(2).reverse(); return M === 1 ? 1 : n <= M ? Math.max(2, n) : ok.find(k => n % k === 0) || ok.find(k => n % k !== 1) || M; };
  const fitGrid = () => {
    if (!grid) return;
    const n = cards.length + (add ? 1 : 0), c = colsFor(n, wide.matches ? 4 : mid.matches ? 2 : 1);
    grid.style.setProperty('--cols', c); if (add) add.classList.toggle('wide', c > 1 && n > c && n % c === 1);
  };
  /* The compact bar is made from the goals themselves, in their order, and shows once the band is off the top of the window. */
  const bars = gbar ? [...(gl5 ? gl5.children : [])].filter(r => r.matches('.g[data-g]')).map(r => {
    const s = document.createElement('span'); s.className = 'gi' + (r.classList.contains('off') ? ' off' : '') + (r.classList.contains('new') ? ' un' : ''); s.style.cssText = r.style.cssText;
    s.innerHTML = '<span class="nm"></span><span class="gb"><i></i><b></b></span><em></em>';
    s.firstChild.textContent = $('.gn', r).textContent; s.lastChild.textContent = r.dataset.pace || 'Not counted yet'; s._row = r; gbar.append(s); return s;
  }) : [];
  if (gbar && bars.length && band) new IntersectionObserver(([e]) => gbar.classList.toggle('show', !e.isIntersecting && e.boundingClientRect.top < 0), { rootMargin: '-56px 0px 0px 0px' }).observe(band);

  /* Lighting. A goal rings the widgets that feed it, in its own colour. A widget lights its goal. A row under the
     apps rings the widgets its engine fed. Everything else dims. Nothing is drawn between any of them. Just
     installed, nothing lights: nothing is connected to anything yet. */
  let pin = null, sd = null;
  const light = el => {
    if (NEW || sd !== null) el = null;
    const on = new Set(), ring = (k, c) => { on.add(k); k.style.setProperty('--ring', c); };
    web.classList.toggle('focus', !!el);
    cards.forEach(k => k.style.removeProperty('--ring'));
    if (el) on.add(el);
    if (el && el.classList.contains('sp')) cards.filter(k => (k.dataset.fed || '').split(' ').includes(el.dataset.eng)).forEach(k => { ring(k, `var(--${el.dataset.eng})`); feeds(k).forEach(g => on.add(goal(g))); });
    else if (el && el.classList.contains('g')) cards.filter(k => feeds(k).includes(el.dataset.g)).forEach(k => ring(k, col(el)));
    else if (el) feeds(el).forEach(g => on.add(goal(g)));
    [...rows, ...cards, ...engs].forEach(x => x.classList.toggle('on', on.has(x)));
    bars.forEach(s => s.classList.toggle('on', on.has(s._row))); if (gbar) gbar.classList.toggle('focus', !!el);
  };
  /* Hover or focus lights it; a tap holds it, and a second tap lets go. */
  if (!NEW) [...rows, ...cards, ...engs].forEach(el => {
    el.addEventListener('mouseenter', () => light(el)); el.addEventListener('mouseleave', () => light(pin));
    el.addEventListener('focus', () => light(el)); el.addEventListener('blur', () => light(pin));
    el.addEventListener('click', e => { if (e.target.closest('a,button,input,.ins')) return; pin = pin === el ? null : el; light(pin); });
    el.addEventListener('keydown', e => { if (e.target === el && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); pin = pin === el ? null : el; light(pin); } });
  });
  bars.forEach(s => { s.addEventListener('mouseenter', () => light(s._row)); s.addEventListener('mouseleave', () => light(pin)); });
  document.addEventListener('click', e => { if (pin && !e.target.closest('.g,.card,.sp')) { pin = null; light(null); } });

  /* Scrub. A day pointed at in one chart is the day in all of them: one line, that day's bars lit, the rest quiet,
     and the day read out beside Your pages, in each app's own words. While it runs it takes over from the lighting;
     leaving hands it back. */
  const dayEl = $('.day', web), DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const charts = $$('.card .ins', web).map(el => { let says = []; try { says = JSON.parse(el.dataset.says || '[]'); } catch (e) {} return { el, pl: $('.pl', el), bars: $$('.pl > *', el), says, name: el.closest('.card').dataset.name || '' }; }).filter(c => c.pl);
  /* The 14 days end on the charts' own last day, an old export's included, and only that day of today says so. */
  const last14 = web.dataset.to ? new Date(web.dataset.to + 'T12:00:00') : null, isToday = (web.dataset.today || web.dataset.to) === web.dataset.to;
  const dayName = i => { if (!last14) return ''; const d = new Date(last14); d.setDate(d.getDate() - (13 - i)); return `${DOW[d.getDay()]} ${MON[d.getMonth()]} ${d.getDate()}${i === 13 && isToday ? ', today' : ''}`; };
  const say = i => { const parts = charts.map(c => typeof c.says[i] === 'string' && c.says[i].trim() ? (charts.length > 1 ? c.name + ': ' : '') + c.says[i].trim().replace(/[.?!]+$/, '') : '').filter(Boolean); return parts.length ? parts.join('. ') + '.' : ''; };
  let hold = false, last = 13;
  const setDay = i => {
    if (i === sd) return;
    sd = i; const live = i !== null;
    if (live) { last = i; web.style.setProperty('--sd', i); if (dayEl) { dayEl.textContent = ''; const b = document.createElement('b'); b.textContent = dayName(i) + (say(i) ? ':' : ''); dayEl.append(b, say(i) ? ' ' + say(i) : ''); } }
    web.classList.toggle('scrub', live);
    charts.forEach(c => c.bars.forEach((b, j) => b.classList.toggle('hi', j === i)));
    light(live ? null : pin || cards.find(c => c.matches(':hover')) || null);
  };
  const dayAt = (c, e) => { const r = c.pl.getBoundingClientRect(); return Math.max(0, Math.min(13, Math.floor((e.clientX - r.left) / r.width * 14))); };
  const keyed = () => !!document.activeElement && document.activeElement.matches('.ins:focus-visible');
  charts.forEach(c => {
    /* A mouse scrubs as it moves and lets go as it leaves. A tap shows the day and holds it; a tap on the same day, or anywhere else, lets go. */
    c.el.addEventListener('pointermove', e => { if (e.pointerType === 'mouse') setDay(dayAt(c, e)); });
    c.el.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse' && !hold && !keyed()) setDay(null); });
    c.el.addEventListener('click', e => { e.stopPropagation(); const i = dayAt(c, e), touch = e.pointerType && e.pointerType !== 'mouse'; if (touch && hold && i === sd) { hold = false; setDay(null); } else { hold = true; setDay(i); } });
    /* A focused chart takes Left and Right, Home and End; Escape or moving on lets go. */
    c.el.addEventListener('focus', () => { if (c.el.matches(':focus-visible')) setDay(sd === null ? last : sd); });
    c.el.addEventListener('blur', () => { if (!hold) setDay(null); });
    c.el.addEventListener('keydown', e => {
      const k = e.key, to = k === 'Home' ? 0 : k === 'End' ? 13 : k === 'ArrowLeft' ? (sd === null ? last : sd) - 1 : k === 'ArrowRight' ? (sd === null ? last : sd) + 1 : null;
      if (to !== null) { e.preventDefault(); e.stopPropagation(); setDay(Math.max(0, Math.min(13, to))); } else if (k === 'Escape') { hold = false; setDay(null); }
    });
  });
  document.addEventListener('click', e => { if (!e.target.closest('.ins')) { hold = false; setDay(null); } }, true);

  /* An added widget's button takes it off Home: Home's server takes it out of the layout, the
     tile goes at once, focus moves to what followed it, and the page built next leaves it out. */
  $$('[data-remove]', web).forEach(b => b.addEventListener('click', () => {
    if (b.disabled) return;
    b.disabled = true;
    kit.send('POST', '/api/widget/remove', { id: b.dataset.remove }).then(a => {
      if (!a || !a.ok) { b.disabled = false; kit.tip(b, kit.notSaved(a || {})); return; }
      const card = b.closest('.card'), next = card.nextElementSibling;
      cards.splice(cards.indexOf(card), 1);
      for (let i = charts.length - 1; i >= 0; i--) if (card.contains(charts[i].el)) charts.splice(i, 1);
      card.remove(); fitGrid();
      if (next) next.focus();
    });
  }));

  /* ?lit=<app or goal> holds one thing lit from the start, for checks only. */
  const lit = new URLSearchParams(location.search).get('lit'); if (lit && !NEW) { pin = app(lit) || goal(lit) || null; light(pin); }
  fitGrid(); addEventListener('resize', fitGrid);

})();
