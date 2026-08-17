(() => {
  const menuButton = document.querySelector('.staff-menu-button');
  const menu = document.querySelector('.staff-sidebar');
  const backdrop = document.querySelector('[data-staff-backdrop]');

  const closeMenu = ({ returnFocus = false } = {}) => {
    const wasOpen = menu?.classList.contains('open');
    menu?.classList.remove('open');
    backdrop?.classList.remove('open');
    menuButton?.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('staff-menu-open');
    if (returnFocus && wasOpen) menuButton?.focus();
  };
  menuButton?.addEventListener('click', () => {
    const open = !menu.classList.contains('open');
    if (!open) {
      closeMenu();
      return;
    }
    menu.classList.add('open');
    backdrop?.classList.add('open');
    menuButton.setAttribute('aria-expanded', 'true');
    document.body.classList.add('staff-menu-open');
    menu.querySelector('a')?.focus();
  });
  backdrop?.addEventListener('click', () => closeMenu({ returnFocus: true }));

  document.querySelectorAll('[data-confirm]').forEach((form) => form.addEventListener('submit', (event) => {
    if (!confirm(form.dataset.confirm)) event.preventDefault();
  }));
  document.querySelector('[data-copy]')?.addEventListener('click', async (event) => {
    const input = document.querySelector('[data-copy-source]');
    try {
      await navigator.clipboard.writeText(input.value);
      event.currentTarget.textContent = 'Скопировано';
    } catch {
      input.select();
      document.execCommand('copy');
    }
  });

  const dialog = document.querySelector('.photo-dialog');
  const dialogImage = dialog?.querySelector('img');
  const dialogName = dialog?.querySelector('p');
  const dialogClose = dialog?.querySelector('[data-photo-close]');
  let photoOpener = null;
  const closeDialog = () => {
    if (!dialog?.open) return;
    dialog.close();
  };
  document.querySelectorAll('[data-photo]').forEach((photoButton) => photoButton.addEventListener('click', () => {
    if (!dialog) return;
    photoOpener = photoButton;
    dialogImage.src = photoButton.dataset.photo;
    dialogImage.alt = `Просмотр: ${photoButton.dataset.name || 'фотография заказа'}`;
    dialogName.textContent = photoButton.dataset.name || '';
    dialog.showModal();
    dialogClose?.focus();
  }));
  dialogClose?.addEventListener('click', closeDialog);
  dialog?.addEventListener('click', (event) => {
    if (event.target === dialog) closeDialog();
  });
  dialog?.addEventListener('close', () => {
    dialogImage?.removeAttribute('src');
    photoOpener?.focus();
    photoOpener = null;
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (dialog?.open) closeDialog();
    else closeMenu({ returnFocus: true });
  });
})();
