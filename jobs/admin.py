from django.contrib import admin

from jobs.models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "department", "location", "experience_level", "status", "created_at")
    list_filter = ("status", "department", "experience_level")
    search_fields = ("title", "department", "location")
