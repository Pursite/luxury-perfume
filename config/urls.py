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
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from config.health import live, ready, startup


urlpatterns = [
    path("health/live", live, name="health-live"),
    path("health/ready", ready, name="health-ready"),
    path("health/startup", startup, name="health-startup"),
    path('admin/', admin.site.urls),
    path("api/v1/users/", include("apps.users.urls", namespace="users")),
    path("api/v1/products/", include("apps.products.urls", namespace="products")),
    path("api/v1/cart/", include("apps.cart.urls", namespace="cart")),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
