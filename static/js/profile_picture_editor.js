(() => {
  'use strict';
  const MAX_BYTES = 5 * 1024 * 1024;
  const ALLOWED = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif']);
  const init = () => {
    const editor = document.querySelector('[data-profile-picture-editor]');
    const input = document.querySelector('[data-profile-picture-input]');
    const canvas = editor?.querySelector('[data-picture-canvas]');
    const stage = editor?.querySelector('[data-picture-stage]');
    const zoomInput = editor?.querySelector('[data-picture-zoom]');
    const saveButton = editor?.querySelector('[data-picture-save]');
    const error = editor?.querySelector('[data-picture-error]');
    const dialog = editor?.querySelector('.profile-picture-editor__dialog');
    const preview = document.querySelector('[data-avatar-preview]');
    if (!editor || !input || !canvas || !stage || !zoomInput || !saveButton || !dialog) return;

    const ctx = canvas.getContext('2d', { alpha: false });
    let image = null;
    let sourceUrl = '';
    let zoom = 1;
    let panX = 0;
    let panY = 0;
    let drag = null;
    let previousFocus = null;

    const showError = (message) => {
      if (!error) return;
      error.textContent = message;
      error.hidden = !message;
    };
    const bounds = () => {
      if (!image) return null;
      const base = Math.max(canvas.width / image.naturalWidth, canvas.height / image.naturalHeight);
      const width = image.naturalWidth * base * zoom;
      const height = image.naturalHeight * base * zoom;
      panX = Math.min(0, Math.max(canvas.width - width, panX));
      panY = Math.min(0, Math.max(canvas.height - height, panY));
      return { width, height, x: (canvas.width - width) / 2 + panX, y: (canvas.height - height) / 2 + panY };
    };
    const draw = () => {
      if (!ctx || !image) return;
      const b = bounds();
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#0b1424';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(image, b.x, b.y, b.width, b.height);
    };
    const open = () => {
      previousFocus = document.activeElement;
      editor.hidden = false;
      document.body.classList.add('profile-picture-editor-open');
      draw();
      dialog.focus();
      showError('');
    };
    const close = (cancelled) => {
      editor.hidden = true;
      document.body.classList.remove('profile-picture-editor-open');
      if (cancelled) input.value = '';
      if (sourceUrl) URL.revokeObjectURL(sourceUrl);
      sourceUrl = '';
      image = null;
      drag = null;
      if (previousFocus && typeof previousFocus.focus === 'function') previousFocus.focus();
    };
    const setPreview = (file) => {
      if (!preview) return;
      let img = preview.querySelector('img');
      if (!img) {
        img = document.createElement('img');
        img.alt = '';
        const initials = preview.querySelector(':scope > span:not(.account-avatar-edit)');
        if (initials) initials.remove();
        const editIcon = preview.querySelector('.account-avatar-edit');
        preview.insertBefore(img, editIcon || null);
      }
      const old = img.dataset.previewUrl;
      const url = URL.createObjectURL(file);
      img.src = url;
      img.dataset.previewUrl = url;
      if (old) URL.revokeObjectURL(old);
    };

    input.addEventListener('change', () => {
      const file = input.files && input.files[0];
      if (!file) return;
      if (!ALLOWED.has(file.type) || file.size > MAX_BYTES) {
        input.value = '';
        showError('Choose a JPEG, PNG, WEBP or GIF image no larger than 5 MB.');
        editor.hidden = false;
        document.body.classList.add('profile-picture-editor-open');
        dialog.focus();
        return;
      }
      if (sourceUrl) URL.revokeObjectURL(sourceUrl);
      sourceUrl = URL.createObjectURL(file);
      image = new Image();
      image.onload = () => {
        if (!image.naturalWidth || !image.naturalHeight || image.naturalWidth * image.naturalHeight > 25000000) {
          showError('This image is too large to edit. Choose an image with 25 megapixels or fewer.');
          return;
        }
        zoom = 1;
        panX = 0;
        panY = 0;
        zoomInput.value = '1';
        draw();
        open();
      };
      image.onerror = () => showError('The selected image could not be opened. Choose another image.');
      image.src = sourceUrl;
    });

    zoomInput.addEventListener('input', () => {
      const old = zoom;
      zoom = Number(zoomInput.value) || 1;
      const factor = zoom / old;
      panX *= factor;
      panY *= factor;
      draw();
    });
    stage.addEventListener('pointerdown', (event) => {
      if (!image || editor.hidden) return;
      drag = { x: event.clientX, y: event.clientY, panX, panY };
      stage.setPointerCapture?.(event.pointerId);
      stage.classList.add('is-dragging');
    });
    stage.addEventListener('pointermove', (event) => {
      if (!drag) return;
      panX = drag.panX + (event.clientX - drag.x) * (canvas.width / Math.max(stage.clientWidth, 1));
      panY = drag.panY + (event.clientY - drag.y) * (canvas.height / Math.max(stage.clientHeight, 1));
      draw();
    });
    const stopDrag = () => { drag = null; stage.classList.remove('is-dragging'); };
    stage.addEventListener('pointerup', stopDrag);
    stage.addEventListener('pointercancel', stopDrag);
    stage.addEventListener('lostpointercapture', stopDrag);

    saveButton.addEventListener('click', () => {
      if (!image) {
        showError('Choose an image before saving the crop.');
        return;
      }
      saveButton.disabled = true;
      saveButton.textContent = 'Preparing…';
      canvas.toBlob((blob) => {
        saveButton.disabled = false;
        saveButton.textContent = 'Use this picture';
        if (!blob) {
          showError('The crop could not be prepared. Please try another image.');
          return;
        }
        const baseName = (input.files?.[0]?.name || 'profile-picture').replace(/\.[^.]+$/, '');
        const cropped = new File([blob], baseName + '.webp', { type: 'image/webp', lastModified: Date.now() });
        try {
          const transfer = new DataTransfer();
          transfer.items.add(cropped);
          input.files = transfer.files;
          setPreview(cropped);
          showError('');
          close(false);
        } catch (_) {
          showError('Your browser could not prepare the edited image. Update your browser or choose another image.');
        }
      }, 'image/webp', 0.9);
    });

    editor.querySelectorAll('[data-picture-cancel]').forEach(button => button.addEventListener('click', () => close(true)));
    document.addEventListener('keydown', (event) => {
      if (editor.hidden) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        close(true);
      }
      if (event.key === 'Tab') {
        const focusable = Array.from(dialog.querySelectorAll('button:not(:disabled),input:not(:disabled)'));
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault(); last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault(); first.focus();
        }
      }
    });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
