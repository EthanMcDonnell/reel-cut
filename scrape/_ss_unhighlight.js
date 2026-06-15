() => {
  document.querySelectorAll('mark[data-snippet-highlight]').forEach(m => m.replaceWith(...m.childNodes));
  document.querySelectorAll('[data-snippet-highlight]').forEach(el => {
    el.removeAttribute('data-snippet-highlight');
    el.style.removeProperty('background-color');
    el.style.removeProperty('border-radius');
  });
  document.querySelectorAll('[data-snippet-target]').forEach(el => el.removeAttribute('data-snippet-target'));
}
