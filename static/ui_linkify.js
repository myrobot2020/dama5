// #region agent log
fetch('http://127.0.0.1:7685/ingest/6975c974-9b9d-4128-9761-b8675de3184c',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'a9c28f'},body:JSON.stringify({sessionId:'a9c28f',runId:'pre-fix',hypothesisId:'M1',location:'static/ui_linkify.js:1',message:'ui_linkify loaded',data:{},timestamp:Date.now()})}).catch(()=>{});
// #endregion agent log

// NOTE: This file defines global helpers used by the main chat script.
// We keep them on `window` so the rest of the app can stay unchanged while modularizing.

(function () {
  function esc(s) {
    return (s ?? '').toString().replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }
  function escAttr(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
  function normalizeSuttaCiteRef(raw) {
    const t0 = String(raw || '').trim().replace(/\s+/g, ' ');
    let m = t0.match(/^cAN\s*(\d+(?:\.\d+)*)\s*$/i);
    if (m) return 'cAN ' + m[1];
    // Sometimes the backend emits "pAN 2.4.1" (prefixed AN). Normalize to canonical "AN 2.4.1".
    m = t0.match(/^pAN\s*(\d+(?:\.\d+)*)\s*$/i);
    if (m) return 'AN ' + m[1];
    m = t0.match(/^AN\s*(\d+(?:\.\d+)*)\s*$/i);
    if (m) return 'AN ' + m[1];
    return t0;
  }
  function citeOpenButton(refInner, kind, wrapParens) {
    const r = normalizeSuttaCiteRef(String(refInner || '').trim());
    const safe = esc(r);
    const a = escAttr(r);
    const k = kind === 'commentary' ? 'commentary' : 'sutta';
    const wrap = (wrapParens === undefined) ? true : !!wrapParens;
    /* <a> is valid inside <p>; <button> is often stripped by DOMPurify inside paragraphs */
    return '<a href="#" class="cite cite-open" data-kind="' + k + '" data-ref="' + a + '">' + (wrap ? '(' : '') + safe + (wrap ? ')' : '') + '</a>';
  }
  function citeTokenToButton(token) {
    const t = String(token || '').trim();
    if (/^cAN\s*\d/i.test(t)) return citeOpenButton(t, 'commentary', true);
    if (/^pAN\s*\d/i.test(t)) return citeOpenButton(normalizeSuttaCiteRef(t), 'sutta', true);
    if (/^AN\s*\d/i.test(t)) return citeOpenButton(t, 'sutta', true);
    return esc(t);
  }
  /** Split comma-separated refs inside one pair of parens so each (AN …)/(cAN …) is its own link. */
  function citeParenGroup(innerRaw) {
    const inner = String(innerRaw || '').trim();
    if (!inner) return '()';
    const parts = inner.split(',').map((x) => x.trim()).filter(Boolean);
    if (parts.length === 1) {
      const b = citeTokenToButton(parts[0]);
      if (b.indexOf('<a ') === 0) return b;
      return '(' + b + ')';
    }
    return '(' + parts.map(citeTokenToButton).join(', ') + ')';
  }
  function _replaceBareCitations(t) {
    let x = String(t || '');
    /* cAN before AN; optional space so AN1.5.8 matches like AN 1.5.8 */
    x = x.replace(/\b(cAN)\s*(\d+(?:\.\d+)*)\b/gi, (_, __, nums) => citeOpenButton('cAN ' + nums, 'commentary', false));
    // Support both "AN 1.5.8" and "pAN 1.5.8" (seen in some generated text).
    x = x.replace(/\b(pAN|AN)\s*(\d+(?:\.\d+)*)\b/gi, (_, __, nums) => citeOpenButton('AN ' + nums, 'sutta', false));
    return x;
  }
  function citeifyBareOutsideButtons(s) {
    const str = String(s || '');
    const low = str.toLowerCase();
    let i = 0;
    let out = '';
    while (i < str.length) {
      const iBtn = low.indexOf('<button', i);
      const iA = low.indexOf('<a ', i);
      let open = -1;
      let closeTag = '';
      if (iBtn >= 0 && (iA < 0 || iBtn <= iA)) {
        open = iBtn;
        closeTag = '</button>';
      } else if (iA >= 0) {
        open = iA;
        closeTag = '</a>';
      }
      if (open === -1) {
        out += _replaceBareCitations(str.slice(i));
        break;
      }
      const gt = str.indexOf('>', open);
      if (gt < 0) {
        out += _replaceBareCitations(str.slice(i));
        out += str.slice(open);
        break;
      }
      const openTag = str.slice(open, gt + 1);
      const isCite = openTag.indexOf('cite-open') >= 0;
      if (!isCite) {
        out += _replaceBareCitations(str.slice(i, open));
        out += str.slice(open, (open === iBtn) ? open + 7 : open + 3);
        i = (open === iBtn) ? open + 7 : open + 3;
        continue;
      }
      out += _replaceBareCitations(str.slice(i, open));
      const close = low.indexOf(closeTag, gt);
      if (close === -1) {
        out += str.slice(open);
        break;
      }
      out += str.slice(open, close + closeTag.length);
      i = close + closeTag.length;
    }
    return out;
  }
  function formatAsstAnswer(raw) {
    let s = esc(raw ?? '');
    /* [(] [)] = literal parens; split commas so (AN 1, AN 2) is not one mashed ref */
    s = s.replace(/[(](cAN[^)]{0,400})[)]/gi, (_, g1) => citeParenGroup(g1));
    s = s.replace(/[(](AN[^)]{0,400})[)]/g, (_, g1) => citeParenGroup(g1));
    s = citeifyBareOutsideButtons(s);
    return s;
  }
  function citeifyOutsideFences(raw) {
    const parts = String(raw ?? '').split('```');
    const out = [];
    for (let i = 0; i < parts.length; i++) {
      let chunk = parts[i];
      if (i % 2 === 0) {
        chunk = chunk.replace(/[(](cAN[^)]{0,400})[)]/gi, (_, g1) => citeParenGroup(g1));
        chunk = chunk.replace(/[(](AN[^)]{0,400})[)]/g, (_, g1) => citeParenGroup(g1));
        chunk = citeifyBareOutsideButtons(chunk);
      }
      out.push(chunk);
    }
    return out.join('```');
  }
  function safeMdHtml(html) {
    if (typeof DOMPurify === 'undefined') return esc(String(html ?? ''));
    return DOMPurify.sanitize(String(html ?? ''), {
      ALLOWED_TAGS: ['p','br','ul','ol','li','strong','em','del','h1','h2','h3','h4','blockquote','a','pre','code','table','thead','tbody','tr','th','td','hr','small','span','button'],
      ALLOWED_ATTR: ['href','title','class','colspan','rowspan','rel','target','type','data-kind','data-ref'],
      // We rely on data-kind/data-ref to open the Reference panel from citations.
      ALLOW_DATA_ATTR: true,
    });
  }
  function renderMarkdown(raw) {
    const src = String(raw ?? '');
    if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
      return '<div class="md md-fallback">' + formatAsstAnswer(src) + '</div>';
    }
    const cited = citeifyOutsideFences(src);
    let html;
    try {
      marked.setOptions({ gfm: true, breaks: true, headerIds: false, mangle: false });
      html = marked.parse(cited);
    } catch (e) {
      html = '<p>' + esc(src) + '</p>';
    }
    return '<div class="md">' + safeMdHtml(html) + '</div>';
  }

  window.esc = esc;
  window.escAttr = escAttr;
  window.normalizeSuttaCiteRef = normalizeSuttaCiteRef;
  window.citeOpenButton = citeOpenButton;
  window.citeifyOutsideFences = citeifyOutsideFences;
  window.safeMdHtml = safeMdHtml;
  window.renderMarkdown = renderMarkdown;
})();

