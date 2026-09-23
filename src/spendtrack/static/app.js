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

  // Панели «Импорт»/«Добавить» на главной (M-6): формы свёрнуты в кнопки шапки таблицы.
  function setPanel(btn, open) {
    var panel = document.getElementById(btn.getAttribute('aria-controls'));
    if (!panel) return;
    panel.toggleAttribute('hidden', !open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  document.body.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('[data-toggle]') : null;
    if (!btn) return;
    setPanel(btn, btn.getAttribute('aria-expanded') !== 'true');
  });

  // Ссылки /#import и /#add (лендинг, чек-лист, дашборд) открывают панель, а не «немой» якорь.
  function openFromHash() {
    var btn = document.getElementById((location.hash || '').replace('#', ''));
    if (btn && btn.hasAttribute('data-toggle')) setPanel(btn, true);
  }
  openFromHash();
  window.addEventListener('hashchange', openFromHash);

  // Drop-zone импорта: файл можно перетащить в зону.
  var drop = document.getElementById('import-drop');
  if (drop) {
    var fileInput = drop.querySelector('input[type=file]');
    ['dragenter', 'dragover'].forEach(function (t) {
      drop.addEventListener(t, function (e) { e.preventDefault(); drop.classList.add('border-accent'); });
    });
    ['dragleave', 'drop'].forEach(function (t) {
      drop.addEventListener(t, function (e) { e.preventDefault(); drop.classList.remove('border-accent'); });
    });
    drop.addEventListener('drop', function (e) {
      if (fileInput && e.dataTransfer && e.dataTransfer.files.length) fileInput.files = e.dataTransfer.files;
    });
  }
})();
