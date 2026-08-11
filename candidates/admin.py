from django.contrib import admin

from candidates.models import Application, ApplicationEvent, Candidate, Resume


class ResumeInline(admin.TabularInline):
    model = Resume
    extra = 0


class ApplicationInline(admin.TabularInline):
    model = Application
    extra = 0


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "headline", "current_company", "source", "created_at")
    list_filter = ("source",)
    search_fields = ("first_name", "last_name", "email")
    inlines = [ResumeInline, ApplicationInline]


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ("candidate", "file_type", "created_at")
    search_fields = ("candidate__first_name", "candidate__last_name")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("candidate", "job", "status", "created_at")
    list_filter = ("status", "job")
    search_fields = ("candidate__first_name", "candidate__last_name", "job__title")


@admin.register(ApplicationEvent)
class ApplicationEventAdmin(admin.ModelAdmin):
    list_display = ("application", "kind", "text", "user", "created_at")
    list_filter = ("kind",)
    search_fields = ("text", "application__candidate__first_name", "application__candidate__last_name")
