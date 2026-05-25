from rest_framework import serializers
from .models import Subscription, Plan, TeamMember


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ('id', 'name', 'price', 'currency', 'interval', 'trial_days', 'product_id')


class SubscriptionStatusSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(allow_null=True)
    team_id = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = (
            'id',
            'status',
            'platform',
            'trial_start_date',
            'trial_end_date',
            'renewal_date',
            'plan',
            'team_id',
        )

    def get_team_id(self, obj):
        if hasattr(obj, 'team') and obj.team:
            return obj.team.id
        return None


class IAPValidateSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=('ios', 'android'))
    product_id = serializers.CharField()
    token = serializers.CharField(required=False, allow_blank=True, allow_null=True)


# simple alias if PlansSerializer was referenced
class PlansSerializer(PlanSerializer):
    pass


class TeamInviteAcceptSerializer(serializers.Serializer):
    token = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False)
    password = serializers.CharField(required=False, write_only=True)
    name = serializers.CharField(required=False)

    def validate(self, data):
        if not data.get('token') and not (data.get('email') and data.get('password') and data.get('name')):
            raise serializers.ValidationError("Provide either 'token' or 'email'+'password'+'name'.")
        return data


class TeamMemberSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    team_id = serializers.IntegerField(source='team.id', read_only=True)
    invited_by_id = serializers.IntegerField(source='invited_by.id', read_only=True)

    class Meta:
        model = TeamMember
        fields = (
            "id",
            "invited_email",
            "status",
            "user_id",
            "team_id",
            "invited_by_id",
            "accepted_at",
        )
