from rest_framework import views, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from .serializers import TeamMemberSerializer

# serializers used by the views (add any other serializers your views reference)
from .serializers import (
    SubscriptionStatusSerializer,
    IAPValidateSerializer,
    PlansSerializer,
)

# models used by the views
from .models import Subscription, Plan, Team, TeamMember
from django.db import transaction

User = get_user_model()


class SubscriptionStatusView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            subscription = Subscription.objects.get(user=request.user)
        except Subscription.MultipleObjectsReturned:
            subscription = Subscription.objects.filter(user=request.user).order_by('-id').first()
        except Subscription.DoesNotExist:
            return Response({"status": "no_subscription", "message": "No active subscription found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = SubscriptionStatusSerializer(subscription)
        data = serializer.data
        data['subscription_user_id'] = getattr(subscription, 'user_id', None)

        team = getattr(subscription, 'team', None)
        if team:
            # all team members (invited + accepted/active/removed)
            members_qs = TeamMember.objects.filter(team=team)
            total_members = members_qs.count()
            invited_count = members_qs.filter(status__iexact='invited').count()
            active_count = members_qs.filter(user__isnull=False, status__in=['accepted', 'active']).count()

            # small member listing (id, invited_email, status, user_id)
            members_list = list(members_qs.values("id", "invited_email", "status", "user_id"))

            max_seats = getattr(team, 'max_seats', None)
            seats_available = (max_seats - active_count) if max_seats is not None else None

            data['team'] = {
                "id": team.id,
                "max_seats": max_seats,
                "active_members": active_count,
                "invited_members": invited_count,
                "total_members": total_members,
                "seats_available": seats_available,
                "members": members_list,
            }
        else:
            data['team'] = None

        return Response(data, status=status.HTTP_200_OK)


class SubscriptionCheckView(views.APIView):
    """
    API to check if user has active subscription.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscription = Subscription.objects.filter(user=request.user).first()
        
        if not subscription:
            return Response({
                "has_subscription": False,
                "message": "No subscription found."
            }, status=status.HTTP_200_OK)
        
        is_active = subscription.status == 'active'
        is_trial_active = subscription.is_trial_active()
        
        return Response({
            "has_subscription": True,
            "is_active": is_active,
            "is_trial_active": is_trial_active,
            "status": subscription.status,
            "plan": subscription.plan.name if subscription.plan else None,
            "renewal_date": subscription.renewal_date.isoformat() if subscription.renewal_date else None,
        }, status=status.HTTP_200_OK)


class IAPValidateView(views.APIView):
    """
    API to validate Google Play or Apple App Store purchase.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = IAPValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        platform = serializer.validated_data['platform']
        product_id = serializer.validated_data['product_id']
        token = serializer.validated_data.get('token')

        # Search by product_id (works for both platforms)
        plan = Plan.objects.filter(product_id=product_id, is_active=True).first()

        if not plan:
            return Response(
                {"error": f"Invalid product_id '{product_id}' or plan not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get or create subscription
        subscription, created = Subscription.objects.get_or_create(user=request.user)

        now = timezone.now()

        # determine billing period in days
        if plan.interval == 'monthly':
            billing_days = 30
        elif plan.interval == 'yearly':
            billing_days = 365
        else:
            billing_days = 30

        # determine trial days correctly (don't use `or` for numeric 0)
        trial_days = plan.trial_days if plan.trial_days is not None else 7

        # If this is a team plan (or trial_days == 0) => no free trial, activate immediately
        is_team_plan = getattr(plan, "plan_type", None) == "team" or trial_days == 0

        subscription.plan = plan
        subscription.platform = platform
        subscription.latest_receipt_token = token

        if is_team_plan:
            # team plans: active immediately, no free trial
            subscription.status = 'active'
            subscription.trial_start_date = now
            subscription.trial_end_date = None
            subscription.renewal_date = now + timedelta(days=billing_days)
        else:
            # individual/free plans: grant trial then set next renewal after billing period
            subscription.status = 'trial'
            subscription.trial_start_date = now
            subscription.trial_end_date = now + timedelta(days=trial_days)
            subscription.renewal_date = subscription.trial_end_date + timedelta(days=billing_days)

        subscription.save()

        # create team record only for team plans (so team shows up)
        if is_team_plan:
            Team.objects.get_or_create(subscription=subscription)

        return Response({
            "success": True,
            "message": "Subscription activated with trial period." if not is_team_plan else "Subscription activated.",
            "subscription": {
                "status": subscription.status,
                "plan": subscription.plan.name,
                "platform": subscription.platform,
                "trial_start_date": subscription.trial_start_date.isoformat() if subscription.trial_start_date else None,
                "trial_end_date": subscription.trial_end_date.isoformat() if subscription.trial_end_date else None,
                "renewal_date": subscription.renewal_date.isoformat() if subscription.renewal_date else None,
            }
        }, status=status.HTTP_200_OK)


class PlansView(views.APIView):
    """
    API to list available subscription plans.
    """
    def get(self, request):
        plans = Plan.objects.filter(is_active=True).values(
            'id', 'name', 'price', 'currency', 'interval', 'trial_days', 'product_id'
        )
        return Response({"plans": list(plans)}, status=status.HTTP_200_OK)


class TeamMembersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # find the current user's team (via subscription)
        sub = Subscription.objects.filter(user=request.user).order_by('-id').first()
        team = getattr(sub, 'team', None)
        if not team:
            return Response({"members": []})
        members = TeamMember.objects.filter(team=team).values("id", "invited_email", "status", "user_id")
        return Response({"members": list(members)})

    def post(self, request, *args, **kwargs):
        """
        Accept either single invite (email/name) or bulk invites under "emails".
        - Single: {"email":"a@example.com", "name":"A"}
        - Bulk:   {"emails":"a@example.com:Alice, b@example.com:Bob"}
                 or {"emails":[{"email":"a","name":"A"}, ...]}
        """
        data = request.data

        # detect bulk payload
        if "emails" in data:
            raw = data.get("emails")
            emails = []

            # normalize different input types
            if isinstance(raw, str):
                parts = [p.strip() for p in raw.split(',') if p.strip()]
                for p in parts:
                    if ':' in p:
                        e, n = p.split(':', 1)
                        emails.append({"email": e.strip(), "name": n.strip()})
                    else:
                        emails.append({"email": p.strip()})
            elif isinstance(raw, (list, tuple)):
                for item in raw:
                    if isinstance(item, str):
                        emails.append({"email": item.strip()})
                    elif isinstance(item, dict):
                        e = item.get("email") or item.get("email_address") or item.get("mail")
                        if not e:
                            continue
                        name = item.get("name") or item.get("full_name") or item.get("display_name")
                        entry = {"email": str(e).strip()}
                        if name:
                            entry["name"] = str(name).strip()
                        emails.append(entry)
            else:
                return Response({"detail": "Provide 'emails' as list/objects or comma separated string."}, status=status.HTTP_400_BAD_REQUEST)

            if not emails:
                return Response({"detail": "No valid emails provided."}, status=status.HTTP_400_BAD_REQUEST)

            # ensure owner has subscription/team
            sub, _ = Subscription.objects.get_or_create(user=request.user)
            team = getattr(sub, "team", None)
            if not team:
                team = Team.objects.create(subscription=sub)

            created = []
            skipped = []
            now = timezone.now()

            with transaction.atomic():
                for item in emails:
                    email = item.get("email", "").lower()
                    name = item.get("name")
                    if not email:
                        continue

                    tm_exists = TeamMember.objects.filter(team=team, invited_email__iexact=email).first()
                    if tm_exists:
                        if name:
                            try:
                                setattr(tm_exists, "invited_name", name)
                                tm_exists.save(update_fields=["invited_name"])
                            except Exception:
                                try:
                                    setattr(tm_exists, "name", name)
                                    tm_exists.save(update_fields=["name"])
                                except Exception:
                                    pass
                        skipped.append({"email": email, "name": name})
                        continue

                    tm = TeamMember.objects.create(
                        team=team,
                        invited_email=email,
                        status="invited"
                    )
                    if name:
                        try:
                            setattr(tm, "invited_name", name)
                            tm.save(update_fields=["invited_name"])
                        except Exception:
                            try:
                                setattr(tm, "name", name)
                                tm.save(update_fields=["name"])
                            except Exception:
                                pass

                    # attach existing user immediately if present
                    try:
                        existing_user = User.objects.filter(email__iexact=email).first()
                        if existing_user:
                            tm.user = existing_user
                            tm.status = "active"
                            tm.accepted_at = timezone.now()
                            tm.save(update_fields=["user", "status", "accepted_at"])

                            sub_user, _ = Subscription.objects.get_or_create(user=existing_user)
                            team_plan = getattr(getattr(team, "subscription", None), "plan", None)
                            if team_plan:
                                sub_user.plan = team_plan
                            sub_user.status = "active"
                            try:
                                sub_user.team = team
                            except Exception:
                                pass
                            sub_user.trial_start_date = now
                            sub_user.trial_end_date = None
                            sub_user.renewal_date = now + timedelta(days=30)
                            sub_user.save()
                    except Exception:
                        pass

                    created.append({"email": email, "name": name})

            return Response({"created": created, "skipped_existing": skipped}, status=status.HTTP_201_CREATED)

        # fallback: single invite flow (existing behavior)
        email = data.get("email")
        name = data.get("name")
        no_token = bool(data.get("no_token", False))

        if not email:
            return Response({"error": "email required"}, status=400)

        sub, _ = Subscription.objects.get_or_create(user=request.user)
        team = getattr(sub, "team", None)
        if not team:
            team = Team.objects.create(subscription=sub)

        tm = team.invite_member(email=email, invited_by=request.user, use_token=not no_token)

        try:
            existing_user = User.objects.filter(email__iexact=email).first()
            if existing_user:
                now = timezone.now()
                sub_user, _ = Subscription.objects.get_or_create(user=existing_user)
                team_plan = getattr(getattr(team, "subscription", None), "plan", None)
                if team_plan:
                    sub_user.plan = team_plan
                sub_user.status = "active"
                try:
                    sub_user.team = team
                except Exception:
                    pass
                sub_user.trial_start_date = now
                sub_user.trial_end_date = None
                sub_user.renewal_date = now + timedelta(days=30)
                sub_user.save()
                tm.user = existing_user
                tm.status = "active"
                tm.save(update_fields=["user","status"])
        except Exception:
            pass

        serializer = TeamMemberSerializer(tm)
        return Response(serializer.data, status=201)


class TeamInviteAcceptView(APIView):
    """
    Accept invite via token OR via email+password+name (no token).
    If token provided -> validate and attach user.
    If email provided and user exists -> attach.
    If email provided and user not exists -> return need_register or create user if password+name provided.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get('token')
        email = request.data.get('email')
        password = request.data.get('password')
        name = request.data.get('name')

        # Resolve invite record
        tm = None
        if token:
            try:
                data = signing.loads(token, max_age=60*60*24*30)  # 30 days max
            except signing.BadSignature:
                return Response({"error":"Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)
            team_id = data.get('team_id')
            email = data.get('email')
            tm = get_object_or_404(TeamMember, team_id=team_id, invited_email__iexact=email)
        else:
            if not email:
                return Response({"error":"token or email required"}, status=status.HTTP_400_BAD_REQUEST)
            # try find pending invite, but if none and caller supplied team_id -> create member directly
            tm = TeamMember.objects.filter(invited_email__iexact=email, status__in=['invited', 'active']).first()
            if not tm:
                team_id = request.data.get('team_id')
                if not team_id:
                    return Response({"error":"invite not found"}, status=status.HTTP_404_NOT_FOUND)
                # create direct active member (no checks)
                team = get_object_or_404(Team, id=team_id)
                tm = TeamMember.objects.create(team=team, invited_email=email, status='active')

        # find or create user
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            if not password or not name:
                # frontend should register: signal or manual flow will handle subscription
                return Response({"need_register": True, "email": email}, status=status.HTTP_200_OK)
            user = User.objects.create_user(email=email, password=password)
            try:
                # set name if available on your user model
                user.first_name = name
                user.save(update_fields=['first_name'])
            except Exception:
                pass

        # enforce seat capacity
        if tm.team.seats_available() <= 0:
            return Response({"error":"No seats available"}, status=status.HTTP_400_BAD_REQUEST)

        tm.user = user
        tm.status = 'active'
        try:
            tm.accepted_at = timezone.now()
            tm.save(update_fields=['user', 'status', 'accepted_at'])
        except Exception:
            tm.save()

        # ensure the user has a subscription (grant 30 days if none)
        sub, created = Subscription.objects.get_or_create(user=user)
        if created or sub.status != 'active':
            now = timezone.now()
            plan = getattr(tm.team.subscription, 'plan', None)
            sub.plan = plan
            sub.status = 'active'
            # link user's subscription to the team they joined
            try:
                sub.team = tm.team
            except Exception:
                pass
            sub.trial_start_date = now
            sub.trial_end_date = None
            sub.renewal_date = now + timedelta(days=30)
            sub.save(update_fields=['plan','status','trial_start_date','trial_end_date','renewal_date'])

        return Response({"success": True, "team_id": tm.team.id, "member_id": tm.id}, status=status.HTTP_200_OK)


class TeamMemberRemoveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, member_id):
        """Remove member (soft remove). Only subscription owner can remove (you can add admin checks)."""
        subscription = Subscription.objects.filter(user=request.user).first()
        if not subscription or not hasattr(subscription, 'team'):
            return Response({"detail":"No team subscription."}, status=status.HTTP_404_NOT_FOUND)
        team = subscription.team
        tm = get_object_or_404(TeamMember, id=member_id, team=team)
        tm.status = 'removed'
        tm.user = None
        tm.save()
        return Response({"removed": member_id})


class BulkInviteMembersView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        POST /subscriptions/team/members/
        Accepts:
          - {"emails": ["a@example.com","b@example.com"]}
          - {"emails": [{"email":"a@example.com","name":"A"}, ...]}
          - {"emails": "a@example.com:Alice, b@example.com:Bob"}
        Uses current user's team (user must have a team subscription).
        """
        raw = request.data.get('emails') or request.data.get('email') or []
        emails = []

        # normalize different input types
        if isinstance(raw, str):
            parts = [p.strip() for p in raw.split(',') if p.strip()]
            for p in parts:
                if ':' in p:
                    e, n = p.split(':', 1)
                    emails.append({"email": e.strip(), "name": n.strip()})
                else:
                    emails.append({"email": p})
        elif isinstance(raw, (list, tuple)):
            for item in raw:
                if isinstance(item, str):
                    emails.append({"email": item.strip()})
                elif isinstance(item, dict):
                    e = item.get("email") or item.get("email_address") or item.get("mail")
                    if not e:
                        continue
                    name = item.get("name") or item.get("full_name") or item.get("display_name")
                    entry = {"email": str(e).strip()}
                    if name:
                        entry["name"] = str(name).strip()
                    emails.append(entry)
        else:
            return Response({"detail": "Provide 'emails' as list/objects or comma separated string."}, status=status.HTTP_400_BAD_REQUEST)

        if not emails:
            return Response({"detail": "No valid emails provided."}, status=status.HTTP_400_BAD_REQUEST)

        # determine team from current user's subscription
        try:
            subscription = Subscription.objects.get(user=request.user)
            team = getattr(subscription, "team", None)
        except Subscription.DoesNotExist:
            return Response({"detail": "You have no subscription/team."}, status=status.HTTP_403_FORBIDDEN)
        except Subscription.MultipleObjectsReturned:
            subscription = Subscription.objects.filter(user=request.user).order_by('-id').first()
            team = getattr(subscription, "team", None)

        if not team:
            return Response({"detail": "No team found for current user."}, status=status.HTTP_404_NOT_FOUND)

        created = []
        skipped = []
        now = timezone.now()

        with transaction.atomic():
            for item in emails:
                email = item.get("email", "").lower()
                name = item.get("name")
                if not email:
                    continue

                tm_exists = TeamMember.objects.filter(team=team, invited_email__iexact=email).first()
                if tm_exists:
                    if name:
                        try:
                            setattr(tm_exists, "invited_name", name)
                            tm_exists.save(update_fields=["invited_name"])
                        except Exception:
                            try:
                                setattr(tm_exists, "name", name)
                                tm_exists.save(update_fields=["name"])
                            except Exception:
                                pass
                    skipped.append({"email": email, "name": name})
                    continue

                tm = TeamMember.objects.create(
                    team=team,
                    invited_email=email,
                    status="invited"
                )
                if name:
                    try:
                        setattr(tm, "invited_name", name)
                        tm.save(update_fields=["invited_name"])
                    except Exception:
                        try:
                            setattr(tm, "name", name)
                            tm.save(update_fields=["name"])
                        except Exception:
                            pass

                # attach existing user immediately if present
                try:
                    existing_user = User.objects.filter(email__iexact=email).first()
                    if existing_user:
                        tm.user = existing_user
                        tm.status = "active"
                        tm.accepted_at = timezone.now()
                        tm.save(update_fields=["user", "status", "accepted_at"])

                        sub_user, _ = Subscription.objects.get_or_create(user=existing_user)
                        team_plan = getattr(getattr(team, "subscription", None), "plan", None)
                        if team_plan:
                            sub_user.plan = team_plan
                        sub_user.status = "active"
                        try:
                            sub_user.team = team
                        except Exception:
                            pass
                        sub_user.trial_start_date = now
                        sub_user.trial_end_date = None
                        sub_user.renewal_date = now + timedelta(days=30)
                        sub_user.save()
                except Exception:
                    pass

                created.append({"email": email, "name": name})

        return Response({"created": created, "skipped_existing": skipped}, status=status.HTTP_201_CREATED)