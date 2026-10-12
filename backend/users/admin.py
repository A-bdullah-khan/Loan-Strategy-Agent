from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from users.models import ChatSession, Employment, LoanRequest, User, UserProfile


class EmploymentInline(admin.StackedInline):
    model = Employment
    can_delete = False


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Additional Info", {"fields": ("phone_number",)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Additional Info", {"fields": ("phone_number",)}),
    )
    inlines = (EmploymentInline,)


@admin.register(Employment)
class EmploymentAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "employment_type",
        "employer_name",
        "monthly_net_income",
        "work_experience_years",
    )
    list_filter = ("employment_type",)
    search_fields = ("user__username", "employer_name")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "employment_type",
        "monthly_income",
        "credit_score",
        "age",
    )
    list_filter = ("employment_type",)
    search_fields = ("full_name",)


@admin.register(LoanRequest)
class LoanRequestAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "chat_session",
        "loan_type",
        "required_amount",
        "monthly_income",
        "is_islamic",
        "desired_tenure_years",
        "status",
        "created_at",
    )
    list_filter = ("loan_type", "is_islamic", "status")
    search_fields = ("user__username", "chat_session__id")


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "created_at")
    search_fields = ("id", "user__username")
