(() => {
  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#primary-nav');
  toggle.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(open));
    toggle.querySelector('.sr-only').textContent = open ? 'Chiudi il menu' : 'Apri il menu';
    nav.classList.toggle('is-open', open);
  });
  nav.addEventListener('click', (event) => {
    if (event.target.closest('a')) {
      nav.classList.remove('is-open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.querySelector('.sr-only').textContent = 'Apri il menu';
    }
  });
  document.querySelectorAll('.service-card').forEach((card) => {
    card.addEventListener('click', () => {
      const service = card.dataset.service;
      const select = document.querySelector('#service');
      select.value = service;
      document.querySelector('#richiesta').scrollIntoView({ behavior: 'smooth' });
      window.setTimeout(() => select.focus(), 450);
    });
  });
  const upload = document.querySelector('#upload');
  upload.addEventListener('change', () => {
    const list = document.querySelector('.file-list');
    list.textContent = upload.files.length ? `${upload.files.length} file selezionat${upload.files.length === 1 ? 'o' : 'i'} (solo anteprima locale)` : 'Nessun file selezionato';
  });
  document.querySelector('#request-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const feedback = document.querySelector('#form-feedback');
    if (!form.reportValidity()) {
      feedback.textContent = 'Completa i campi richiesti per vedere il riepilogo dimostrativo.';
      return;
    }
    const name = document.querySelector('#full-name').value.trim();
    const service = document.querySelector('#service').value || 'servizio da definire';
    feedback.textContent = `Riepilogo demo pronto per ${name}: ${service}. Nessun dato è stato inviato.`;
  });
})();
