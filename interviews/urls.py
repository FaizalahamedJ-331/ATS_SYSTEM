from django.urls import path

from interviews import views

urlpatterns = [
    path("interviews/", views.interview_list, name="interview_list"),
    path("interviews/schedule/", views.interview_schedule, name="interview_schedule"),
    path("interviews/<int:pk>/complete/", views.interview_complete, name="interview_complete"),
    path("interviews/<int:pk>/cancel/", views.interview_cancel, name="interview_cancel"),
]
