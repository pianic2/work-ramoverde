(() => {
  const menuButton = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#main-nav');
  if (menuButton && nav) {
    const setMenu = (open) => {
      menuButton.setAttribute('aria-expanded', String(open));
      menuButton.querySelector('.sr-only').textContent = open ? 'Chiudi il menu' : 'Apri il menu';
      nav.classList.toggle('is-open', open);
    };
    menuButton.addEventListener('click', () => setMenu(menuButton.getAttribute('aria-expanded') !== 'true'));
    nav.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => setMenu(false)));
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && menuButton.getAttribute('aria-expanded') === 'true') {
        setMenu(false);
        menuButton.focus();
      }
    });
  }

  const fileInput = document.querySelector('#files');
  const uploadLabel = document.querySelector('.upload-control small');
  if (fileInput && uploadLabel) {
    fileInput.addEventListener('change', () => {
      uploadLabel.textContent = fileInput.files.length
        ? `${fileInput.files.length} file selezionat${fileInput.files.length === 1 ? 'o' : 'i'} · demo, non inviati`
        : 'Elemento dimostrativo — l’invio file non è attivo';
    });
  }

  const form = document.querySelector('#request-form');
  const feedback = document.querySelector('#form-feedback');
  if (form && feedback) {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      feedback.textContent = 'Richiesta compilata in modalità demo. Nessun dato è stato inviato.';
      feedback.focus();
    });
  }
})();
