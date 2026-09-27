(() => {
  const menuButton = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#primary-nav');
  const status = document.querySelector('#form-status');
  const fileInput = document.querySelector('#media');
  const fileName = document.querySelector('#file-name');

  if (menuButton && nav) {
    menuButton.addEventListener('click', () => {
      const isOpen = menuButton.getAttribute('aria-expanded') === 'true';
      menuButton.setAttribute('aria-expanded', String(!isOpen));
      menuButton.querySelector('.sr-only').textContent = isOpen ? 'Apri navigazione' : 'Chiudi navigazione';
      nav.classList.toggle('is-open', !isOpen);
    });
    nav.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
      menuButton.setAttribute('aria-expanded', 'false');
      menuButton.querySelector('.sr-only').textContent = 'Apri navigazione';
      nav.classList.remove('is-open');
    }));
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && nav.classList.contains('is-open')) {
        nav.classList.remove('is-open');
        menuButton.setAttribute('aria-expanded', 'false');
        menuButton.querySelector('.sr-only').textContent = 'Apri navigazione';
        menuButton.focus();
      }
    });
  }

  if (fileInput && fileName) {
    fileInput.addEventListener('change', () => {
      const count = fileInput.files?.length || 0;
      fileName.textContent = count ? `${count} file selezionat${count === 1 ? 'o' : 'i'} — anteprima dimostrativa, nessun invio.` : '';
    });
  }

  document.querySelector('#request-form')?.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    status.textContent = 'Dimostrazione completata: nessun dato è stato inviato o salvato.';
  });
})();
