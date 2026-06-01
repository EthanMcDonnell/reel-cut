(anchor) => {
  const zwRe = /[​‌‍⁠﻿­]/g;
  const clean = s => s.replace(zwRe, '').replace(/[‘’“”]/g, "'").toLowerCase();
  const skip = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE']);
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    if (skip.has(n.parentElement?.tagName)) continue;
    if (clean(n.textContent).includes(anchor)) return n.parentElement;
  }
  return null;
}
