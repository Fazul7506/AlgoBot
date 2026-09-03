(() => {
  const refreshButton = document.querySelector('[data-alert-refresh]');
  if (!refreshButton) return;

  refreshButton.addEventListener('click', () => {
    window.location.reload();
  });
})();
