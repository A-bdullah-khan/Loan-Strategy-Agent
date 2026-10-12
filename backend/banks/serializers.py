from rest_framework import serializers

from banks.models import Bank, LoanPolicy


class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = ["id", "name", "is_islamic", "main_page_url"]


class LoanPolicySerializer(serializers.ModelSerializer):
    bank = BankSerializer(read_only=True)

    class Meta:
        model = LoanPolicy
        fields = [
            "id",
            "bank",
            "loan_type",
            "min_income",
            "max_dti_percentage",
            "min_age",
            "max_age",
            "max_loan_amount",
            "profit_rate",
            "min_downpayment_percentage",
            "max_tenure_years",
            "is_islamic",
            "policy_details",
            "raw_scraped_data",
            "updated_at",
        ]
