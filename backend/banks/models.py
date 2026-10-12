from django.db import models


class LoanCategory(models.TextChoices):
    PERSONAL = "Personal", "Personal"
    VEHICLE = "Vehicle", "Vehicle"
    HOME = "Home", "Home"


class Bank(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_islamic = models.BooleanField(default=False)
    main_page_url = models.URLField(
        max_length=500,
        help_text="Official main website URL of the bank",
    )

    class Meta:
        db_table = "core_bank"

    def __str__(self):
        return f"{self.name} (ID: {self.id})"


class LoanPolicy(models.Model):
    bank = models.ForeignKey(
        Bank, on_delete=models.CASCADE, related_name="loan_policies"
    )
    loan_type = models.CharField(max_length=20, choices=LoanCategory.choices)
    min_income = models.DecimalField(max_digits=12, decimal_places=2)
    max_dti_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=50.00
    )
    min_age = models.IntegerField(default=21)
    max_age = models.IntegerField(default=60)
    max_loan_amount = models.DecimalField(max_digits=14, decimal_places=2)
    profit_rate = models.DecimalField(max_digits=5, decimal_places=2)
    min_downpayment_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00
    )
    max_tenure_years = models.IntegerField()
    is_islamic = models.BooleanField(default=False)
    policy_details = models.JSONField(
        blank=True,
        null=True,
        help_text="Granular policy terms: full terms & conditions, required documents, and interest/profit calculation formulas.",
    )
    raw_scraped_data = models.JSONField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_loanpolicy"
        constraints = [
            models.UniqueConstraint(
                fields=["bank", "loan_type"],
                name="unique_loan_policy_per_bank_and_type",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.is_islamic and self.bank_id and self.bank.is_islamic:
            self.is_islamic = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[Bank ID: {self.bank_id}] {self.loan_type}"
