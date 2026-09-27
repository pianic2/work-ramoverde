const menuButton = document.querySelector('.menu-toggle');
const primaryNav = document.querySelector('#primary-nav');

menuButton?.addEventListener('click', () => {
  const isOpen = menuButton.getAttribute('aria-expanded') === 'true';
  menuButton.setAttribute('aria-expanded', String(!isOpen));
  menuButton.querySelector('.visually-hidden').textContent = isOpen ? 'Apri il menu' : 'Chiudi il menu';
  primaryNav.classList.toggle('is-open', !isOpen);
});

primaryNav?.querySelectorAll('a').forEach((link) => {
  link.addEventListener('click', () => {
    primaryNav.classList.remove('is-open');
    menuButton?.setAttribute('aria-expanded', 'false');
    const label = menuButton?.querySelector('.visually-hidden');
    if (label) label.textContent = 'Apri il menu';
  });
});

const attachmentInput = document.querySelector('#attachments');
const uploadTitle = document.querySelector('.upload-control b');
const uploadDescription = document.querySelector('.upload-control small');
attachmentInput?.addEventListener('change', () => {
  if (attachmentInput.files.length) {
    uploadTitle.textContent = `${attachmentInput.files.length} file selezionat${attachmentInput.files.length === 1 ? 'o' : 'i'}`;
    uploadDescription.textContent = 'Anteprima locale: i file non vengono caricati.';
  } else {
    uploadTitle.textContent = 'Aggiungi foto o video';
    uploadDescription.textContent = 'Elemento dimostrativo, nessun file viene caricato';
  }
});

document.querySelector('#request-form')?.addEventListener('submit', (event) => {
  event.preventDefault();
  const feedback = document.querySelector('#form-feedback');
  feedback.textContent = 'Demo interattiva: nessun dato è stato inviato o memorizzato.';
  feedback.classList.add('is-active');
});
