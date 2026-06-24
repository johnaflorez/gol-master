document.addEventListener('DOMContentLoaded', function () {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    const liveConfig = document.getElementById('dashboard-live-config');
    const liveSnapshotUrl = liveConfig ? liveConfig.dataset.liveSnapshotUrl : '';

    function renderLiveStatus(match) {
        const statusEl = document.getElementById(`live-status-${match.id}`);
        const minuteEl = document.getElementById(`live-minute-${match.id}`);
        const eventsEl = document.getElementById(`live-events-${match.id}`);

        if (!statusEl) {
            return;
        }

        if (match.status === "FT") {
            statusEl.className = "badge text-bg-dark";
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
            if (match.events && match.events.length) {
                eventsEl.innerHTML = `<i class="fas fa-bolt me-1"></i>${match.events.map((event) => event.text).join(" | ")}`;
            } else {
                eventsEl.textContent = "";
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
        container.innerHTML = announcements.map((announcement) => `
            <div class="final-match-marquee" data-match-id="${announcement.match_id}" data-finished-at="${escapeHtml(announcement.finished_at)}">
                <div class="final-match-marquee__track">
                    <span class="final-match-marquee__text">${escapeHtml(announcement.message)}</span>
                </div>
            </div>
        `).join("");
    }

    async function refreshLiveMatches() {
        if (!liveSnapshotUrl) {
            return;
        }

        try {
            const response = await fetch(liveSnapshotUrl, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                }
            });

            if (!response.ok) {
                return;
            }

            const payload = await response.json();
            (payload.matches || []).forEach(renderLiveStatus);
            renderFinalMatchAnnouncements(payload.final_match_announcements || []);
        } catch (error) {
            // Keep UI stable if network requests fail intermittently.
            console.debug("Live refresh failed", error);
        }
    }

    refreshLiveMatches();
    setInterval(refreshLiveMatches, 15000);
});

