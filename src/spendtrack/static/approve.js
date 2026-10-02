// Клавиатурный триаж очереди /approve (дизайн-ревью M-4): j/k — строки, Enter — одобрить,
// s — пропустить, 1–9 — категория. Фокус — на реальной кнопке строки (a11y + нативный Enter).
// После approve/skip htmx удаляет строку — фокус возвращаем на ту же позицию списка.
//
// Адъюдикация 02.10 (Astra S1/S3/O3):
//   * S3: bulk-approve делает `hx-swap="outerHTML"` по `#review-rows` — статичная ссылка на
//     tbody после этого указывала на отсоединённый узел; все обращения идут через getTbody(),
//     а click/pointerdown делегированы на document (слушатели не теряются при пересоздании);
//   * S1: htmx:afterSwap реагирует только на свап самой очереди — OOB-обновление счётчика
//     больше не «крадёт» фокус при фоновых свапах;
//   * O3: шорткаты 1–9 диспатчат change на селекте (hx-trigger="change" в шаблоне).
(function () {
  'use strict';

  if (!document.getElementById('review-rows')) return;

  var idx = -1;
  var keyboard = false;

  function getTbody() {
    return document.getElementById('review-rows');
  }

  function rows() {
    var tb = getTbody();
    return tb ? Array.prototype.slice.call(tb.querySelectorAll('tr.review-row')) : [];
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
        // O3 (Astra 02.10): selectedIndex не диспатчит change — hx-trigger="change" на селекте
        // (если задан в шаблоне) молча не сработал бы.
        sel.dispatchEvent(new Event('change', { bubbles: true }));
        keyboard = true;
        focusRow(row);
        e.preventDefault();
      }
    }
  });

  // Своп строки (approve/skip) или всей очереди (bulk) — вернуть фокус на текущую позицию.
  document.addEventListener('htmx:afterSwap', function (e) {
    if (!keyboard) return;
    // S1 (Astra 02.10): реагируем только на свап самой очереди — OOB-обновление счётчика или
    // чужой регион не должны перекидывать фокус (фоновые свапы «крали» фокус без действий юзера).
    var tgt = e.detail && e.detail.target;
    var tb = getTbody();
    if (!tgt || !tb || (tgt !== tb && !tb.contains(tgt))) return;
    var list = rows();
    if (!list.length) { idx = -1; return; }
    if (idx >= list.length) idx = list.length - 1;
    focusRow(list[idx]);
  });

  // Клик мышью делает строку текущей для последующих клавиш (делегирование: tbody пересоздаётся).
  document.addEventListener('click', function (e) {
    var tb = getTbody();
    if (!tb) return;
    var tr = e.target && e.target.closest ? e.target.closest('tr.review-row') : null;
    if (!tr || !tb.contains(tr)) return;
    idx = rows().indexOf(tr);
    mark(tr);
  });

  // Мышь вне очереди — выходим из клавиатурного режима: иначе следующий htmx-своп
  // вернёт фокус на строку и помешает работе с select/кнопками (ревью 24.09, P2).
  document.addEventListener('pointerdown', function (e) {
    var tb = getTbody();
    if (!tb || !tb.contains(e.target)) keyboard = false;
  });
})();
