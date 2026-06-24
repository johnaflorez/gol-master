document.addEventListener('DOMContentLoaded', function () {
    const modalElement = document.getElementById('avatarPreviewModal');
    const modalImage = document.getElementById('avatarPreviewModalImage');
    const modalTitle = document.getElementById('avatarPreviewModalLabel');

    if (!modalElement || !modalImage || !modalTitle || typeof bootstrap === 'undefined') {
        return;
    }

    const avatarModal = new bootstrap.Modal(modalElement);

    function openAvatarPreview(trigger) {
        const avatarUrl = trigger.getAttribute('data-avatar-url');
        if (!avatarUrl) {
            return;
        }

        const avatarTitle = trigger.getAttribute('data-avatar-title') || 'Foto de perfil';
        modalImage.src = avatarUrl;
        modalImage.alt = avatarTitle;
        const titleIcon = document.createElement('i');
        titleIcon.className = 'fas fa-user-circle me-2 text-mundial-red';
        modalTitle.replaceChildren(titleIcon, document.createTextNode(avatarTitle));
        avatarModal.show();
    }

    document.addEventListener('click', function (event) {
        const trigger = event.target.closest('[data-avatar-url]');
        if (trigger) {
            openAvatarPreview(trigger);
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' && event.key !== ' ') {
            return;
        }

        const trigger = event.target.closest('[data-avatar-url]');
        if (trigger) {
            event.preventDefault();
            openAvatarPreview(trigger);
        }
    });

    modalElement.addEventListener('hidden.bs.modal', function () {
        modalImage.src = '';
    });
});

