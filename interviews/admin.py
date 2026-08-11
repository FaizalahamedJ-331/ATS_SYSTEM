from django.contrib import admin

from interviews.models import Interview


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ("application", "interview_type", "scheduled_at", "status", "rating")
    list_filter = ("status", "interview_type")
    search_fields = ("application__candidate__first_name", "application__candidate__last_name")
