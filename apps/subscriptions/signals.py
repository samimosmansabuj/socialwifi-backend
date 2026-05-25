from datetime import timedelta
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import FieldDoesNotExist

User = get_user_model()
TeamMember = apps.get_model('subscriptions', 'TeamMember')
Subscription = apps.get_model('subscriptions', 'Subscription')
Team = apps.get_model('subscriptions', 'Team')
Plan = apps.get_model('subscriptions', 'Plan')


def _team_active_subscription(team):
    if not team:
        return None
    return Subscription.objects.filter(team=team, status__in=['active', 'trial']).order_by('-renewal_date').first()


def _team_has_capacity(team):
    # return True if team has seats for one more member
    if not team:
        return False
    max_seats = getattr(team, 'max_seats', None)
    active = getattr(team, 'active_members', None)
    if max_seats is None:
        return True
    if active is None:
        return True
    return active < max_seats


def _has_concrete_field(model_instance, field_name):
    try:
        f = model_instance._meta.get_field(field_name)
        return not getattr(f, "many_to_many", False) and getattr(f, "concrete", True)
    except FieldDoesNotExist:
        return False


def _update_team_counters_safe(team, delta=1):
    """
    Safely update team's active_members and seats_available if concrete fields exist.
    Otherwise recompute seats_available from TeamMember where possible.
    """
    TeamMember = apps.get_model('subscriptions', 'TeamMember')

    # If model has active_members field (concrete), update it
    if _has_concrete_field(team, "active_members"):
        team.active_members = max(0, (getattr(team, "active_members", 0) or 0) + delta)
        update_fields = ["active_members"]
        if _has_concrete_field(team, "max_seats") and _has_concrete_field(team, "seats_available"):
            team.seats_available = max(0, getattr(team, "max_seats", 0) - team.active_members)
            update_fields.append("seats_available")
        try:
            team.save(update_fields=update_fields)
        except Exception:
            # fallback to full save
            team.save()
        return

    # If seats_available is a concrete field but active_members is not, recompute active_count and set seats_available
    if _has_concrete_field(team, "max_seats") and _has_concrete_field(team, "seats_available"):
        active_count = TeamMember.objects.filter(team=team, user__isnull=False, status__in=["accepted", "active"]).count()
        team.seats_available = max(0, getattr(team, "max_seats", 0) - active_count)
        try:
            team.save(update_fields=["seats_available"])
        except Exception:
            team.save()
        return

    # Nothing to update on model -> no-op
    return


@receiver(post_save, sender=User)
def attach_invites_and_grant_team_subscription(sender, instance, created, **kwargs):
    if not created:
        return

    email = getattr(instance, "email", None)
    if not email:
        return

    now = timezone.now()

    # invites = TeamMember.objects.filter(
    #     invited_email__iexact=email,
    #     user__isnull=True,
    #     status__in=["invited", "active"]
    # ).select_related("team")

    # AFTER: include pending/accepted and be case‑insensitive
    invites = TeamMember.objects.filter(
        invited_email__iexact=email,
        user__isnull=True,
        status__in=["invited", "pending", "accepted", "active"]
    ).select_related("team")

    if not invites.exists():
        return

    for tm in invites:
        team = tm.team

        # capacity check (if you track seats)
        # if team and hasattr(team, "max_seats") and getattr(team, "active_members", 0) >= team.max_seats:
        # AFTER:
        if team and getattr(team, "max_seats", None) is not None:
            active = getattr(team, "active_members", None)
            if active is not None and active >= team.max_seats:
                tm.status = "pending"
                tm.save(update_fields=["status"])
                continue

        tm.user = instance
        tm.status = "active"
        tm.accepted_at = now
        tm.save(update_fields=["user", "status", "accepted_at"])

        # create or get a plain Subscription for the user (do NOT pass reverse 'team' here)
        sub, created_sub = Subscription.objects.get_or_create(user=instance)

        with transaction.atomic():
            # find authoritative team subscription (if any)
            team_sub = Subscription.objects.filter(team=team, status__in=['active','trial']).order_by('-renewal_date').first() if team else None

            if team_sub and team_sub.renewal_date and team_sub.renewal_date > now:
                # assign plan and dates based on the team's authoritative subscription
                sub.plan = getattr(team_sub, "plan", None)
                sub.team = team
                sub.status = 'active'
                sub.trial_start_date = now
                sub.trial_end_date = team_sub.renewal_date
                sub.renewal_date = team_sub.renewal_date
            else:
                # fallback: individual/free behavior (use plan trial_days)
                plan = getattr(team, "plan", None) if team else None
                trial_days = getattr(plan, "trial_days", 7) if plan else 7
                if plan and getattr(plan, "plan_type", None) == "team" and trial_days == 0:
                    # team plan with no trial -> activate for billing period (30 days here)
                    sub.plan = plan
                    sub.team = team                       # <-- ensure team FK set here
                    sub.status = 'active'
                    sub.trial_start_date = now
                    sub.trial_end_date = None
                    sub.renewal_date = now + timedelta(days=30)
                else:
                    sub.plan = plan
                    sub.team = team
                    sub.status = 'trial'
                    sub.trial_start_date = now
                    sub.trial_end_date = now + timedelta(days=trial_days)
                    sub.renewal_date = sub.trial_end_date

            # clear receipt token if any
            try:
                sub.latest_receipt_token = None
            except Exception:
                pass

            sub.save()

        # update team counters if needed
        if team:
            try:
                _update_team_counters_safe(team, delta=1)
            except Exception:
                pass


@receiver(post_save, sender=TeamMember)
def grant_team_subscription_on_accept(sender, instance, created, **kwargs):
    # only act when member is accepted and has an associated user
    if instance.status not in ('accepted', 'active') or not getattr(instance, 'user', None):
        return

    user = instance.user
    team = instance.team
    now = timezone.now()

    # enforce capacity
    if team and not _team_has_capacity(team):
        instance.status = "pending"
        instance.save(update_fields=["status"])
        return

    with transaction.atomic():
        # authoritative team subscription (if any)
        team_sub = _team_active_subscription(team)

        if team_sub and team_sub.renewal_date and team_sub.renewal_date > now:
            # use the team's authoritative subscription
            assigned_plan = getattr(team_sub, "plan", None)
            trial_end = team_sub.renewal_date
            status_to_set = 'active'  # team members get active access
        else:
            # no active team subscription — fallback to team's configured plan
            assigned_plan = getattr(team, "plan", None)
            trial_days = getattr(assigned_plan, "trial_days", 7) if assigned_plan else 7
            if assigned_plan and getattr(assigned_plan, "plan_type", None) == "team" and trial_days == 0:
                # team plan with no trial => activate and set a billing window (30d)
                trial_end = now + timedelta(days=30)
                status_to_set = 'active'
            else:
                trial_end = now + timedelta(days=trial_days)
                status_to_set = 'trial'

        # update or create subscription for this user
        sub, created_sub = Subscription.objects.get_or_create(user=user)
        sub.team = team                            # <-- ensure team FK set
        sub.plan = assigned_plan
        sub.status = status_to_set
        sub.trial_start_date = now
        sub.trial_end_date = trial_end
        sub.renewal_date = trial_end
        try:
            sub.latest_receipt_token = None
        except Exception:
            pass
        sub.save()

        # update team counters
        if team:
            _update_team_counters_safe(team, delta=1)


@receiver(post_save, sender=Subscription)
def propagate_team_subscription_to_members(sender, instance, created, **kwargs):
    """
    Use the team's authoritative subscription (latest active/trial) to propagate
    renewal_date/plan to members. Ignore saves of unrelated/non-authoritative subs.
    """
    team = getattr(instance, "team", None)
    if not team:
        return

    # find the authoritative team subscription (latest active/trial)
    team_sub = _team_active_subscription(team)
    if not team_sub or not getattr(team_sub, "renewal_date", None):
        return

    renewal = team_sub.renewal_date
    plan = getattr(team_sub, "plan", None)

    # update all member subscriptions for this team (exclude the team_sub itself)
    with transaction.atomic():
        qs = Subscription.objects.filter(team=team).exclude(pk=team_sub.pk)
        update_data = {
            "trial_end_date": renewal,
            "renewal_date": renewal,
        }
        if plan is not None:
            update_data["plan"] = plan
        qs.update(**update_data)