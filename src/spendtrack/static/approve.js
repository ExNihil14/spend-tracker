// Клавиатурный триаж очереди /approve (дизайн-ревью M-4): j/k — строки, Enter — одобрить,
// s — пропустить, 1–9 — категория. Фокус — на реальной кнопке строки (a11y + нативный Enter).
// После approve/skip htmx удаляет строку — фокус возвращаем на ту же позицию списка.
(function () {
  'use strict';

  var tbody = document.getElementById('review-rows');
  if (!tbody) return;

  var idx = -1;
  var keyboard = false;

  function rows() {
    return Array.prototype.slice.call(tbody.querySelectorAll('tr.review-row'));
  }

  function mark(row) {
    rows().forEach(function (r) { r.classList.toggle('is-selected', r === row); });
  }

  function focusRow(row) {
    if (!row) return;
    var btn = row.querySelector('.review-approve');
    if (btn) btn.focus();
    mark(row);
  }

  function select(i) {
    var list = rows();
    if (!list.length) { idx = -1; return; }
    idx = Math.max(0, Math.min(i, list.length - 1));
    focusRow(list[idx]);
  }

  function current() {
    var list = rows();
    return idx >= 0 && idx < list.length ? list[idx] : null;
  }

  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    var tag = ((e.target && e.target.tagName) || '').toUpperCase();
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

    var row = current();
    if (e.key === 'j') { keyboard = true; select(idx + 1); e.preventDefault(); }
    else if (e.key === 'k') { keyboard = true; select(idx - 1); e.preventDefault(); }
    else if (e.key === 's' && row) {
      var skip = row.querySelector('.review-skip');
      if (skip) { keyboard = true; skip.click(); e.preventDefault(); }
    } else if (/^[1-9]$/.test(e.key) && row) {
      var sel = row.querySelector('.review-cat');
      var n = Number(e.key) - 1;
      if (sel && sel.options[n]) {
        sel.selectedIndex = n;
        keyboard = true;
        focusRow(row);
        e.preventDefault();
      }
    }
  });

  // Своп строки (approve/skip) или всей очереди (bulk) — вернуть фокус на текущую позицию.
  document.body.addEventListener('htmx:afterSwap', function () {
    if (!keyboard) return;
    var list = rows();
    if (!list.length) { idx = -1; return; }
    if (idx >= list.length) idx = list.length - 1;
    focusRow(list[idx]);
  });

  // Клик мышью делает строку текущей для последующих клавиш.
  tbody.addEventListener('click', function (e) {
    var tr = e.target && e.target.closest ? e.target.closest('tr.review-row') : null;
    if (!tr) return;
    idx = rows().indexOf(tr);
    mark(tr);
  });
})();
