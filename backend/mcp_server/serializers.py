from rest_framework import serializers


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(allow_blank=False, trim_whitespace=True)
    session_id = serializers.CharField(
        required=False, allow_null=True, allow_blank=False, default=None
    )
    state = serializers.JSONField(required=False, default=dict)
    loan_request_id = serializers.IntegerField(
        required=False, allow_null=True, default=None
    )

    def validate_state(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("state must be a JSON object.")
        return value


class ChatHistoryQuerySerializer(serializers.Serializer):
    session_id = serializers.CharField(allow_blank=False)
    limit = serializers.IntegerField(
        required=False, default=20, min_value=1, max_value=100
    )
