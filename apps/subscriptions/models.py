from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core import signing
from django.core.mail import send_mail
from datetime import timedelta

User = settings.AUTH_USER_MODEL


class Plan(models.Model):
    PLAN_TYPES = [
        ('basic', 'Basic'),
        ('premium', 'Premium'),
        ('team', 'Team'),
    ]
    
    INTERVAL_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]
    
    name = models.CharField(max_length=100)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES, default='monthly')
    product_id = models.CharField(max_length=255, unique=True)
    max_drivers = models.IntegerField(default=1, help_text="Maximum number of drivers for team plans")
    trial_days = models.IntegerField(default=7, help_text="Trial period in days")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['plan_type', 'price']
        verbose_name = 'Plan'
        verbose_name_plural = 'Plans'
    
    def __str__(self):
        return f"{self.name} - ${self.price}/{self.interval}"


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('trial', 'Trial'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    PLATFORM_CHOICES = [
        ('google', 'Google Play'),
        ('apple', 'Apple App Store'),
    ]
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trial')
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, blank=True, null=True)
    
    trial_start_date = models.DateTimeField(blank=True, null=True)
    trial_end_date = models.DateTimeField(blank=True, null=True)
    renewal_date = models.DateTimeField(blank=True, null=True)
    
    latest_receipt_token = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Subscription'
        verbose_name_plural = 'Subscriptions'
    
    def __str__(self):
        return f"{self.user.email} - {self.plan.name if self.plan else 'No Plan'}"
    
    def is_trial_active(self):
        """Check if trial period is still active"""
        if self.trial_end_date is None:
            return False
        return timezone.now() < self.trial_end_date
    
    def is_subscription_active(self):
        """Check if subscription is active (not expired)"""
        if self.renewal_date is None:
            return self.status == 'active'
        return self.status == 'active' and timezone.now() < self.renewal_date

    def activate_trial(self, plan=None):
        """
        Activate a trial for this subscription.
        If plan not provided, try to pick a 'basic' monthly Plan.
        """
        if plan is None:
            try:
                plan = Plan.objects.filter(plan_type='basic', interval='monthly', is_active=True).first()
            except Exception:
                plan = None

        now = timezone.now()
        self.plan = plan
        self.status = 'trial'
        self.trial_start_date = now
        self.trial_end_date = now + timedelta(days=(plan.trial_days if plan else 7))
        # Do NOT add an extra 30 days — keep renewal at the trial end
        self.renewal_date = self.trial_end_date
        self.save(update_fields=['plan', 'status', 'trial_start_date', 'trial_end_date', 'renewal_date'])
        return self

    def is_active_and_valid(self):
        """Helper used in views to check if subscription is active and not expired."""
        if self.status == 'active':
            return self.is_subscription_active()
        if self.status == 'trial':
            return self.is_trial_active()
        return False


class Team(models.Model):
    subscription = models.OneToOneField('Subscription', on_delete=models.CASCADE, related_name='team')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def max_seats(self):
        plan = getattr(self.subscription, 'plan', None)
        return getattr(plan, 'max_drivers', 1) if plan else 1

    def current_active_members_count(self):
        return self.members.filter(status='active').count()

    def seats_available(self):
        return max(0, self.max_seats - self.current_active_members_count())

    def invite_member(self, email, invited_by=None, use_token=True):
        """Create or return existing invitation. If use_token is False we create a pending invite without token/email send."""
        token = None
        if use_token:
            token = signing.dumps({'email': email, 'team_id': self.id, 'ts': timezone.now().timestamp()})

        # if an invite for this email+team already exists, return/update it instead of creating duplicate
        tm = TeamMember.objects.filter(team=self, invited_email__iexact=email).first()
        new_token_created = False
        if tm:
            updated = False
            if use_token and token and not tm.invite_token:
                tm.invite_token = token
                new_token_created = True
                updated = True
            if invited_by and tm.invited_by_id != getattr(invited_by, 'id', None):
                tm.invited_by = invited_by
                updated = True
            if updated:
                try:
                    tm.save()
                except Exception:
                    pass
        else:
            tm = TeamMember.objects.create(
                team=self,
                invited_email=email,
                invited_by=invited_by,
                invite_token=token,
                status='invited'
            )
            new_token_created = bool(use_token and token)

        # send email only when we have a frontend URL and a newly created token
        frontend_url = getattr(settings, 'FRONTEND_URL', None)
        if new_token_created and frontend_url:
            accept_url = f"{frontend_url.rstrip('/')}/team/invite/accept/?token={tm.invite_token}"
            try:
                send_mail(
                    subject="You're invited to join a RightRoute team",
                    message=f"You were invited to join a team. Click to accept: {accept_url}",
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                    recipient_list=[email],
                    fail_silently=True
                )
            except Exception:
                pass

        return tm

class TeamMember(models.Model):
    STATUS_CHOICES = (
        ('invited','invited'),
        ('active','active'),
        ('removed','removed'),
    )
    team = models.ForeignKey(Team, related_name='members', on_delete=models.CASCADE)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    invited_email = models.EmailField()
    invited_by = models.ForeignKey(User, null=True, blank=True, related_name='invites_sent', on_delete=models.SET_NULL)
    invite_token = models.CharField(max_length=512, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='invited')
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('team', 'invited_email')