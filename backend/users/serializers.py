from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import serializers

from users.models import Employment, LoanRequest, User, UserProfile

# `User.username` (max 150 chars) holds the account's email — see
# `RegisterSerializer.create` — so an email can't be longer than that.
EMAIL_MAX_LENGTH = 150
FULL_NAME_MAX_LENGTH = 150


class EmploymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employment
        fields = [
            "id",
            "employment_type",
            "employer_name",
            "monthly_net_income",
            "work_experience_years",
            "created_at",
            "updated_at",
        ]


class UserSerializer(serializers.ModelSerializer):
    employment = EmploymentSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "employment",
        ]


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            "id",
            "full_name",
            "monthly_income",
            "credit_score",
            "age",
            "employment_type",
        ]


class LoanRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanRequest
        fields = [
            "id",
            "user",
            "loan_type",
            "required_amount",
            "monthly_income",
            "is_islamic",
            "desired_tenure_years",
            "additional_details",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "created_at", "updated_at"]


class AuthUserSerializer(serializers.ModelSerializer):
    """The logged-in user as returned alongside their tokens."""

    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "full_name"]

    def get_full_name(self, user: User) -> str:
        return user.get_full_name()


class RegisterSerializer(serializers.Serializer):
    """Validates and creates a new account, keyed by its (case-insensitive) email."""

    full_name = serializers.CharField(
        max_length=FULL_NAME_MAX_LENGTH, trim_whitespace=True
    )
    email = serializers.EmailField(max_length=EMAIL_MAX_LENGTH)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        if User.objects.filter(
            Q(username__iexact=email) | Q(email__iexact=email)
        ).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )
        return email

    def validate(self, attrs: dict) -> dict:
        first_name, _, last_name = attrs["full_name"].partition(" ")
        attrs["first_name"] = first_name
        attrs["last_name"] = last_name.strip()
        # Run against an unsaved user so the similarity validator can compare
        # the password to the name/email being registered.
        candidate = User(
            username=attrs["email"],
            email=attrs["email"],
            first_name=attrs["first_name"],
            last_name=attrs["last_name"],
        )
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

    def create(self, validated_data: dict) -> User:
        return User.objects.create_user(
            username=validated_data["email"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
        )


class LoginSerializer(serializers.Serializer):
    """Checks an email/password pair; `validated_data['user']` is the matching account."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs: dict) -> dict:
        email = attrs["email"].strip().lower()
        # Accounts created outside `RegisterSerializer` (e.g. `createsuperuser`)
        # may have a username that isn't their email, so resolve it first.
        account = User.objects.filter(email__iexact=email).order_by("id").first()
        # Always goes through `authenticate` — even for an unknown email — so
        # the password hasher runs either way and response time doesn't
        # reveal which emails are registered.
        user = authenticate(
            request=self.context.get("request"),
            username=account.username if account else email,
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError("Incorrect email or password.")
        attrs["user"] = user
        return attrs
