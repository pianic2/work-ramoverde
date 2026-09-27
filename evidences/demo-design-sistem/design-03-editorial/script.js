(() => {
  const menuButton = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#primary-nav');
  if (menuButton && nav) {
    menuButton.addEventListener('click', () => {
      const isOpen = menuButton.getAttribute('aria-expanded') === 'true';
      menuButton.setAttribute('aria-expanded', String(!isOpen));
      nav.classList.toggle('is-open', !isOpen);
    });
    nav.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
      menuButton.setAttribute('aria-expanded', 'false');
      nav.classList.remove('is-open');
    }));
  }

  const fileInput = document.querySelector('#media');
  const fileList = document.querySelector('#file-list');
  fileInput?.addEventListener('change', () => {
    const files = Array.from(fileInput.files || []);
    fileList.textContent = files.length ? files.map((file) => file.name).join(', ') : 'Nessun file selezionato';
  });

  document.querySelector('#request-form')?.addEventListener('submit', (event) => {
    event.preventDefault();
    const response = document.querySelector('#form-response');
    if (!event.currentTarget.reportValidity()) return;
    response.textContent = 'Richiesta dimostrativa compilata. Nessun dato è stato inviato.';
  });
})();
