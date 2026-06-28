document.addEventListener('DOMContentLoaded', function () {
    if (typeof bootstrap !== 'undefined') {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }

    const liveConfig = document.getElementById('dashboard-live-config');
    const liveSnapshotUrl = liveConfig ? liveConfig.dataset.liveSnapshotUrl : '';
    const baseRefreshDelay = 15000;
    const maxRefreshDelay = 60000;
    let refreshDelay = baseRefreshDelay;
    let refreshTimer = null;
    let isRefreshing = false;

    function renderLiveStatus(match) {
        const statusEl = document.getElementById(`live-status-${match.id}`);
        const minuteEl = document.getElementById(`live-minute-${match.id}`);
        const eventsEl = document.getElementById(`live-events-${match.id}`);

        if (!statusEl) {
            return;
        }

        if (match.status === "FT") {
            statusEl.className = "badge text-bg-secondary";
            statusEl.innerHTML = `<i class="fas fa-check-circle me-1"></i>${match.home_score} - ${match.away_score}`;
            minuteEl.textContent = "";
        } else if (match.status === "HT") {
            statusEl.className = "badge text-bg-warning";
            statusEl.innerHTML = `<i class="fas fa-pause me-1"></i>Descanso ${match.home_score} - ${match.away_score}`;
            minuteEl.textContent = "";
        } else if (match.status === "LIVE") {
            statusEl.className = "badge text-bg-success";
            statusEl.innerHTML = `<i class="fas fa-circle-play me-1"></i>En juego ${match.home_score} - ${match.away_score}`;
            minuteEl.textContent = match.live_minute ? `${match.live_minute}'` : "";
        } else {
            statusEl.className = "badge text-bg-dark";
            statusEl.innerHTML = `<i class="fas fa-hourglass-half me-1"></i>Por jugar`;
            minuteEl.textContent = "";
        }

        if (eventsEl) {
            eventsEl.replaceChildren();
            if (match.events && match.events.length) {
                const icon = document.createElement('i');
                icon.className = 'fas fa-bolt me-1';
                eventsEl.appendChild(icon);
                eventsEl.appendChild(document.createTextNode(match.events.map((event) => event.text).join(' | ')));
            }
        }
    }

    function escapeHtml(value) {
        const div = document.createElement("div");
        div.textContent = value || "";
        return div.innerHTML;
    }

    function renderFinalMatchAnnouncements(announcements) {
        const container = document.getElementById("final-match-marquee-container");
        if (!container) {
            return;
        }

        if (!announcements || !announcements.length) {
            container.classList.add("d-none");
            container.innerHTML = "";
            return;
        }

        container.classList.remove("d-none");
        const messages = announcements.map((announcement, index) => `
            <span class="final-match-marquee__text" data-match-id="${announcement.match_id}" data-finished-at="${escapeHtml(announcement.finished_at)}">${escapeHtml(announcement.message)}</span>
            ${index < announcements.length - 1 ? '<span class="final-match-marquee__separator" aria-hidden="true">•</span>' : ''}
        `).join("");
        container.innerHTML = `
            <div class="final-match-marquee">
                <div class="final-match-marquee__track">${messages}</div>
            </div>
        `;
    }

    async function refreshLiveMatches() {
        if (!liveSnapshotUrl || isRefreshing || document.hidden) {
            return;
        }

        isRefreshing = true;
        try {
            const response = await fetch(liveSnapshotUrl, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                },
                cache: "no-store"
            });

            if (!response.ok) {
                refreshDelay = Math.min(refreshDelay * 2, maxRefreshDelay);
                return;
            }

            const payload = await response.json();
            (payload.matches || []).forEach(renderLiveStatus);
            renderFinalMatchAnnouncements(payload.final_match_announcements || []);
            refreshDelay = baseRefreshDelay;
        } catch (error) {
            // Keep UI stable if network requests fail intermittently.
            console.debug("Live refresh failed", error);
            refreshDelay = Math.min(refreshDelay * 2, maxRefreshDelay);
        } finally {
            isRefreshing = false;
            scheduleNextRefresh();
        }
    }

    function scheduleNextRefresh() {
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(refreshLiveMatches, refreshDelay);
    }

    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) {
            refreshDelay = baseRefreshDelay;
            refreshLiveMatches();
        }
    });

    refreshLiveMatches();
});

