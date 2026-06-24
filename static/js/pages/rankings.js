document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-progress-width]').forEach(function (progressBar) {
        const width = Number(progressBar.dataset.progressWidth);
        if (Number.isFinite(width)) {
            progressBar.style.width = `${Math.max(0, Math.min(100, width))}%`;
        }
    });

    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

