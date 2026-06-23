from django.urls import path

from users.views import MediaDiagnosticsView, UserProfileUpdateView

urlpatterns = [
    path("profile/edit/", UserProfileUpdateView.as_view(), name="profile_edit"),
    path("media/diagnostics/", MediaDiagnosticsView.as_view(), name="media_diagnostics"),
]

