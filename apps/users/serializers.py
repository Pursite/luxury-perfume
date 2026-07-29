import re
from rest_framework import serializers
from django.core.validators import RegexValidator
from .models import CustomUser, Address
from .selectors import UserSelector

phone_regex = RegexValidator(
    regex=r'^09\d{9}$',
    message="Phone number must be entered in the format: '0912345678'."
)

username_regex = RegexValidator(
    regex=r'^[a-zA-Z0-9_]+$',
    message="Username must be entered in the format: '[a-zA-Z0-9_]+'."
)


def validate_password_complexity(value):
    if not re.search(r'[A-Za-z]', value):
        raise serializers.ValidationError("Password must contain at least one english letter.,")

    if not re.search(r'\d', value):
        raise serializers.ValidationError("Password must contain at least one digit.")

    if not re.search(r'[!@#$%^&*()]', value):
        raise serializers.ValidationError("password must contain at one of these characters -!@#$%^&*()-.")

    return value


class PhoneInputSerializer(serializers.Serializer):
    phone_number = serializers.CharField(
        validators=[phone_regex],
        max_length=11
    )


class VerifyOTPInputSerializer(serializers.Serializer):
    phone_number = serializers.CharField(
        validators=[phone_regex],
        max_length=11
    )
    otp = serializers.CharField(
        max_length=6,
        min_length=6,
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
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password_complexity],
        min_length=6,
        max_length=18,
        error_messages={
            'min_length': 'password must be at least 6 characters.',
            'max_length': 'password can`t be more than 18 characters.'
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
        if UserSelector.is_username_taken(username=value, exclude_user_id=user.pk):
            raise serializers.ValidationError("this user is already taken.")
        return value

    def validate_email(self, value):
        user = self.context['request'].user
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

    password = serializers.CharField(
        write_only=True,
        required=False,
        validators=[validate_password_complexity],
        min_length=6,
        max_length=18,
        error_messages={
            'min_length': 'password must be at least 6 characters.',
            'max_length': 'password cant`t be more than 18 characters.'
        }
    )

    def validate_username(self, value):
        user = self.context['request'].user
        if UserSelector.is_username_taken(username=value, exclude_user_id=user.pk):
            raise serializers.ValidationError("this username is already taken.")
        return value


class PasswordResetVerifyInputSerializer(serializers.Serializer):
    phone_number = serializers.CharField(
        validators=[phone_regex],
        max_length=11,
        error_messages={'required': 'phone number is required.'}
    )
    otp = serializers.CharField(
        max_length=6,
        min_length=6,
        error_messages={'required': 'otp is required.'}
    )
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password_complexity],
        min_length=6,
        max_length=18,
        error_messages={'required': 'enter new password.'}
    )
