(() => {
  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#primary-nav');

  function setMenu(open) {
    toggle.setAttribute('aria-expanded', String(open));
    toggle.querySelector('.sr-only').textContent = open ? 'Chiudi menu' : 'Apri menu';
    nav.classList.toggle('is-open', open);
  }

  toggle.addEventListener('click', () => {
    setMenu(toggle.getAttribute('aria-expanded') !== 'true');
  });

  nav.addEventListener('click', event => {
    if (event.target.closest('a')) setMenu(false);
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
      setMenu(false);
      toggle.focus();
    }
  });

  document.addEventListener('click', event => {
    if (!nav.contains(event.target) && !toggle.contains(event.target)) setMenu(false);
  });

  const form = document.querySelector('#request-form');
  const feedback = document.querySelector('#form-feedback');
  form.addEventListener('submit', event => {
    event.preventDefault();
    feedback.classList.remove('is-error');
    if (!form.reportValidity()) {
      feedback.textContent = 'Controlla i campi obbligatori evidenziati.';
      feedback.classList.add('is-error');
      return;
    }
    feedback.textContent = 'Demo: richiesta compilata. Nessun dato è stato inviato.';
  });

  form.addEventListener('input', () => {
    if (feedback.textContent) feedback.textContent = '';
  });
})();
