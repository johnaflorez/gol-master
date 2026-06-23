from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from users.models import UserProfile
from users.forms import UserProfileForm


class UserProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = UserProfile
    form_class = UserProfileForm
    template_name = "users/profile_edit.html"
    success_url = reverse_lazy("dashboard")

    def get_object(self, queryset=None):
        profile, created = UserProfile.objects.get_or_create(user=self.request.user)
        return profile

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except OSError:
            form.add_error(
                None,
                forms.ValidationError(
                    "No se pudo guardar la imagen en este momento. Intenta con otra imagen o vuelve a intentarlo más tarde."
                ),
            )
            return self.form_invalid(form)

