from django.contrib import admin

from banks.models import Bank, LoanPolicy


@admin.register(Bank)
class BankAdmin(admin.ModelAdmin):
    list_display = ("name", "is_islamic", "main_page_url")
    search_fields = ("name",)
    list_filter = ("is_islamic",)


@admin.register(LoanPolicy)
class LoanPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "bank",
        "loan_type",
        "min_income",
        "max_loan_amount",
        "profit_rate",
        "updated_at",
    )
    list_filter = ("loan_type", "bank")
    search_fields = ("bank__name",)
