/* Help's "Copy a report": the first press asks Home's server for
   the report (GET /api/report, `hydra report`'s exact text: states and counts only) and shows all of it; then Copy puts
   exactly that text on the clipboard. Nothing is copied before it's shown, and nothing else is ever copied. */
(() => {
  'use strict';
  const kit = window.HydraKit;
  if (!kit) return;
  const { $, send } = kit;
  const show = $('#rep-show'), box = $('#rep'), text = $('#rep-text'), copy = $('#rep-copy'), said = $('#rep-said');
  if (!show || !box || !text || !copy || !said) return;
  show.addEventListener('click', () => {
    if (!kit.live) { said.textContent = "The report comes from Hydra-OS's own pages."; return; }
    show.disabled = true; said.textContent = '';
    send('GET', '/api/report').then(r => {
      show.disabled = false;
      if (!r || r.ok !== true || typeof r.report !== 'string' || !r.report) {
        said.textContent = r && typeof r.said === 'string' && r.said ? r.said : "The report couldn't be made. Try again in a moment.";
        return;
      }
      text.textContent = r.report; box.hidden = false; show.hidden = true;
      said.textContent = 'This is all of it. Copy puts exactly this on your clipboard.';
      copy.focus();
    });
  });
  copy.addEventListener('click', () => {
    const all = text.textContent;
    const done = () => { said.textContent = 'Copied. Paste it into your message.'; };
    const by_hand = () => {
      const r = document.createRange(); r.selectNodeContents(text);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r);
      said.textContent = "It's selected. Press Command-C to copy it.";
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(all).then(done, by_hand); else by_hand();
  });
})();
