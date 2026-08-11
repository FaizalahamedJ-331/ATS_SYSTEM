from django.urls import path

from candidates import views

urlpatterns = [
    path("candidates/", views.candidate_list, name="candidate_list"),
    path("candidates/export/", views.candidate_export_csv, name="candidate_export_csv"),
    path("candidates/new/", views.candidate_create, name="candidate_create"),
    path("candidates/<int:pk>/", views.candidate_detail, name="candidate_detail"),
    path("candidates/<int:pk>/pin/", views.candidate_toggle_pin, name="candidate_toggle_pin"),
    path("candidates/<int:pk>/upload-resume/", views.candidate_upload_resume, name="candidate_upload_resume"),
    path("candidates/<int:pk>/apply/", views.candidate_apply, name="candidate_apply"),
    path("pipeline/", views.pipeline, name="pipeline"),
    path("applications/<int:pk>/status/", views.application_status, name="application_status"),
    path("applications/<int:pk>/hire/", views.application_hired, name="application_hired"),
    path("applications/<int:pk>/note/", views.application_note, name="application_note"),
]
