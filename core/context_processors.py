from core.services.final_match_announcements import get_recent_final_match_announcements


def final_match_announcements(request):
    if not request.user.is_authenticated:
        return {"final_match_announcements": []}

    try:
        announcements = get_recent_final_match_announcements()
    except Exception:
        announcements = []

    return {
        "final_match_announcements": announcements,
    }

