(anchor) => {
  const zwRe = /[​‌‍⁠﻿­]/g;
  const zwSingle = /[​‌‍⁠﻿­]/;
  // Length-preserving normalization (modulo zero-width removal) so cleaned-string offsets
  // still map back onto raw text-node offsets in rawOffset(). Do NOT add NFKD or whitespace
  // collapsing here — they change length and would corrupt splitText().
  const clean = s => s
    .replace(zwRe, '')
    .replace(/[‘’“”]/g, "'")
    .replace(/[—–]/g, '-')
    .toLowerCase();
  const cleanAnchor = clean(anchor);
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
      const ci = cleaned.indexOf(cleanAnchor);
      if (ci === -1) continue;
      try {
        const mid = n.splitText(rawOffset(n.textContent, ci));
        mid.splitText(rawOffset(mid.textContent, cleanAnchor.length));
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
    const blockSel = 'p, li, blockquote, td, pre';
    const blocks = root.matches && root.matches(blockSel)
      ? [root, ...root.querySelectorAll(blockSel)]
      : [...root.querySelectorAll(blockSel)];
    for (const block of blocks) {
      if (inSkipped(block, root)) continue;
      const bt = clean(block.innerText || block.textContent);
      if (!bt.includes(cleanAnchor)) continue;
      highlightWhole(block);
      return true;
    }
    return false;
  }

  // CSS-highlight an entire element. Used as the fuzzy-match fallback: when the anchor
  // isn't an exact substring of the chosen block, highlight the whole block so the
  // screenshot still shows a highlight on the correct text.
  function highlightWhole(el) {
    el.dataset.snippetHighlight = 'true';
    el.style.setProperty('background-color', '#FFE066', 'important');
    el.style.setProperty('border-radius', '3px', 'important');
  }

  // Prefer the block find tagged, so the highlight lands on the same element that was
  // scrolled to and screenshotted. If the anchor can't be located inside it (a fuzzy
  // match), highlight the whole tagged block rather than leaving it unmarked.
  const target = document.querySelector('[data-snippet-target]');
  if (target) {
    if (!highlightIn(target)) highlightWhole(target);
    return;
  }
  const main = document.querySelector('main, article, [role="main"]');
  if (main && highlightIn(main)) return;
  highlightIn(document.body);
}
