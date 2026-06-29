() => {
  if (window.CSS && CSS.highlights) CSS.highlights.delete('ssSnippet');
  const st = document.getElementById('ss-hl-style');
  if (st) st.remove();
  window.__ssRegion = null;
  window.__ssHighlight = null;
  document.querySelectorAll('mark[data-snippet-highlight]').forEach(m => m.replaceWith(...m.childNodes));
  document.querySelectorAll('[data-snippet-highlight]').forEach(el => {
    el.removeAttribute('data-snippet-highlight');
    el.style.removeProperty('background-color');
    el.style.removeProperty('border-radius');
  });
  document.querySelectorAll('[data-snippet-target]').forEach(el => el.removeAttribute('data-snippet-target'));
}
