(anchor) => {
  const zwRe = /[​‌‍⁠﻿­]/g;
  const zwSingle = /[​‌‍⁠﻿­]/;
  const clean = s => s.replace(zwRe, '').replace(/[‘’“”]/g, "'").toLowerCase();
  const skip = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE']);

  function findInOrig(text, anch) {
    const cleaned = clean(text);
    const ci = cleaned.indexOf(anch);
    if (ci === -1) return null;
    let oi = 0, cc = 0;
    while (oi < text.length && cc < ci) { if (!zwSingle.test(text[oi])) cc++; oi++; }
    const start = oi;
    while (oi < text.length && cc < ci + anch.length) { if (!zwSingle.test(text[oi])) cc++; oi++; }
    return { start, end: oi };
  }

  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    if (skip.has(n.parentElement?.tagName)) continue;
    const pos = findInOrig(n.textContent, anchor);
    if (!pos) continue;
    try {
      const anchorNode = n.splitText(pos.start);
      anchorNode.splitText(pos.end - pos.start);
      const m = document.createElement('mark');
      m.style.backgroundColor = '#FFE066';
      m.style.borderRadius = '2px';
      m.dataset.snippetHighlight = 'true';
      anchorNode.parentNode.insertBefore(m, anchorNode);
      m.appendChild(anchorNode);
    } catch(e) {}
    break;
  }
}
