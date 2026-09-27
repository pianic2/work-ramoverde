(() => {
  const menuButton = document.querySelector('.menu-toggle');
  const mobileMenu = document.querySelector('#mobile-menu');
  if (menuButton && mobileMenu) {
    menuButton.addEventListener('click', () => {
      const open = menuButton.getAttribute('aria-expanded') === 'true';
      menuButton.setAttribute('aria-expanded', String(!open));
      mobileMenu.hidden = open;
      menuButton.querySelector('.sr-only').textContent = open ? 'Apri il menu' : 'Chiudi il menu';
    });
    mobileMenu.addEventListener('click', event => {
      if (event.target.closest('a')) {
        mobileMenu.hidden = true;
        menuButton.setAttribute('aria-expanded', 'false');
        menuButton.querySelector('.sr-only').textContent = 'Apri il menu';
      }
    });
  }

  const serviceSelect = document.querySelector('#service');
  const serviceStatus = document.querySelector('#service-selection');
  document.querySelectorAll('.service-card[data-service]').forEach(card => {
    card.addEventListener('click', () => {
      const selected = card.dataset.service;
      serviceSelect.value = selected;
      document.querySelectorAll('.service-card').forEach(item => item.classList.toggle('is-selected', item === card));
      serviceStatus.textContent = `Hai selezionato “${selected}”. Il servizio è stato riportato nel modulo.`;
      serviceSelect.dispatchEvent(new Event('change', { bubbles: true }));
    });
  });
  serviceSelect.addEventListener('change', () => {
    const selected = serviceSelect.value;
    document.querySelectorAll('.service-card').forEach(card => card.classList.toggle('is-selected', card.dataset.service === selected));
    if (selected && !serviceStatus.textContent.includes(selected)) serviceStatus.textContent = `Servizio selezionato: ${selected}.`;
  });

  const form = document.querySelector('#request-form');
  const steps = [...document.querySelectorAll('.form-step')];
  const titles = ['Di cosa hai bisogno?', 'Come possiamo ricontattarti?', 'Controlla la richiesta'];
  const next = document.querySelector('#next-button');
  const back = document.querySelector('#back-button');
  const submit = document.querySelector('#submit-button');
  const counter = document.querySelector('#step-counter');
  const progress = document.querySelector('#progress-bar');
  const progressTrack = document.querySelector('[role="progressbar"]');
  const labels = [...document.querySelectorAll('.progress-labels span')];
  const title = document.querySelector('#step-title');
  const error = document.querySelector('#form-error');
  let current = 0;

  function renderStep(index) {
    current = index;
    steps.forEach((step, i) => {
      step.hidden = i !== index;
      step.classList.toggle('active', i === index);
    });
    title.textContent = titles[index];
    counter.innerHTML = `0${index + 1} <span>/ 03</span>`;
    progress.style.width = `${((index + 1) / steps.length) * 100}%`;
    progressTrack.setAttribute('aria-valuenow', String(index + 1));
    labels.forEach((label, i) => label.classList.toggle('current', i === index));
    back.hidden = index === 0;
    next.hidden = index === steps.length - 1;
    submit.hidden = index !== steps.length - 1;
    error.hidden = true;
  }
  function stepIsValid() {
    const requiredFields = [...steps[current].querySelectorAll('[required]')];
    const invalid = requiredFields.find(field => !field.checkValidity());
    if (invalid) {
      error.hidden = false;
      invalid.focus();
      invalid.reportValidity();
      return false;
    }
    error.hidden = true;
    return true;
  }
  function getValue(id, fallback) {
    const field = document.getElementById(id);
    return field && field.value.trim() ? field.value.trim() : fallback;
  }
  function updateSummary() {
    const values = {
      'service': getValue('service', 'Da selezionare'),
      'client-type': getValue('client-type', 'Da selezionare'),
      'zone': getValue('zone', 'Da indicare'),
      'area-size': getValue('area-size', 'Non indicata'),
      'contact': `${getValue('first-name', '')} ${getValue('last-name', '')} · ${getValue('phone', '')}`.trim() || 'Da indicare',
      'period': getValue('period', 'Da concordare')
    };
    Object.entries(values).forEach(([key, value]) => {
      document.querySelector(`[data-summary="${key}"]`).textContent = value;
    });
  }
  next.addEventListener('click', () => {
    if (!stepIsValid()) return;
    if (current === 1) updateSummary();
    renderStep(Math.min(current + 1, steps.length - 1));
    title.focus?.();
  });
  back.addEventListener('click', () => renderStep(Math.max(current - 1, 0)));
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!stepIsValid()) return;
    const existing = document.querySelector('.demo-complete');
    if (!existing) {
      const message = document.createElement('p');
      message.className = 'info-alert demo-complete';
      message.setAttribute('role', 'status');
      message.textContent = 'Flusso completato in modalità demo: nessun dato è stato inviato.';
      form.querySelector('.form-actions').after(message);
    }
    submit.textContent = 'Demo completata ✓';
    submit.disabled = true;
  });

  const fileInput = document.querySelector('#media');
  fileInput.addEventListener('change', () => {
    const names = [...fileInput.files].map(file => file.name);
    document.querySelector('#file-status').textContent = names.length ? `${names.length} file selezionat${names.length === 1 ? 'o' : 'i'} (solo anteprima locale)` : 'Nessun file selezionato';
  });
  renderStep(0);
})();
