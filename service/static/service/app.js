document.addEventListener('DOMContentLoaded', () => {
  const button = document.querySelector('.menu-button');
  const menu = document.querySelector('#menu');
  const setMenu = (open, returnFocus = false) => {
    menu?.classList.toggle('open', open);
    button?.setAttribute('aria-expanded', String(open));
    button?.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
    document.body.classList.toggle('menu-open', open);
    if (returnFocus) button?.focus();
  };
  button?.addEventListener('click', () => setMenu(!menu?.classList.contains('open')));
  menu?.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => setMenu(false)));
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && menu?.classList.contains('open')) setMenu(false, true); });
  window.matchMedia('(min-width: 961px)').addEventListener('change', (event) => { if (event.matches) setMenu(false); });
  document.querySelectorAll('input[type=file]').forEach((input) => {
    const status = document.createElement('span');
    status.className = 'file-status';
    status.setAttribute('aria-live', 'polite');
    status.textContent = 'Файлы не выбраны';
    input.insertAdjacentElement('afterend', status);
    input.addEventListener('change', () => {
      const count = input.files?.length || 0;
      status.textContent = count ? `Выбрано файлов: ${count}` : 'Файлы не выбраны';
    });
  });
  document.querySelectorAll('[data-submit-form]').forEach((form) => form.addEventListener('submit', () => {
    const submit = form.querySelector('button[type=submit]');
    if (submit) { submit.disabled = true; submit.textContent = 'Отправляем…'; }
  }));
});
