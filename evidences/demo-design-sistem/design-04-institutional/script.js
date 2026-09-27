const menuButton = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#primary-nav');

menuButton?.addEventListener('click', () => {
  const isOpen = menuButton.getAttribute('aria-expanded') === 'true';
  menuButton.setAttribute('aria-expanded', String(!isOpen));
  menuButton.querySelector('.sr-only').textContent = isOpen ? 'Apri menu' : 'Chiudi menu';
  navigation.classList.toggle('is-open', !isOpen);
});

navigation?.querySelectorAll('a').forEach((link) => {
  link.addEventListener('click', () => {
    menuButton?.setAttribute('aria-expanded', 'false');
    const label = menuButton?.querySelector('.sr-only');
    if (label) label.textContent = 'Apri menu';
    navigation.classList.remove('is-open');
  });
});

document.querySelector('#files')?.addEventListener('change', (event) => {
  const files = [...event.target.files];
  const output = document.querySelector('.file-name');
  output.textContent = files.length ? `${files.length} file selezionati (solo demo)` : '';
});

document.querySelector('#request-form')?.addEventListener('submit', (event) => {
  event.preventDefault();
  const alert = document.querySelector('.form-alert');
  alert.hidden = false;
  alert.focus?.();
});
