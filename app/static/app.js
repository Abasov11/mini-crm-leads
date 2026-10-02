// Живой список: сервер шлёт события через SSE, страница перерисовывает нужный кусок.
(function () {
  var live = document.getElementById('live');

  function refresh(select, after) {
    htmx.ajax('GET', location.pathname + location.search, { target: select, select: select, swap: 'outerHTML' })
      .then(after || function () {});
  }

  if (live && window.EventSource) {
    var es = new EventSource('/events');
    es.onmessage = function (e) {
      var ev = JSON.parse(e.data);
      if (live.dataset.page === 'list') {
        refresh('#workspace', function () {
          var row = document.querySelector('tr[data-id="' + ev.lead_id + '"]');
          if (row && ev.kind === 'new') row.classList.add('flash');
        });
      } else if (live.dataset.page === 'lead' && String(ev.lead_id) === live.dataset.id && ev.kind === 'update') {
        // в открытой карточке обновляем только историю, чтобы не затереть то, что человек сейчас правит
        refresh('#messages');
      }
    };
  }

  // клик по строке открывает лида
  document.addEventListener('click', function (e) {
    var row = e.target.closest('tr[data-href]');
    if (row && !e.target.closest('a, button')) location.href = row.dataset.href;
    var add = e.target.closest('[data-add-tag]');
    if (add) {
      var input = document.getElementById('tags');
      var cur = input.value.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
      if (cur.indexOf(add.dataset.addTag) < 0) cur.push(add.dataset.addTag);
      input.value = cur.join(', ');
    }
  });

  // чекбокс-переключатель отправляет свою форму
  document.addEventListener('change', function (e) {
    if (e.target.matches('[data-submit]')) htmx.trigger(e.target.form, 'submit');
  });

  // после добавления тега поле очищается и остаётся в фокусе
  document.addEventListener('htmx:afterSwap', function (e) {
    if (e.target.id === 'tags' || (e.detail.target && e.detail.target.id === 'tags')) {
      var i = document.querySelector('#tags input[name=name]');
      if (i) i.focus();
    }
  });
})();

// ошибка сохранения в карточке видна рядом с полем, а не теряется молча
document.addEventListener('htmx:responseError', function (e) {
  var saved = document.getElementById('saved');
  if (saved && e.detail.target === saved) {
    saved.textContent = e.detail.xhr.responseText || 'Не сохранилось, попробуйте ещё раз';
    saved.classList.add('saved-error');
  }
});
document.addEventListener('htmx:beforeRequest', function (e) {
  var saved = document.getElementById('saved');
  if (saved && e.detail.target === saved) saved.classList.remove('saved-error');
});
