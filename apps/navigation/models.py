from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class Route(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='routes')
    name = models.CharField(max_length=255, help_text="রুটের নাম (যেমন: 'Dallas to Houston')")
    description = models.TextField(blank=True, null=True, help_text="রুটের বিবরণ")
    
    # লোকেশন ডেটা
    start_latitude = models.FloatField(help_text="শুরুর অবস্থান - Latitude")
    start_longitude = models.FloatField(help_text="শুরুর অবস্থান - Longitude")
    start_location_name = models.CharField(max_length=255, blank=True, help_text="শুরুর লোকেশনের নাম")
    
    end_latitude = models.FloatField(help_text="শেষের অবস্থান - Latitude")
    end_longitude = models.FloatField(help_text="শেষের অবস্থান - Longitude")
    end_location_name = models.CharField(max_length=255, blank=True, help_text="শেষের লোকেশনের নাম")
    
    # মেটা ডেটা
    total_distance = models.FloatField(default=0, help_text="মোট দূরত্ব (km)")
    waypoint_count = models.IntegerField(default=0, help_text="মোট ওয়েপয়েন্ট সংখ্যা")
    
    # ফাইল রেফারেন্স
    source_file = models.FileField(
        upload_to='route_imports/%Y/%m/%d/', 
        blank=True, 
        null=True,
        help_text="ইমপোর্টেড ফাইল (PDF/Image)"
    )
    
    # স্ট্যাটাস
    is_completed = models.BooleanField(default=False, help_text="রুট সম্পূর্ণ হয়েছে কি না")
    is_favorite = models.BooleanField(default=False, help_text="প্রিয় রুট চিহ্নিত")
    
    # টাইমস্ট্যাম্প
    created_at = models.DateTimeField(auto_now_add=True, help_text="তৈরির সময়")
    updated_at = models.DateTimeField(auto_now=True, help_text="সর্বশেষ আপডেটের সময়")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Routes"
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.user.email}"


class Waypoint(models.Model):
    """ওয়েপয়েন্ট মডেল - রুটের প্রতিটি পয়েন্ট"""
    
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name='waypoints')
    
    # লোকেশন ডেটা
    name = models.CharField(max_length=255, help_text="ওয়েপয়েন্টের নাম (যেমন: 'Exit 340')")
    latitude = models.FloatField(help_text="Latitude")
    longitude = models.FloatField(help_text="Longitude")
    
    # ক্রম এবং মেটা ডেটা
    order = models.IntegerField(help_text="ক্রম সংখ্যা (1, 2, 3...)")
    description = models.TextField(blank=True, null=True, help_text="ওয়েপয়েন্টের বিবরণ")
    
    # দূরত্ব এবং সময়
    distance_from_previous = models.FloatField(
        default=0, 
        help_text="আগের ওয়েপয়েন্ট থেকে দূরত্ব (km)"
    )
    estimated_time_minutes = models.IntegerField(
        default=0, 
        help_text="আগের পয়েন্ট থেকে অনুমানিক সময় (মিনিট)"
    )
    
    # সম্পদ
    icon = models.CharField(
        max_length=50, 
        default="📍", 
        help_text="আইকন ইমোজি বা রঙ"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['route', 'order']
        unique_together = [['route', 'order']]
        indexes = [
            models.Index(fields=['route', 'order']),
        ]
    
    def __str__(self):
        return f"{self.route.name} - {self.order}. {self.name}"


class RouteHistory(models.Model):
    """রুট ট্র্যাভার্স হিস্ট্রি - ব্যবহারকারী যখন রুট অনুসরণ করে"""
    
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name='histories')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='route_histories')
    
    started_at = models.DateTimeField(auto_now_add=True, help_text="যাত্রা শুরুর সময়")
    completed_at = models.DateTimeField(null=True, blank=True, help_text="যাত্রা শেষের সময়")
    
    total_time_spent = models.DurationField(null=True, blank=True, help_text="মোট সময় ব্যয়")
    total_distance_traveled = models.FloatField(default=0, help_text="প্রকৃত ভ্রমণ দূরত্ব (km)")
    
    status = models.CharField(
        max_length=20,
        choices=[
            ('in_progress', 'যাত্রা চলছে'),
            ('completed', 'সম্পূর্ণ'),
            ('paused', 'বিরাম'),
            ('cancelled', 'বাতিল'),
        ],
        default='in_progress',
        help_text="যাত্রার স্থিতি"
    )
    
    notes = models.TextField(blank=True, null=True, help_text="যাত্রার নোট")
    
    class Meta:
        ordering = ['-started_at']
        verbose_name_plural = "Route Histories"
        indexes = [
            models.Index(fields=['user', '-started_at']),
        ]
    
    def __str__(self):
        return f"{self.route.name} - {self.started_at.strftime('%Y-%m-%d')}"


class ROUTE_STATUS(models.TextChoices):
    DRAFT = "DRAFT"
    START = "START"
    STOP = "STOP"
    COMPLETE = "COMPLETE"
    CANCEL = "CANCEL"

class CreateRoute(models.Model):
    # user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='routes')
    name = models.CharField(max_length=255, help_text="Route Name (like as 'Dallas to Houston')")
    description = models.TextField(blank=True, null=True, help_text="Route Details")
    status = models.CharField(max_length=20, choices=ROUTE_STATUS.choices, default=ROUTE_STATUS.DRAFT)
    is_completed = models.BooleanField(default=False)
    is_favorite = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "CreateRoutes"
        # indexes = [
        #     models.Index(fields=['user', '-created_at']),
        # ]
    
    def __str__(self):
        # return f"{self.name} - {self.user.email}"
        return f"{self.name}"

class AddPermit(models.Model):
    route = models.ForeignKey(CreateRoute, on_delete=models.CASCADE, related_name="permits")
    order = models.PositiveIntegerField(blank=True, null=True)
    name = models.CharField(max_length=255, help_text="Permits Name (like as: 'Exit 340')", blank=True, null=True)
    
    start_location_name = models.CharField(max_length=255, blank=True, help_text="Start Location Name")
    start_latitude = models.FloatField(help_text="Start location - Latitude")
    start_longitude = models.FloatField(help_text="Start location - Longitude")
    
    end_location_name = models.CharField(max_length=255, blank=True, help_text="End Location Name")
    end_latitude = models.FloatField(help_text="End location - Latitude")
    end_longitude = models.FloatField(help_text="End location - Longitude")

    total_distance = models.FloatField(default=0, help_text="Total Distance (km)")
    permit_file = models.FileField(
        upload_to='route_imports/%Y/%m/%d/', 
        blank=True, 
        null=True,
        help_text="Imported File (PDF/Image)"
    )
    
    class Meta:
        ordering = ['route', 'order']
        unique_together = [['route', 'order']]
        indexes = [
            models.Index(fields=['route', 'order']),
        ]

class Waypoint(models.Model):
    permit = models.ForeignKey(AddPermit, on_delete=models.CASCADE, related_name='waypoints')
    order = models.PositiveIntegerField(blank=True, null=True)
    name = models.CharField(max_length=255, help_text="Waypoints Name (like as: 'Exit 340')")
    latitude = models.FloatField(help_text="Latitude")
    longitude = models.FloatField(help_text="Longitude")
    description = models.TextField(blank=True, null=True, help_text="Waypoint Details")
    icon = models.CharField(
        max_length=50, 
        default="📍", 
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['permit', 'order']
        unique_together = [['permit', 'order']]
        indexes = [
            models.Index(fields=['permit', 'order']),
        ]
    
    def __str__(self):
        return f"{self.permit.name} - {self.order}. {self.name}"

