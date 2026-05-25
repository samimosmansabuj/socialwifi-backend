from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    """Admin panel for Plan model"""
    
    list_display = ('name', 'plan_type', 'price_display', 'interval', 'product_id', 'trial_days', 'is_active_display')
    list_filter = ('plan_type', 'interval', 'is_active')
    search_fields = ('name', 'product_id')
    ordering = ('plan_type', 'price')
    
    fieldsets = (
        ('Plan Information', {
            'fields': ('name', 'plan_type')
        }),
        ('Product ID', {
            'fields': ('product_id',)
        }),
        ('Pricing', {
            'fields': ('price', 'currency', 'interval')
        }),
        ('Team Plan Settings', {
            'fields': ('max_drivers',),
        }),
        ('Trial Settings', {
            'fields': ('trial_days',),
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at',)
    
    # ✅ Custom display methods
    def price_display(self, obj):
        return format_html(
            '<strong style="color: green;">${}</strong>',
            obj.price
        )
    price_display.short_description = 'Price'
    price_display.admin_order_field = 'price'
    
    def is_active_display(self, obj):
        if obj.is_active:
            return mark_safe('<span style="color: green;">✅ Active</span>')
        return mark_safe('<span style="color: red;">❌ Inactive</span>')
    is_active_display.short_description = 'Status'
    is_active_display.admin_order_field = 'is_active'
    
    actions = ['activate_plans', 'deactivate_plans']
    
    def activate_plans(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'✅ {updated} plan(s) activated.')
    activate_plans.short_description = 'Activate Plans'
    
    def deactivate_plans(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'❌ {updated} plan(s) deactivated.')
    deactivate_plans.short_description = 'Deactivate Plans'


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Admin panel for Subscription model"""
    
    list_display = ('user_email', 'plan_name', 'status_display', 'platform_display', 'trial_status_display')
    list_filter = ('status', 'platform', 'created_at')
    search_fields = ('user__email', 'plan__name')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('User & Plan', {
            'fields': ('user', 'plan')
        }),
        ('Subscription Status', {
            'fields': ('status', 'platform')
        }),
        ('Trial Information', {
            'fields': ('trial_start_date', 'trial_end_date')
        }),
        ('Renewal Information', {
            'fields': ('renewal_date', 'latest_receipt_token')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    # ✅ Custom display methods - All fixed!
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'
    user_email.admin_order_field = 'user__email'
    
    def plan_name(self, obj):
        if obj.plan:
            return format_html('<strong>{}</strong>', obj.plan.name)
        return mark_safe('<span style="color: red;">❌ No Plan</span>')
    plan_name.short_description = 'Plan Name'
    plan_name.admin_order_field = 'plan__name'
    
    def status_display(self, obj):
        colors = {
            'trial': '#0066cc',
            'active': 'green',
            'expired': 'red',
            'cancelled': 'gray',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    status_display.admin_order_field = 'status'
    
    def platform_display(self, obj):
        if not obj.platform:
            return '-'
        icons = {
            'google': '🤖',
            'apple': '🍎',
        }
        icon = icons.get(obj.platform, '')
        return format_html('{} {}', icon, obj.get_platform_display())
    platform_display.short_description = 'Platform'
    platform_display.admin_order_field = 'platform'
    
    def trial_status_display(self, obj):
        if obj.is_trial_active():
            from django.utils import timezone
            days_left = (obj.trial_end_date - timezone.now()).days
            return format_html(
                '<span style="color: #0066cc;">🎉 Active ({} days)</span>',
                max(0, days_left)
            )
        if obj.status == 'trial':
            return mark_safe('<span style="color: orange;">⏱️ Expired</span>')
        return mark_safe('<span style="color: gray;">-</span>')
    trial_status_display.short_description = 'Trial'
    
    actions = ['mark_as_active', 'mark_as_expired', 'mark_as_trial']
    
    def mark_as_active(self, request, queryset):
        updated = queryset.update(status='active')
        self.message_user(request, f'✅ {updated} subscription(s) marked as active.')
    mark_as_active.short_description = 'Mark as Active'
    
    def mark_as_expired(self, request, queryset):
        updated = queryset.update(status='expired')
        self.message_user(request, f'❌ {updated} subscription(s) marked as expired.')
    mark_as_expired.short_description = 'Mark as Expired'
    
    def mark_as_trial(self, request, queryset):
        updated = queryset.update(status='trial')
        self.message_user(request, f'🔄 {updated} subscription(s) marked as trial.')
    mark_as_trial.short_description = 'Mark as Trial'