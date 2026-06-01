() => document.querySelectorAll('mark[data-snippet-highlight]').forEach(m => m.replaceWith(...m.childNodes))
