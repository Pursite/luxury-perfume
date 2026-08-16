from rest_framework import serializers
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import CustomUser, Address
from .selectors import UserSelector

from django.core.validators import RegexValidator

username_regex = RegexValidator(
    regex=r'^[a-zA-Z0-9_]+$',
    message="Username must be entered in the format: '[a-zA-Z0-9_]+'."
)


PASSWORD_MAX_LENGTH = 128


def validate_password_policy(password, user):
    """Apply the project's single Django password policy to request input."""
    try:
        password_validation.validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"password": list(exc.messages)}) from exc


class NormalizedPhoneNumberSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=11, trim_whitespace=False)

    def validate_phone_number(self, value):
        value = CustomUser.normalize_phone_number(value)
        if not CustomUser.is_valid_phone_number(value):
            raise serializers.ValidationError(
                "Phone number must be entered in the format: '0912345678'."
            )
        return value


class PhoneInputSerializer(NormalizedPhoneNumberSerializer):
    pass


class VerifyOTPInputSerializer(NormalizedPhoneNumberSerializer):
    otp = serializers.CharField(
        max_length=6,
        min_length=6,
        validators=[RegexValidator(r"^[0-9]{6}$", "OTP must contain six ASCII digits.")],
        error_messages={
            'min_length': 'confirmation code must be at least 6 digits.',
            'max_length': 'confirmation code must be no more than 6 digits.'
        }
    )


class UserPassLoginInputSerializer(serializers.Serializer):
    username = serializers.CharField(
        max_length=150,
        error_messages={'required': 'username is required.'}
    )
    password = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'},
        error_messages={'required': 'password is required.'}
    )

    def validate_username(self, value):
        return CustomUser.normalize_username(value)


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ['id', 'title', 'full_address', 'postal_code']


class AddressInputSerializer(serializers.Serializer):
    title = serializers.CharField(
        max_length=50,
        error_messages={'max_length': 'title of address can`t be more than 50 characters.'}
    )
    full_address = serializers.CharField(
        error_messages={'required': 'exact address required.'}
    )
    postal_code = serializers.CharField(
        max_length=10,
        required=False,
        allow_blank=True,
        allow_null=True
    )


class AddressUpdateInputSerializer(AddressInputSerializer):
    id = serializers.UUIDField(required=False)


class CompleteProfileInputSerializer(serializers.Serializer):
    username = serializers.CharField(
        validators=[username_regex],
        min_length=5,
        max_length=12,
        error_messages={
            'min_length': 'username must be at least 5 characters.',
            'max_length': 'username can`t be more than 12 characters.'
        }
    )
    email = serializers.EmailField(
        error_messages={'invalid': 'invalid email address.'}
    )
    first_name = serializers.CharField(max_length=50)
    last_name = serializers.CharField(max_length=50)

    address = AddressInputSerializer()

    def validate_username(self, value):
        user = self.context['request'].user
        value = CustomUser.normalize_username(value)
        if UserSelector.is_username_taken(username=value, exclude_user_id=user.pk):
            raise serializers.ValidationError("this user is already taken.")
        return value

    def validate_email(self, value):
        user = self.context['request'].user
        value = CustomUser.normalize_email(value)
        if UserSelector.is_email_taken(email=value, exclude_user_id=user.pk):
            raise serializers.ValidationError("this email is already taken.")
        return value

class UserOutputSerializer(serializers.ModelSerializer):
    addresses = AddressSerializer(many=True, read_only=True)

    class Meta:
        model = CustomUser
        fields = [
            'id', 'phone_number', 'username', 'email',
            'first_name', 'last_name', 'is_profile_complete', 'addresses'
        ]


class LogoutInputSerializer(serializers.Serializer):
    refresh = serializers.CharField(
        error_messages={'required': 'refresh token is required.'}
    )


class UserProfileUpdateInputSerializer(serializers.Serializer):
    username = serializers.CharField(
        validators=[username_regex],
        min_length=5,
        max_length=12,
        required=False,
        error_messages={
            'min_length': 'username must be at least 5 characters.',
            'max_length': 'username can`t be more than 12 characters.'
        }
    )
    first_name = serializers.CharField(max_length=50, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=50, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, error_messages={'invalid': 'invalid email address.'})
    address = AddressUpdateInputSerializer(required=False)

    password = serializers.CharField(
        write_only=True,
        required=False,
        trim_whitespace=False,
        max_length=PASSWORD_MAX_LENGTH,
    )

    def validate_username(self, value):
        user = self.context['request'].user
        value = CustomUser.normalize_username(value)
        if UserSelector.is_username_taken(username=value, exclude_user_id=user.pk):
            raise serializers.ValidationError("this username is already taken.")
        return value

    def validate_email(self, value):
        user = self.context['request'].user
        value = CustomUser.normalize_email(value)
        if UserSelector.is_email_taken(email=value, exclude_user_id=user.pk):
            raise serializers.ValidationError("this email is already taken.")
        return value

    def validate(self, attrs):
        password = attrs.get("password")
        if password is None:
            return attrs
        user = self.context["request"].user
        candidate = CustomUser(
            pk=user.pk,
            phone_number=user.phone_number,
            username=attrs.get("username", user.username),
            email=user.email,
            first_name=attrs.get("first_name", user.first_name),
            last_name=attrs.get("last_name", user.last_name),
        )
        validate_password_policy(password, candidate)
        return attrs


class PasswordResetVerifyInputSerializer(NormalizedPhoneNumberSerializer):
    otp = serializers.CharField(
        max_length=6,
        min_length=6,
        validators=[RegexValidator(r"^[0-9]{6}$", "OTP must contain six ASCII digits.")],
        error_messages={'required': 'otp is required.'}
    )
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        max_length=PASSWORD_MAX_LENGTH,
        error_messages={'required': 'enter new password.'}
    )

    def validate(self, attrs):
        user = UserSelector.get_user_by_phone(attrs["phone_number"])
        validate_password_policy(attrs["password"], user)
        return attrs


class UserSignupInputSerializer(serializers.Serializer):
    """Validated input for direct username/password registration only."""

    username = serializers.CharField(
        min_length=5,
        max_length=150,
        validators=[username_regex],
    )
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        max_length=PASSWORD_MAX_LENGTH,
        style={"input_type": "password"},
    )

    default_error_message = "Unable to create an account with the provided information."

    def validate_username(self, value):
        return CustomUser.normalize_username(value)

    def validate(self, attrs):
        if UserSelector.signup_username_exists(username=attrs["username"]):
            raise serializers.ValidationError({
                "non_field_errors": [self.default_error_message],
            })

        candidate_user = CustomUser(username=attrs["username"])
        validate_password_policy(attrs["password"], candidate_user)
        return attrs


class UserSignupOutputSerializer(serializers.ModelSerializer):
    """Deliberately minimal signup response with no password or PII fields."""

    class Meta:
        model = CustomUser
        fields = ("username",)
        read_only_fields = fields
