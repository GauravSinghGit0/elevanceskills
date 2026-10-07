from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Movie, MovieImage, Genre, Language, CastMember,
    Theater, Screen, ShowSchedule, Seat, Booking, Payment,
    Review, ReviewReport
)


class MovieImageInline(admin.TabularInline):
    model = MovieImage
    extra = 1
    fields = ['image_preview', 'image', 'caption', 'is_primary', 'display_order']
    readonly_fields = ['image_preview']

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 60px; max-width: 100px; border-radius: 4px; object-fit: cover;" />',
                obj.image.url
            )
        return "No Image"
    image_preview.short_description = "Preview"


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = [
        'poster_thumbnail', 'title', 'language', 'release_date',
        'age_certification', 'duration_display', 'rating_display',
        'total_reviews', 'is_active'
    ]
    list_display_links = ['poster_thumbnail', 'title']
    list_filter = ['is_active', 'age_certification', 'language', 'genres', 'release_date']
    search_fields = ['title', 'name', 'director_name', 'cast', 'short_description']
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ['genres', 'cast_members', 'languages']
    readonly_fields = ['rating', 'total_reviews', 'trailer_video_id', 'trailer_preview', 'created_at', 'updated_at']
    inlines = [MovieImageInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'name', 'slug', 'is_active')
        }),
        ('Descriptions & Synopsis', {
            'fields': ('short_description', 'detailed_description', 'description')
        }),
        ('Classification & Specifications', {
            'fields': ('age_certification', 'duration', 'release_date')
        }),
        ('Languages & Genres', {
            'fields': ('language', 'languages', 'genres')
        }),
        ('Cast & Crew', {
            'fields': ('director_name', 'director', 'cast_members', 'cast')
        }),
        ('Posters & Gallery Media', {
            'fields': ('poster', 'image')
        }),
        ('Trailer (YouTube)', {
            'fields': ('trailer_url', 'trailer_video_id', 'trailer_preview')
        }),
        ('Statistics & Timestamps', {
            'fields': ('rating', 'total_reviews', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def poster_thumbnail(self, obj):
        url = obj.get_primary_poster_url()
        if url:
            return format_html(
                '<img src="{}" style="height: 50px; width: 35px; border-radius: 3px; object-fit: cover;" />',
                url
            )
        return "-"
    poster_thumbnail.short_description = "Poster"

    def duration_display(self, obj):
        return f"{obj.duration} min"
    duration_display.short_description = "Duration"

    def rating_display(self, obj):
        return format_html('<strong style="color: #f39c12;">★ {}</strong>', obj.rating)
    rating_display.short_description = "Rating"

    def trailer_preview(self, obj):
        if obj.trailer_video_id:
            return format_html(
                '<iframe width="320" height="180" src="https://www.youtube-nocookie.com/embed/{}" '
                'frameborder="0" allowfullscreen sandbox="allow-scripts allow-same-origin"></iframe>',
                obj.trailer_video_id
            )
        return "No trailer configured"
    trailer_preview.short_description = "Trailer Preview"


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active', 'created_at']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}
    list_filter = ['is_active']


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active']
    search_fields = ['name', 'code']
    list_filter = ['is_active']


@admin.register(CastMember)
class CastMemberAdmin(admin.ModelAdmin):
    list_display = ['photo_thumbnail', 'name', 'role', 'is_active']
    list_display_links = ['photo_thumbnail', 'name']
    search_fields = ['name', 'bio']
    list_filter = ['role', 'is_active']
    prepopulated_fields = {'slug': ('name',)}

    def photo_thumbnail(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" style="height: 40px; width: 40px; border-radius: 50%; object-fit: cover;" />',
                obj.photo.url
            )
        return "-"
    photo_thumbnail.short_description = "Photo"


class ScreenInline(admin.TabularInline):
    model = Screen
    extra = 1
    fields = ['name', 'screen_type', 'seating_capacity', 'is_active']


@admin.register(Theater)
class TheaterAdmin(admin.ModelAdmin):
    list_display = ['name', 'city', 'screens_count', 'is_active']
    search_fields = ['name', 'city', 'address']
    list_filter = ['is_active', 'city']
    inlines = [ScreenInline]

    def screens_count(self, obj):
        return obj.screens.count()
    screens_count.short_description = "Screens"


@admin.register(Screen)
class ScreenAdmin(admin.ModelAdmin):
    list_display = ['name', 'theater', 'screen_type', 'seating_capacity', 'is_active']
    list_filter = ['screen_type', 'is_active', 'theater']
    search_fields = ['name', 'theater__name']


@admin.register(ShowSchedule)
class ShowScheduleAdmin(admin.ModelAdmin):
    list_display = ['movie', 'theater', 'screen', 'start_time', 'end_time', 'price', 'status']
    list_filter = ['status', 'theater', 'start_time']
    search_fields = ['movie__title', 'theater__name', 'screen__name']
    date_hierarchy = 'start_time'


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ['theater', 'screen', 'seat_number', 'is_booked']
    list_filter = ['is_booked', 'theater']
    search_fields = ['seat_number', 'theater__name']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['user', 'seat', 'movie', 'theater', 'booked_at']
    list_filter = ['theater', 'booked_at']
    search_fields = ['user__username', 'movie__title', 'seat__seat_number']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['user', 'movie', 'rating_stars', 'is_verified_viewer', 'is_approved', 'created_at']
    list_filter = ['is_approved', 'is_verified_viewer', 'rating', 'created_at']
    search_fields = ['user__username', 'movie__title', 'title', 'comment']
    readonly_fields = ['is_verified_viewer', 'created_at', 'updated_at']
    actions = ['approve_reviews', 'hide_reviews']

    def rating_stars(self, obj):
        return format_html('<span style="color: #f39c12;">{}</span> ({})', '★' * obj.rating, obj.rating)
    rating_stars.short_description = "Rating"

    def approve_reviews(self, request, queryset):
        queryset.update(is_approved=True)
        for r in queryset:
            r.movie.update_rating_stats()
        self.message_user(request, f"Approved {queryset.count()} reviews.")
    approve_reviews.short_description = "Approve selected reviews"

    def hide_reviews(self, request, queryset):
        queryset.update(is_approved=False)
        for r in queryset:
            r.movie.update_rating_stats()
        self.message_user(request, f"Hidden {queryset.count()} reviews.")
    hide_reviews.short_description = "Hide selected reviews from public view"


@admin.register(ReviewReport)
class ReviewReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'reporter', 'review_summary', 'reason', 'status', 'created_at']
    list_filter = ['status', 'reason', 'created_at']
    search_fields = ['reporter__username', 'review__comment', 'details', 'moderator_notes']
    readonly_fields = ['reporter', 'review', 'reason', 'details', 'created_at', 'updated_at']
    actions = ['dismiss_reports', 'take_action_hide_review']

    def review_summary(self, obj):
        return f"{obj.review.movie.title}: {obj.review.comment[:40]}..."
    review_summary.short_description = "Reported Review"

    def dismiss_reports(self, request, queryset):
        queryset.update(status='dismissed', action_taken_by=request.user)
        self.message_user(request, f"Dismissed {queryset.count()} reports.")
    dismiss_reports.short_description = "Dismiss selected reports"

    def take_action_hide_review(self, request, queryset):
        for report in queryset:
            report.status = 'action_taken'
            report.action_taken_by = request.user
            report.save()
            review = report.review
            review.is_approved = False
            review.save()
            review.movie.update_rating_stats()
        self.message_user(request, f"Action taken: {queryset.count()} reviews hidden.")
    take_action_hide_review.short_description = "Take Action: Hide associated review(s)"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'order_id', 'transaction_id', 'user', 'movie', 'theater',
        'amount', 'currency', 'payment_method', 'status', 'created_at'
    ]
    list_filter = ['status', 'gateway', 'payment_method', 'created_at']
    search_fields = ['order_id', 'transaction_id', 'user__username', 'seat_numbers', 'movie__title']
    readonly_fields = ['order_id', 'transaction_id', 'signature', 'created_at', 'updated_at']
