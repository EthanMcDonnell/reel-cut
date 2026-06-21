(args) => {
  const anchor = ((args && args.anchor) || '').toString();
  const snippet = ((args && args.snippet) || anchor).toString();
  const zwSingle = /[​‌‍⁠﻿­]/;
  // Length-preserving per-character normalization so concatenation offsets map back onto
  // raw text-node offsets. Do NOT add NFKD or whitespace collapse here — they change length.
  const cleanChar = c => c
    .replace(/[‘’“”]/g, "'")
    .replace(/[—–]/g, '-')
    .toLowerCase();
  // Needle normalization: whitespace-collapsed and trimmed to match the concatenation built
  // below (which also collapses runs of whitespace to a single space).
  const cleanNeedle = s => s
    .replace(/[​‌‍⁠﻿­]/g, '')
    .replace(/[‘’“”]/g, "'")
    .replace(/[—–]/g, '-')
    .replace(/\s+/g, ' ')
    .toLowerCase()
    .trim();
  const skipTags = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'NAV', 'ASIDE', 'FOOTER']);
  const HL_NAME = 'ssSnippet';

  function inSkipped(el, root) {
    let p = el;
    while (p && p !== root) { if (skipTags.has(p.tagName)) return true; p = p.parentElement; }
    return false;
  }

  // Concatenate a block's text nodes (whitespace collapsed) and record, for each emitted
  // character, the (node, offset) it came from. Lets us locate text that spans inline tags
  // like <a>/<span> and build a Range across them.
  function buildIndex(block) {
    const w = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    let concat = '', prevSpace = true;
    const map = [];
    let n;
    while ((n = w.nextNode())) {
      if (inSkipped(n.parentElement, block)) continue;
      const raw = n.textContent;
      for (let i = 0; i < raw.length; i++) {
        const c = raw[i];
        if (zwSingle.test(c)) continue;
        if (/\s/.test(c)) {
          if (prevSpace) continue;
          concat += ' '; map.push({ node: n, offset: i }); prevSpace = true;
        } else {
          concat += cleanChar(c); map.push({ node: n, offset: i }); prevSpace = false;
        }
      }
    }
    return { concat, map };
  }

  // Build a Range covering `needle` within `block`, spanning inline tags. Null if not found.
  function rangeFor(block, needle) {
    if (!needle) return null;
    const { concat, map } = buildIndex(block);
    const idx = concat.indexOf(needle);
    if (idx === -1) return null;
    const start = map[idx];
    const end = map[idx + needle.length - 1];
    if (!start || !end) return null;
    const r = document.createRange();
    r.setStart(start.node, start.offset);
    r.setEnd(end.node, end.offset + 1);
    return r;
  }

  function ensureStyle() {
    if (document.getElementById('ss-hl-style')) return;
    const st = document.createElement('style');
    st.id = 'ss-hl-style';
    st.textContent = '::highlight(' + HL_NAME + '){ background-color:#FFE066; color:#000; }';
    document.head.appendChild(st);
  }

  // Highlight a Range with the CSS Custom Highlight API — no DOM mutation, so adjacent
  // inline nodes can't be corrupted. Returns false if the browser lacks the API.
  function highlightRange(range) {
    if (!(window.CSS && CSS.highlights && window.Highlight)) return false;
    ensureStyle();
    let hl = CSS.highlights.get(HL_NAME);
    if (!hl) { hl = new Highlight(); CSS.highlights.set(HL_NAME, hl); }
    hl.add(range);
    return true;
  }

  // Fuzzy fallback: colour the whole block so the screenshot still shows a highlight when
  // the exact snippet can't be located (typography drift, unusual markup).
  function highlightWhole(el) {
    el.dataset.snippetHighlight = 'true';
    el.style.setProperty('background-color', '#FFE066', 'important');
    el.style.setProperty('border-radius', '3px', 'important');
  }

  const target = document.querySelector('[data-snippet-target]') ||
                 document.querySelector('main, article, [role="main"]') ||
                 document.body;

  // Prefer the full snippet so the whole sentence is marked; fall back to the anchor, then
  // to colouring the entire block.
  const range = rangeFor(target, cleanNeedle(snippet)) || rangeFor(target, cleanNeedle(anchor));
  const region = (range && highlightRange(range)) ? range : (highlightWhole(target), target);
  window.__ssRegion = region;

  // Find the nearest scrollable ancestor of `node`, up to and including body/documentElement.
  // SPAs (e.g. Grokipedia) scroll an inner overflow container rather than the window; the same
  // happens when overlay-dismissal forces overflow:auto onto a fixed-height body, which then
  // becomes the scroller and leaves window.scrollTo a no-op. Returns null when nothing scrolls.
  function scrollableAncestor(node) {
    let el = node.nodeType === 1 ? node : node.parentElement;
    while (el) {
      const oy = getComputedStyle(el).overflowY;
      if ((oy === 'auto' || oy === 'scroll' || oy === 'overlay') && el.scrollHeight > el.clientHeight + 1) {
        return el;
      }
      if (el === document.documentElement) break;
      el = el.parentElement;
    }
    return null;
  }

  // Centre the highlighted region in the viewport so the crop frames it.
  const r0 = region.getBoundingClientRect();
  if (r0.top < 0 || r0.top > window.innerHeight || r0.bottom > window.innerHeight) {
    const startNode = (region instanceof Range) ? region.startContainer : region;
    const scroller = scrollableAncestor(startNode);
    if (scroller) {
      // getBoundingClientRect is viewport-relative, so adjusting the container's scrollTop by
      // the offset from the desired viewport centre brings the region into frame.
      const targetTop = window.innerHeight / 2 - r0.height / 2;
      scroller.scrollTop += r0.top - targetTop;
    } else {
      const absY = r0.top + window.pageYOffset;
      window.scrollTo({ top: Math.max(0, absY - window.innerHeight / 2 + r0.height / 2), behavior: 'instant' });
    }
  }
}
