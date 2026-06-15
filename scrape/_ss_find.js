(args) => {
  const rawAnchor = (args && args.anchor) || '';
  const snippet = (args && args.snippet) || rawAnchor;
  const context = (args && args.context) || '';
  const zwRe = /[​‌‍⁠﻿­]/g;
  // Aggressive match-only normalization: decompose unicode, drop zero-width chars, unify
  // smart quotes and dashes, collapse whitespace. No offset mapping happens here (unlike
  // the highlighter), so length-changing normalization is safe and maximises recall.
  const clean = s => s
    .normalize('NFKD')
    .replace(zwRe, '')
    .replace(/[‘’“”]/g, "'")
    .replace(/[—–]/g, '-')
    .replace(/\s+/g, ' ')
    .toLowerCase()
    .trim();
  const anchor = clean(rawAnchor);
  const skipTags = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'NAV', 'ASIDE', 'FOOTER']);
  const specificBlocks = new Set(['P', 'LI', 'TD', 'TH', 'PRE', 'BLOCKQUOTE', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6']);
  const blockSel = 'p, li, blockquote, h1, h2, h3, h4, h5, h6, td, pre';

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

  // Tokens of length>2 used to score candidate blocks.
  function tokens(s) {
    return clean(s).split(/[^a-z0-9]+/).filter(t => t.length > 2);
  }
  const snippetTokens = tokens(snippet);
  const contextTokens = tokens(context);

  // Score a candidate by how many snippet/context tokens it contains. The full snippet
  // is weighted above the (paraphrased) script context, which only breaks ties.
  function score(el) {
    const set = new Set(clean(el.innerText || el.textContent || '').split(/[^a-z0-9]+/));
    let s = 0, c = 0;
    for (const t of snippetTokens) if (set.has(t)) s++;
    for (const t of contextTokens) if (set.has(t)) c++;
    return s * 2 + c;
  }

  // Fraction of snippet tokens present in el — used as the fuzzy-match confidence.
  function snippetRatio(el) {
    if (!snippetTokens.length) return 0;
    const set = new Set(clean(el.innerText || el.textContent || '').split(/[^a-z0-9]+/));
    let hit = 0;
    for (const t of snippetTokens) if (set.has(t)) hit++;
    return hit / snippetTokens.length;
  }

  function collectIn(root) {
    const found = [];
    // Pass 1: text-node walk — fast path for anchor in a single text node
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      if (inSkipped(n.parentElement, root)) continue;
      if (clean(n.textContent).includes(anchor)) {
        const b = nearestBlock(n.parentElement, root);
        if (!found.includes(b)) found.push(b);
      }
    }
    // Pass 2: paragraph-level innerText — catches anchor split across inline tags
    for (const el of root.querySelectorAll(blockSel)) {
      if (inSkipped(el, root)) continue;
      const t = el.innerText || el.textContent;
      if (clean(t).includes(anchor) && !found.includes(el)) found.push(el);
    }
    return found;
  }

  // Highest-scoring candidate; DOM order wins ties (preserves first-match behaviour).
  function pick(cands) {
    let best = null, bestScore = -1;
    for (const el of cands) {
      const sc = score(el);
      if (sc > bestScore) { best = el; bestScore = sc; }
    }
    return best;
  }

  // Best fuzzy candidate by snippet-token overlap, when no exact anchor match exists.
  function fuzzyBest(root) {
    let best = null, bestRatio = 0;
    for (const el of root.querySelectorAll(blockSel)) {
      if (inSkipped(el, root)) continue;
      const r = snippetRatio(el);
      if (r > bestRatio) { bestRatio = r; best = el; }
    }
    return { el: best, ratio: bestRatio };
  }

  // Tag the chosen block so highlight/screenshot target the same element find picked.
  function tag(el) {
    document.querySelectorAll('[data-snippet-target]').forEach(e => e.removeAttribute('data-snippet-target'));
    if (el) el.dataset.snippetTarget = '1';
    return el;
  }

  // Record per-snippet match metadata for the Python caller to read and report.
  function setMeta(found, confidence, matchType) {
    window.__ssLastMatch = { found, confidence, matchType };
  }

  const main = document.querySelector('main, article, [role="main"]');

  // Pass A — exact anchor match (scoped to main/article first, then the whole body).
  let cands = main ? collectIn(main) : [];
  if (!cands.length) cands = collectIn(document.body);
  if (cands.length) {
    setMeta(true, 1.0, 'exact');
    return tag(pick(cands));
  }

  // Pass B — fuzzy fallback: the block with the highest snippet-token overlap, if it
  // clears the threshold. Catches typography/whitespace drift between the scraped text
  // and the live DOM that defeats an exact substring match.
  const root = main || document.body;
  const fz = fuzzyBest(root);
  if (fz.el && fz.ratio >= 0.6) {
    setMeta(true, Number(fz.ratio.toFixed(2)), 'fuzzy');
    return tag(fz.el);
  }

  setMeta(false, Number(fz.ratio.toFixed(2)), 'none');
  return tag(null);
}
