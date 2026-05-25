#aright_route_backend/apps/users/serializers.py
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()

class EmailCheckSerializer(serializers.Serializer):
    email = serializers.EmailField()

class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ('email', 'password', 'first_name', 'last_name',
                  'is_touch_id_enabled', 'terms_agreed')
        extra_kwargs = {
            'first_name': {'required': False},
            'last_name': {'required': False},
            'is_touch_id_enabled': {'required': False},
            'terms_agreed': {'required': False},
        }

    def create(self, validated_data):
        password = validated_data.pop('password')
        # create_user ensures password hashing & any custom logic
        user = User.objects.create_user(password=password, **validated_data)
        return user

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)

class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp_code = serializers.CharField(max_length=6)


class ChangePasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, min_length=6)

    def validate_new_password(self, value):
        validate_password(value)
        return value

class ChangeEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()

class UserDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        # expose non-sensitive user fields only
        fields = (
            "id",
            "email",
            "plain_password",
            "is_active",
            "is_staff",
            "date_joined",
            "last_login",
            # add any custom non-sensitive fields your User model has:
            "is_touch_id_enabled",
            "terms_agreed",
        )
        read_only_fields = fields