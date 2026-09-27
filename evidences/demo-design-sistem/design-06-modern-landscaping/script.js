(() => {
  const menuButton = document.querySelector('.menu-toggle');
  const mobileMenu = document.querySelector('#mobile-menu');

  if (menuButton && mobileMenu) {
    const closeMenu = () => {
      menuButton.setAttribute('aria-expanded', 'false');
      menuButton.setAttribute('aria-label', 'Apri il menu');
      mobileMenu.hidden = true;
    };

    menuButton.addEventListener('click', () => {
      const isOpen = menuButton.getAttribute('aria-expanded') === 'true';
      menuButton.setAttribute('aria-expanded', String(!isOpen));
      menuButton.setAttribute('aria-label', isOpen ? 'Apri il menu' : 'Chiudi il menu');
      mobileMenu.hidden = isOpen;
    });

    mobileMenu.querySelectorAll('a').forEach((link) => link.addEventListener('click', closeMenu));
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && menuButton.getAttribute('aria-expanded') === 'true') {
        closeMenu();
        menuButton.focus();
      }
    });
    document.addEventListener('click', (event) => {
      if (!mobileMenu.hidden && !mobileMenu.contains(event.target) && !menuButton.contains(event.target)) closeMenu();
    });
  }

  const fileInput = document.querySelector('#attachments');
  const fileNames = document.querySelector('.file-names');
  if (fileInput && fileNames) {
    fileInput.addEventListener('change', () => {
      const files = Array.from(fileInput.files || []);
      fileNames.textContent = files.length ? files.map((file) => file.name).join(', ') : '';
    });
  }

  const form = document.querySelector('#request-form');
  const response = document.querySelector('#form-response');
  if (form && response) {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      response.textContent = 'Demo visuale: richiesta compilata, nessun dato è stato inviato.';
    });
  }
})();
