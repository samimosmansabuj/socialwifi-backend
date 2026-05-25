from django.urls import path
from django.views.generic.base import RedirectView
from . import views

urlpatterns = [
    # canonical endpoint (keep this as the real handler)
    path('iap/validate/', views.IAPValidateView.as_view(), name='iap-validate'),

    # legacy alias → redirect to canonical (keeps old clients working)
    path('validate-iap/', RedirectView.as_view(pattern_name='iap-validate', permanent=False)),

    path('status/', views.SubscriptionStatusView.as_view(), name='subscription-status'),
    path('check/', views.SubscriptionCheckView.as_view(), name='subscription-check'),
    path('plans/', views.PlansView.as_view(), name='plans-list'),

    # team members endpoints
    path('team/members/', views.TeamMembersView.as_view(), name='team-members'),
    path('team/invite/accept/', views.TeamInviteAcceptView.as_view(), name='team-invite-accept'),
    path('team/members/<int:member_id>/remove/', views.TeamMemberRemoveView.as_view(), name='team-member-remove'),
]