"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import os

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('', include('core.urls')),
    path("accounts/", include("django.contrib.auth.urls")),
    path("users/", include("users.urls")),
    path("matches/", include("matches.urls")),
    path("predictions/", include("predictions.urls")),
    path("ranking/", include("rankings.urls")),
    path("stats/", include("stats.urls")),
    path('admin/', admin.site.urls),
]

# Servir media files en desarrollo o cuando se habilite explicitamente (Render)
if settings.DEBUG or os.environ.get('SERVE_MEDIA', 'False').lower() == 'true':
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
