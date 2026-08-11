from django.contrib import admin

from screening.models import ScreeningResult


@admin.register(ScreeningResult)
class ScreeningResultAdmin(admin.ModelAdmin):
    list_display = ("application", "ats_score", "verdict", "stage", "created_at")
    list_filter = ("verdict", "stage")
    search_fields = ("application__candidate__first_name", "application__candidate__last_name")
