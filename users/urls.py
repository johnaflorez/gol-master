from django.urls import path

from users.views import UserProfileUpdateView

urlpatterns = [
    path("profile/edit/", UserProfileUpdateView.as_view(), name="profile_edit"),
]

