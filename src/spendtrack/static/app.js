// Клиентские обработчики spend-tracker. Вынесены из inline-скриптов/`hx-on::*`
// (строгий CSP: script-src 'self', htmx.config.allowEval=false — см. base.html).
(function () {
  'use strict';

  // Тост: показать сообщение после OOB-свопа (htmx:oobAfterSwap)
  document.body.addEventListener('htmx:oobAfterSwap', function () {
    var t = document.getElementById('toast');
    if (!t || t.dataset.flash !== '1') return;
    t.dataset.flash = '0';
    t.classList.remove('opacity-0');
    clearTimeout(window.__toastTimer);
    window.__toastTimer = setTimeout(function () { t.classList.add('opacity-0'); }, 1800);
  });

  // После запросов форм главной: обновить список и счётчик очереди
  document.body.addEventListener('htmx:afterRequest', function (e) {
    var el = e.detail && e.detail.elt;
    if (!el || !el.id) return;
    if (el.id === 'add-form') {
      if (!e.detail.successful) return; // при ошибке форму не сбрасываем
      el.reset();
      fetch('/api/pending-count')
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var cnt = document.getElementById('pending-count');
          if (cnt) cnt.textContent = d.count;
        })
        .catch(function () { /* счётчик не критичен */ });
      htmx.trigger('body', 'refresh-list');
    } else if (el.id === 'import-form') {
      htmx.trigger('body', 'refresh-list');
    }
  });
})();
