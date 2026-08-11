from django.urls import path

from screening import views

urlpatterns = [
    path("screening/<int:pk>/", views.screening_detail, name="screening_detail"),
    path("screening/<int:pk>/rerun/", views.screening_rerun, name="screening_rerun"),
    path("screening/<int:pk>/ai/", views.screening_ai, name="screening_ai"),
]
