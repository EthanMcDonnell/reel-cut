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

  // Build a Range from char offsets [lo, hi] (inclusive) into a buildIndex map. Null if either
  // endpoint has no mapping.
  function rangeFromOffsets(map, lo, hi) {
    const start = map[lo];
    const end = map[hi];
    if (!start || !end) return null;
    const r = document.createRange();
    r.setStart(start.node, start.offset);
    r.setEnd(end.node, end.offset + 1);
    return r;
  }

  // Build a Range covering `needle` within `block`, spanning inline tags. Null if not found.
  function rangeFor(block, needle) {
    if (!needle) return null;
    const { concat, map } = buildIndex(block);
    const idx = concat.indexOf(needle);
    if (idx === -1) return null;
    return rangeFromOffsets(map, idx, idx + needle.length - 1);
  }

  // Fuzzy word-level Range: when an exact substring match fails (a stray char, a differently
  // formatted number, normalization drift between scrape and live DOM), slide a word-window over
  // the block and lock onto the span with the most needle words, then trim the window to its
  // first/last actually-matching word so the highlight stays tight. Returns null below threshold.
  function fuzzyRange(block, needle) {
    if (!needle) return null;
    const { concat, map } = buildIndex(block);
    const words = [];
    const re = /\S+/g;
    let m;
    while ((m = re.exec(concat))) words.push({ text: m[0], start: m.index, end: m.index + m[0].length - 1 });
    const needleWords = needle.split(' ').filter(Boolean);
    if (!needleWords.length || !words.length) return null;
    const needleSet = new Set(needleWords);
    const n = needleWords.length;

    // Best window by fraction of needle words present, flexing size around the needle length so a
    // slightly re-worded span still locks on (mirrors reconcile_manifest.py's _best_window).
    let best = { score: 0, lo: 0, hi: 0 };
    for (const size of new Set([Math.max(1, n - 1), n, n + 1, n + 2])) {
      for (let i = 0; i + size <= words.length; i++) {
        let hit = 0;
        for (let j = i; j < i + size; j++) if (needleSet.has(words[j].text)) hit++;
        const score = hit / Math.max(size, n);
        if (score > best.score) best = { score, lo: i, hi: i + size - 1 };
      }
    }
    if (best.score < 0.7) return null;

    let lo = best.lo, hi = best.hi;
    while (lo < hi && !needleSet.has(words[lo].text)) lo++;
    while (hi > lo && !needleSet.has(words[hi].text)) hi--;
    return rangeFromOffsets(map, words[lo].start, words[hi].end);
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

  const root = document.querySelector('main, article, [role="main"]') || document.body;
  const target = document.querySelector('[data-snippet-target]') || root;

  // Same as rangeFor, but indexed over the whole article so a snippet that runs past the end
  // of one block is still found. find() tags a single block, so a proof phrase that continues
  // into the next element (a paragraph closing into its own heading) can never match inside
  // the tag — the search fell through to the 80-char anchor, which does fit, and highlighted
  // only the run-up to the claim. Requiring the match to *begin* inside the tagged block keeps
  // find's script_context disambiguation: this can only extend that block's match, not move it.
  function rangeSpanningBlocks(needle, mustStartIn) {
    if (!needle) return null;
    const { concat, map } = buildIndex(root);
    const idx = concat.indexOf(needle);
    if (idx === -1) return null;
    const start = map[idx];
    if (!start || !mustStartIn.contains(start.node)) return null;
    return rangeFromOffsets(map, idx, idx + needle.length - 1);
  }

  // Prefer an exact range for the full snippet — inside the tagged block, then spanning out of
  // it — before dropping to the anchor prefix; then a fuzzy word-level range; and only as a last
  // resort colour the entire block. `__ssHighlight` records which path won, so the Python caller
  // can flag blunt whole-block highlights *and* anchor-only ones, where the highlight covers the
  // first 80 characters of the requested proof and stops.
  const cleanSnippet = cleanNeedle(snippet);
  let range = rangeFor(target, cleanSnippet) || rangeSpanningBlocks(cleanSnippet, target);
  let precision = range ? 'range' : 'none';
  if (!range) {
    range = rangeFor(target, cleanNeedle(anchor));
    if (range) precision = 'anchor_range';
  }
  if (!range) {
    range = fuzzyRange(target, cleanSnippet);
    if (range) precision = 'fuzzy_range';
  }
  let region;
  if (range && highlightRange(range)) {
    region = range;
  } else {
    highlightWhole(target);
    region = target;
    precision = 'whole_block';
  }
  window.__ssRegion = region;
  window.__ssHighlight = precision;

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
