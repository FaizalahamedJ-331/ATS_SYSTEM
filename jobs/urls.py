from django.urls import path

from jobs import views

urlpatterns = [
    path("jobs/", views.job_list, name="job_list"),
    path("jobs/new/", views.job_create, name="job_create"),
    path("jobs/<int:pk>/", views.job_detail, name="job_detail"),
    path("jobs/<int:pk>/edit/", views.job_edit, name="job_edit"),
    path("jobs/<int:pk>/toggle-status/", views.job_toggle_status, name="job_toggle_status"),
    path("jobs/<int:pk>/screen/", views.job_screen, name="job_screen"),
]
