from django.contrib.auth.models import AbstractUser
from django.db import models


class EmploymentType(models.TextChoices):
    SALARIED = "Salaried", "Salaried"
    SELF_EMPLOYED = "Self-Employed", "Self-Employed"
    BUSINESS = "Business", "Business"


class User(AbstractUser):
    phone_number = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return self.username


class EmploymentStatus(models.TextChoices):
    SALARIED = "salaried", "Salaried"
    SELF_EMPLOYED = "self_employed", "Self-Employed"
    BUSINESS_OWNER = "business_owner", "Business Owner"


class Employment(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="employment"
    )
    employment_type = models.CharField(max_length=20, choices=EmploymentStatus.choices)
    employer_name = models.CharField(max_length=255, blank=True, null=True)
    monthly_net_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00
    )
    work_experience_years = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.employment_type}"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=255)
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2)
    credit_score = models.IntegerField()
    age = models.IntegerField()
    employment_type = models.CharField(max_length=20, choices=EmploymentType.choices)

    def __str__(self):
        return self.full_name


class ChatSession(models.Model):
    """One `mcp_server` chat conversation — the Postgres-side anchor for
    whatever that session produced.

    Primary-keyed by the same UUID string as its MongoDB `chat_logs`
    transcript (see `mcp_server.chat_history`), so the two stores are always
    addressable by the same id without a second lookup. Created lazily — see
    `mcp_server.persistence.save_loan_request` — the moment a session's
    slot-filling completes and its first `LoanRequest` needs somewhere to
    point; a session that never completes one never gets a row here.

    Deleting this row cascades to delete every `LoanRequest` (i.e. every
    report) it produced (see `LoanRequest.chat_session`) — the Mongo
    transcript itself is a separate delete (`mcp_server.chat_history.
    delete_session_chat_history`), since Django's ORM has no reach into
    MongoDB.
    """

    id = models.CharField(max_length=64, primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_sessions",
        help_text="Null for guest/anonymous chat sessions.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        owner = self.user.username if self.user_id else "guest"
        return f"{owner} - {self.id}"


class LoanRequestType(models.TextChoices):
    PERSONAL = "personal", "Personal"
    HOME = "home", "Home"
    AUTO = "auto", "Auto"


class LoanRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ANALYZED = "analyzed", "Analyzed"
    RECOMMENDED = "recommended", "Recommended"


class LoanRequest(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loan_requests",
        help_text="Null for guest/anonymous chat sessions.",
    )
    chat_session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="loan_requests",
        help_text="The chat session this report was generated in. Deleting the session deletes this row too.",
    )
    loan_type = models.CharField(max_length=20, choices=LoanRequestType.choices)
    required_amount = models.DecimalField(max_digits=12, decimal_places=2)
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_islamic = models.BooleanField(default=False)
    desired_tenure_years = models.PositiveIntegerField(default=1)
    additional_details = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=LoanRequestStatus.choices,
        default=LoanRequestStatus.ANALYZED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        owner = self.user.username if self.user_id else "guest"
        return f"{owner} - {self.loan_type} ({self.status})"
