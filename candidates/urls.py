from django.urls import path

from candidates import views

urlpatterns = [
    path("candidates/", views.candidate_list, name="candidate_list"),
    path("candidates/new/", views.candidate_create, name="candidate_create"),
    path("candidates/<int:pk>/", views.candidate_detail, name="candidate_detail"),
    path("candidates/<int:pk>/upload-resume/", views.candidate_upload_resume, name="candidate_upload_resume"),
    path("candidates/<int:pk>/apply/", views.candidate_apply, name="candidate_apply"),
    path("pipeline/", views.pipeline, name="pipeline"),
    path("applications/<int:pk>/status/", views.application_status, name="application_status"),
]
