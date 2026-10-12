from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .serializers import AuthUserSerializer, LoginSerializer, RegisterSerializer


def build_auth_payload(user: User) -> dict:
    """A fresh access/refresh token pair for `user`, plus who they are."""
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": AuthUserSerializer(user).data,
    }


class RegisterAPIView(APIView):
    """POST /api/auth/register/ — creates an account and logs it in.

    Request body: {"full_name": "...", "email": "...", "password": "..."}

    Response body (201 Created):
        {"access": "...", "refresh": "...",
         "user": {"id": int, "email": "...", "full_name": "..."}}

    On invalid input, a 400 with per-field error lists instead.
    """

    # No authentication here: a stale/expired token left in the client must
    # not turn a login or signup attempt into a 401.
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(build_auth_payload(user), status=status.HTTP_201_CREATED)


class LoginAPIView(APIView):
    """POST /api/auth/login/ — exchanges an email/password pair for tokens.

    Request body: {"email": "...", "password": "..."}

    Response body (200 OK): same shape as `RegisterAPIView`.

    On a wrong email or password, a 401 with {"detail": "..."} instead.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            credential_errors = serializer.errors.get("non_field_errors")
            if credential_errors:
                return Response(
                    {"detail": credential_errors[0]},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            build_auth_payload(serializer.validated_data["user"]),
            status=status.HTTP_200_OK,
        )
