(anchor) => {
  const zwRe = /[​‌‍⁠﻿­]/g;
  const zwSingle = /[​‌‍⁠﻿­]/;
  const clean = s => s.replace(zwRe, '').replace(/[''""]/g, "'").toLowerCase();
  const skipTags = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'NAV', 'ASIDE', 'FOOTER']);

  function inSkipped(el, root) {
    let p = el;
    while (p && p !== root) { if (skipTags.has(p.tagName)) return true; p = p.parentElement; }
    return false;
  }

  function rawOffset(text, cleanIdx) {
    let oi = 0, cc = 0;
    while (oi < text.length && cc < cleanIdx) { if (!zwSingle.test(text[oi])) cc++; oi++; }
    return oi;
  }

  function highlightIn(root) {
    // Pass 1: anchor fits inside a single text node — safe, no DOM structure mutation
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      if (inSkipped(n.parentElement, root)) continue;
      const cleaned = clean(n.textContent);
      const ci = cleaned.indexOf(anchor);
      if (ci === -1) continue;
      try {
        const mid = n.splitText(rawOffset(n.textContent, ci));
        mid.splitText(rawOffset(mid.textContent, anchor.length));
        const m = document.createElement('mark');
        m.style.backgroundColor = '#FFE066';
        m.style.borderRadius = '2px';
        m.dataset.snippetHighlight = 'true';
        mid.parentNode.insertBefore(m, mid);
        m.appendChild(mid);
      } catch(e) {}
      return true;
    }

    // Pass 2: anchor spans inline elements — highlight the containing paragraph with CSS only,
    // no DOM structure mutation (avoids corrupting adjacent nodes)
    const blocks = root.querySelectorAll('p, li, blockquote, td, pre');
    for (const block of blocks) {
      if (inSkipped(block, root)) continue;
      const bt = clean(block.innerText || block.textContent);
      if (!bt.includes(anchor)) continue;
      block.dataset.snippetHighlight = 'true';
      block.style.setProperty('background-color', '#FFE066', 'important');
      block.style.setProperty('border-radius', '3px', 'important');
      return true;
    }
    return false;
  }

  const main = document.querySelector('main, article, [role="main"]');
  if (main && highlightIn(main)) return;
  highlightIn(document.body);
}
