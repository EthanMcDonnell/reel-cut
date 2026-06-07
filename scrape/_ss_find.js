(anchor) => {
  const zwRe = /[​‌‍⁠﻿­]/g;
  const clean = s => s.replace(zwRe, '').replace(/[''""]/g, "'").toLowerCase();
  const skipTags = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'NAV', 'ASIDE', 'FOOTER']);
  const specificBlocks = new Set(['P', 'LI', 'TD', 'TH', 'PRE', 'BLOCKQUOTE', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6']);

  function inSkipped(el, root) {
    let p = el;
    while (p && p !== root) { if (skipTags.has(p.tagName)) return true; p = p.parentElement; }
    return false;
  }

  // Walk up from el to the nearest specific block element (p, li, td, etc.)
  // Falls back to el if none found within 8 levels
  function nearestBlock(el, root) {
    let p = el;
    for (let i = 0; i < 8; i++) {
      if (!p || p === root) break;
      if (specificBlocks.has(p.tagName)) return p;
      p = p.parentElement;
    }
    return el;
  }

  function searchIn(root) {
    // Pass 1: text-node walk — fast path for anchor in a single text node
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      if (inSkipped(n.parentElement, root)) continue;
      if (clean(n.textContent).includes(anchor)) return nearestBlock(n.parentElement, root);
    }
    // Pass 2: paragraph-level innerText — catches anchor split across inline tags
    const blocks = root.querySelectorAll('p, li, blockquote, h1, h2, h3, h4, h5, h6, td, pre');
    for (const el of blocks) {
      if (inSkipped(el, root)) continue;
      const t = el.innerText || el.textContent;
      if (clean(t).includes(anchor)) return el;
    }
    return null;
  }

  const main = document.querySelector('main, article, [role="main"]');
  if (main) { const r = searchIn(main); if (r) return r; }
  return searchIn(document.body);
}
