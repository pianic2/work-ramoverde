(() => {
  const menuButton = document.querySelector('.menu-toggle');
  const mobileMenu = document.querySelector('#mobile-menu');
  if (menuButton && mobileMenu) {
    const closeMenu = () => {
      menuButton.setAttribute('aria-expanded', 'false');
      mobileMenu.hidden = true;
      menuButton.querySelector('.sr-only').textContent = 'Apri il menu';
    };
    menuButton.addEventListener('click', () => {
      const open = menuButton.getAttribute('aria-expanded') === 'true';
      menuButton.setAttribute('aria-expanded', String(!open));
      mobileMenu.hidden = open;
      menuButton.querySelector('.sr-only').textContent = open ? 'Apri il menu' : 'Chiudi il menu';
    });
    mobileMenu.addEventListener('click', event => {
      const link = event.target.closest('a');
      if (link) {
        const selected = link.dataset.service;
        if (selected) document.querySelector('#service').value = selected;
        closeMenu();
      }
    });
    window.addEventListener('resize', () => { if (window.innerWidth > 700) closeMenu(); });
  }

  document.querySelectorAll('.service-row[data-service]').forEach(link => {
    link.addEventListener('click', () => {
      const service = document.querySelector('#service');
      if (service) service.value = link.dataset.service;
    });
  });

  const form = document.querySelector('#contact-form');
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const feedback = document.querySelector('#form-feedback');
    feedback.textContent = 'Richiesta dimostrativa pronta. Nessun dato è stato inviato.';
    feedback.classList.add('is-complete');
  });

  const motionAllowed = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (motionAllowed && 'IntersectionObserver' in window) {
    document.documentElement.classList.add('reveal-ready');
    const targets = document.querySelectorAll('.service-row,.path-steps li,.story-photo,.story-note,.path-image');
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('in-view');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -35px 0px' });
    targets.forEach((target, index) => {
      target.style.transitionDelay = `${Math.min(index % 5, 4) * 65}ms`;
      observer.observe(target);
    });
  }
})();
