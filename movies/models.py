import os
import re
import uuid
from decimal import Decimal
from urllib.parse import urlparse, parse_qs
from PIL import Image

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.text import slugify
from django.utils import timezone


# ----------------------------------------------------------------------
# Security & Validation Constants & Helpers
# ----------------------------------------------------------------------

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}

YOUTUBE_DOMAINS = {
    'youtube.com',
    'www.youtube.com',
    'm.youtube.com',
    'youtu.be',
    'www.youtube-nocookie.com',
}

YOUTUBE_ID_REGEX = re.compile(r'^[a-zA-Z0-9_-]{11}$')


def validate_image_file(image_field):
    """
    Validates uploaded image file:
    - Maximum size <= 5MB
    - Allowed extensions: .jpg, .jpeg, .png, .webp
    - Valid image header & structure verified via Pillow
    """
    if not image_field:
        return

    file_obj = getattr(image_field, 'file', image_field)

    # Size check
    size = getattr(image_field, 'size', None)
    if size and size > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError(
            f"Image file size cannot exceed 5MB. Uploaded size: {size / (1024 * 1024):.2f}MB."
        )

    # Extension check
    name = getattr(image_field, 'name', '')
    if name:
        ext = os.path.splitext(name)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            allowed = ', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))
            raise ValidationError(
                f"Unsupported image file extension '{ext}'. Allowed extensions: {allowed}."
            )

    # Content integrity check via Pillow
    try:
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
        img = Image.open(file_obj)
        if img.format not in ALLOWED_IMAGE_FORMATS:
            raise ValidationError(
                f"Unsupported image format '{img.format}'. Only JPEG, PNG, and WebP images are allowed."
            )
        img.verify()
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(f"Invalid or corrupted image file: {e}")


def movie_gallery_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        ext = '.jpg'
    safe_name = f"{uuid.uuid4().hex[:16]}{ext}"
    movie_id = instance.movie_id or 'temp'
    return os.path.join('movies', 'gallery', str(movie_id), safe_name)


def movie_poster_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        ext = '.jpg'
    safe_name = f"poster_{uuid.uuid4().hex[:16]}{ext}"
    return os.path.join('movies', 'posters', safe_name)


def cast_photo_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        ext = '.jpg'
    safe_name = f"cast_{uuid.uuid4().hex[:16]}{ext}"
    return os.path.join('cast', safe_name)


def extract_youtube_video_id(url: str) -> str | None:
    """
    Safely extracts an 11-character YouTube video ID from supported URLs:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - https://m.youtube.com/watch?v=VIDEO_ID
    - https://www.youtube.com/shorts/VIDEO_ID
    Returns None if URL is invalid, unsupported, or domain is untrusted.
    """
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception:
        return None

    if parsed.scheme not in ('http', 'https'):
        return None

    hostname = (parsed.hostname or '').lower()
    if hostname not in YOUTUBE_DOMAINS:
        return None

    video_id = None
    if hostname == 'youtu.be':
        path = parsed.path.lstrip('/')
        video_id = path.split('/')[0] if path else None
    else:
        if parsed.path == '/watch':
            query = parse_qs(parsed.query)
            v_list = query.get('v')
            if v_list:
                video_id = v_list[0]
        elif parsed.path.startswith(('/embed/', '/v/', '/shorts/')):
            parts = [p for p in parsed.path.split('/') if p]
            if len(parts) >= 2:
                video_id = parts[1]

    if video_id and YOUTUBE_ID_REGEX.match(video_id):
        return video_id
    return None


def validate_youtube_url(value: str):
    """
    Model / Form validator ensuring trailer URL is a valid, trusted YouTube URL.
    """
    if not value:
        return
    video_id = extract_youtube_video_id(value)
    if not video_id:
        raise ValidationError(
            "Please provide a valid YouTube URL (e.g. https://www.youtube.com/watch?v=... or https://youtu.be/...). "
            "Arbitrary HTML, javascript:, or non-YouTube domains are not permitted."
        )


# ----------------------------------------------------------------------
# Core Relational Models
# ----------------------------------------------------------------------

class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Language(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True, help_text="ISO 639-1 code (e.g., en, hi, es)")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class CastMember(models.Model):
    ROLE_CHOICES = [
        ('actor', 'Actor'),
        ('actress', 'Actress'),
        ('director', 'Director'),
        ('producer', 'Producer'),
        ('writer', 'Writer'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='actor')
    bio = models.TextField(blank=True, default='')
    photo = models.ImageField(upload_to=cast_photo_upload_path, blank=True, null=True, validators=[validate_image_file])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "cast-member"
            candidate = base_slug
            counter = 1
            while CastMember.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"


class Movie(models.Model):
    AGE_CERTIFICATION_CHOICES = [
        ('U', 'U (Universal - All Ages)'),
        ('UA', 'UA (Parental Guidance)'),
        ('A', 'A (Adults Only 18+)'),
        ('S', 'S (Restricted to Special Class)'),
        ('PG', 'PG (Parental Guidance Suggested)'),
        ('PG-13', 'PG-13 (Parents Strongly Cautioned)'),
        ('R', 'R (Restricted 17+)'),
        ('NC-17', 'NC-17 (Adults Only)'),
    ]

    title = models.CharField(max_length=255, blank=True, db_index=True)
    name = models.CharField(max_length=255, blank=True)  # Legacy compatibility
    slug = models.SlugField(max_length=280, unique=True, blank=True, null=True)
    short_description = models.CharField(max_length=500, blank=True, default='')
    detailed_description = models.TextField(blank=True, default='')
    description = models.TextField(blank=True, null=True)  # Legacy compatibility
    release_date = models.DateField(null=True, blank=True, db_index=True)
    age_certification = models.CharField(max_length=20, choices=AGE_CERTIFICATION_CHOICES, default='UA')
    duration = models.PositiveIntegerField(default=120, help_text="Duration in minutes")

    language = models.ForeignKey(
        Language, on_delete=models.SET_NULL, null=True, blank=True, related_name='primary_movies'
    )
    languages = models.ManyToManyField(Language, blank=True, related_name='available_movies')
    genres = models.ManyToManyField(Genre, blank=True, related_name='movies')
    cast_members = models.ManyToManyField(CastMember, blank=True, related_name='movies')
    cast = models.TextField(blank=True, default='')  # Legacy compatibility

    director_name = models.CharField(max_length=255, blank=True, default='')
    director = models.ForeignKey(
        CastMember, on_delete=models.SET_NULL, null=True, blank=True, related_name='directed_movies'
    )

    poster = models.ImageField(upload_to=movie_poster_upload_path, blank=True, null=True, validators=[validate_image_file])
    image = models.ImageField(upload_to="movies/", blank=True, null=True)  # Legacy compatibility

    trailer_url = models.URLField(
        max_length=500, blank=True, default='', validators=[validate_youtube_url],
        help_text="Direct YouTube link (e.g., https://www.youtube.com/watch?v=... or https://youtu.be/...)"
    )
    trailer_video_id = models.CharField(max_length=30, blank=True, default='', help_text="Extracted YouTube Video ID")

    is_active = models.BooleanField(default=True, db_index=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)
    total_reviews = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ['-release_date', '-created_at']
        indexes = [
            models.Index(fields=['is_active', 'release_date']),
            models.Index(fields=['is_active', 'rating']),
        ]

    def clean(self):
        super().clean()
        if self.trailer_url:
            vid = extract_youtube_video_id(self.trailer_url)
            if not vid:
                raise ValidationError({'trailer_url': "Invalid YouTube URL format."})
            self.trailer_video_id = vid

    def save(self, *args, **kwargs):
        # Synchronize title and name for full backward and forward compatibility
        if not self.title and self.name:
            self.title = self.name
        elif not self.name and self.title:
            self.name = self.title
        elif not self.title and not self.name:
            self.title = "Untitled Movie"
            self.name = "Untitled Movie"

        # Unique slug generation
        if not self.slug:
            base_slug = slugify(self.title or self.name) or "movie"
            candidate = base_slug
            counter = 1
            while Movie.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = candidate

        # Synchronize descriptions
        if not self.short_description and self.description:
            self.short_description = self.description[:500]
        elif not self.description and self.short_description:
            self.description = self.short_description

        # Synchronize poster and image
        if self.poster and not self.image:
            self.image = self.poster
        elif self.image and not self.poster:
            self.poster = self.image

        # Extract YouTube ID safely
        if self.trailer_url and not self.trailer_video_id:
            extracted = extract_youtube_video_id(self.trailer_url)
            if extracted:
                self.trailer_video_id = extracted

        super().save(*args, **kwargs)

    def get_primary_poster_url(self) -> str:
        """Returns the primary gallery image, or poster, or image, or placeholder."""
        primary_img = self.gallery_images.filter(is_primary=True).first()
        if primary_img and primary_img.image:
            return primary_img.image.url
        if self.poster:
            return self.poster.url
        if self.image:
            return self.image.url
        return "/static/images/placeholder_poster.jpg"

    def get_youtube_video_id(self) -> str | None:
        """Returns the extracted YouTube video ID, extracting from trailer_url if not cached."""
        if self.trailer_video_id:
            return self.trailer_video_id
        if self.trailer_url:
            return extract_youtube_video_id(self.trailer_url)
        return None

    def get_trailer_embed_url(self) -> str | None:
        """Constructs secure YouTube embed URL with privacy-enhanced domain."""
        vid = self.get_youtube_video_id()
        if vid:
            return f"https://www.youtube-nocookie.com/embed/{vid}"
        return None

    def update_rating_stats(self):
        """Calculates average rating and total count using database aggregation."""
        stats = self.reviews.filter(is_approved=True).aggregate(
            avg_rating=models.Avg('rating'),
            count=models.Count('id')
        )
        avg = stats['avg_rating']
        self.rating = round(Decimal(str(avg)), 1) if avg is not None else Decimal('0.0')
        self.total_reviews = stats['count'] or 0
        Movie.objects.filter(pk=self.pk).update(rating=self.rating, total_reviews=self.total_reviews)

    def __str__(self):
        return self.title or self.name


class MovieImage(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='gallery_images')
    image = models.ImageField(upload_to=movie_gallery_upload_path, validators=[validate_image_file])
    caption = models.CharField(max_length=255, blank=True, default='')
    is_primary = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', '-created_at']

    def save(self, *args, **kwargs):
        if self.is_primary:
            # Demote other primary images for this movie
            MovieImage.objects.filter(movie=self.movie, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.movie.title} (Order: {self.display_order})"


class Theater(models.Model):
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100, blank=True, default='')
    address = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    # Legacy fields preserved as optional for backward compatibility
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='theaters', null=True, blank=True)
    time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        if self.movie and self.time:
            return f'{self.name} - {self.movie.name} at {self.time}'
        return f'{self.name}' + (f' ({self.city})' if self.city else '')


class Screen(models.Model):
    SCREEN_TYPE_CHOICES = [
        ('2D', '2D Standard'),
        ('3D', '3D Digital'),
        ('IMAX', 'IMAX Experience'),
        ('4DX', '4DX Motion'),
        ('Dolby Atmos', 'Dolby Atmos'),
    ]

    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name='screens')
    name = models.CharField(max_length=100, help_text="e.g. Screen 1, Audi 2, IMAX Hall")
    screen_type = models.CharField(max_length=50, choices=SCREEN_TYPE_CHOICES, default='2D')
    seating_capacity = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['theater', 'name']
        unique_together = ('theater', 'name')

    def __str__(self):
        return f"{self.theater.name} - {self.name} ({self.screen_type})"


class ShowSchedule(models.Model):
    SHOW_STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('open', 'Booking Open'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='shows')
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name='shows')
    screen = models.ForeignKey(Screen, on_delete=models.CASCADE, related_name='shows')
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField(db_index=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('150.00'))
    status = models.CharField(max_length=20, choices=SHOW_STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['movie', 'start_time']),
            models.Index(fields=['screen', 'start_time']),
        ]

    def clean(self):
        super().clean()
        if self.screen and self.theater and self.screen.theater != self.theater:
            raise ValidationError({'screen': "The chosen screen does not belong to the selected theater."})

        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError({'end_time': "End time must be strictly after start time."})

            # Check conflicting active shows on the same screen
            conflicting = ShowSchedule.objects.filter(
                screen=self.screen,
                status__in=['scheduled', 'open'],
                start_time__lt=self.end_time,
                end_time__gt=self.start_time
            )
            if self.pk:
                conflicting = conflicting.exclude(pk=self.pk)
            if conflicting.exists():
                conflict = conflicting.first()
                raise ValidationError(
                    f"Scheduling conflict: Screen '{self.screen.name}' already has show for '{conflict.movie.title}' "
                    f"from {conflict.start_time.strftime('%Y-%m-%d %H:%M')} to {conflict.end_time.strftime('%H:%M')}."
                )

    def __str__(self):
        return f"{self.movie.title} at {self.theater.name} ({self.screen.name}) - {self.start_time.strftime('%Y-%m-%d %H:%M')}"


class Seat(models.Model):
    SEAT_TIER_CHOICES = [
        ('VIP', 'VIP Recliner Pod'),
        ('BALCONY', 'Balcony Gold Plus'),
        ('GOLD', 'Gold Club Class'),
        ('SILVER_PLUS', 'Silver Plus'),
        ('SILVER', 'Silver Standard'),
    ]

    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name='seats')
    screen = models.ForeignKey(Screen, on_delete=models.CASCADE, related_name='seats', null=True, blank=True)
    seat_number = models.CharField(max_length=10)
    is_booked = models.BooleanField(default=False)

    tier = models.CharField(max_length=20, choices=SEAT_TIER_CHOICES, default='SILVER')
    row = models.CharField(max_length=5, blank=True, default='')
    number = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('180.00'))

    # Live Hold / Temporary Reservation Lock fields
    locked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='locked_seats')
    lock_session_key = models.CharField(max_length=100, blank=True, default='', db_index=True)
    locked_until = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ['row', 'number', 'seat_number']
        indexes = [
            models.Index(fields=['theater', 'is_booked'], name='seat_th_booked_idx'),
        ]

    def is_currently_locked(self, user=None, session_key=None):
        """
        Returns True if the seat is held by ANOTHER user/session whose hold has not expired.
        """
        if not self.locked_until:
            return False
        if self.locked_until <= timezone.now():
            return False
        if user and user.is_authenticated and self.locked_by_id == user.id:
            return False
        if session_key and self.lock_session_key == session_key:
            return False
        return True

    def is_locked_by_me(self, user=None, session_key=None):
        """
        Returns True if held by the current requesting user/session.
        """
        if not self.locked_until or self.locked_until <= timezone.now():
            return False
        if user and user.is_authenticated and self.locked_by_id == user.id:
            return True
        if session_key and self.lock_session_key == session_key:
            return True
        return False

    def save(self, *args, **kwargs):
        if self.seat_number and (not self.row or self.row == ''):
            m = re.match(r'^([A-Za-z]+)(\d+)$', self.seat_number.strip().upper())
            if m:
                self.row = m.group(1)
                self.number = int(m.group(2))
                if self.tier == 'SILVER' and self.price == Decimal('180.00'):
                    if self.row in ['A', 'B']:
                        self.tier = 'VIP'
                        self.price = Decimal('350.00')
                    elif self.row in ['C', 'D']:
                        self.tier = 'BALCONY'
                        self.price = Decimal('260.00')
                    elif self.row in ['E', 'F']:
                        self.tier = 'GOLD'
                        self.price = Decimal('200.00')
                    elif self.row in ['G', 'H']:
                        self.tier = 'SILVER_PLUS'
                        self.price = Decimal('160.00')
                    else:
                        self.tier = 'SILVER'
                        self.price = Decimal('120.00')
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.seat_number} ({self.get_tier_display()}) in {self.theater.name}'


class Payment(models.Model):
    """
    Records every payment transaction with its gateway reference, payment status,
    transaction ID, cryptographic signature, and audit trails.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending Verification'),
        ('SUCCESS', 'Payment Successful'),
        ('FAILED', 'Payment Failed'),
        ('CANCELLED', 'Payment Cancelled'),
        ('REFUNDED', 'Payment Refunded'),
    ]

    GATEWAY_CHOICES = [
        ('RAZORPAY', 'Razorpay'),
        ('STRIPE', 'Stripe'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('upi', 'UPI / QR'),
        ('card', 'Credit / Debit Card'),
        ('netbanking', 'Net Banking'),
        ('wallet', 'Wallet / FastPay'),
    ]

    order_id = models.CharField(max_length=100, unique=True, db_index=True)
    transaction_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES, default='RAZORPAY')
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHOD_CHOICES, default='upi')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='payments')
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name='payments')
    show = models.ForeignKey(ShowSchedule, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    signature = models.CharField(max_length=255, blank=True, default='')

    seat_ids = models.JSONField(default=list, blank=True)
    seat_numbers = models.CharField(max_length=255, blank=True, default='')

    error_code = models.CharField(max_length=100, blank=True, default='')
    error_description = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at'], name='pay_stat_created_idx'),
            models.Index(fields=['theater', 'status'], name='pay_th_stat_idx'),
            models.Index(fields=['movie', 'status'], name='pay_mv_stat_idx'),
            models.Index(fields=['user', 'status'], name='pay_usr_stat_idx'),
        ]

    def __str__(self):
        return f"Payment {self.order_id} - {self.status} - ₹{self.amount} by {self.user.username}"

    @property
    def is_successful(self):
        return self.status == 'SUCCESS'

    @property
    def is_failed(self):
        return self.status == 'FAILED'

    @property
    def is_cancelled(self):
        return self.status == 'CANCELLED'

    @property
    def is_pending(self):
        return self.status == 'PENDING'


class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    seat = models.OneToOneField(Seat, on_delete=models.CASCADE)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE)
    show = models.ForeignKey(ShowSchedule, on_delete=models.CASCADE, null=True, blank=True, related_name='bookings')
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    booked_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-booked_at']
        indexes = [
            models.Index(fields=['booked_at'], name='book_booked_at_idx'),
            models.Index(fields=['theater', 'booked_at'], name='book_th_booked_idx'),
            models.Index(fields=['movie', 'booked_at'], name='book_mv_booked_idx'),
            models.Index(fields=['user', 'booked_at'], name='book_usr_booked_idx'),
        ]

    def __str__(self):
        return f'Booking by {self.user.username} for {self.seat.seat_number} at {self.theater.name}'




class Review(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='movie_reviews')
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Rating from 1 (lowest) to 5 (highest) stars"
    )
    title = models.CharField(max_length=200, blank=True, default='')
    comment = models.TextField()
    is_verified_viewer = models.BooleanField(
        default=False, db_index=True,
        help_text="Server-verified: User has booked and watched this movie"
    )
    is_approved = models.BooleanField(default=True, db_index=True, help_text="Moderation approval status")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['movie', 'user'], name='unique_movie_user_review'),
            models.CheckConstraint(
                check=models.Q(rating__gte=1) & models.Q(rating__lte=5),
                name='valid_rating_range'
            ),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.movie.update_rating_stats()

    def delete(self, *args, **kwargs):
        movie = self.movie
        super().delete(*args, **kwargs)
        movie.update_rating_stats()

    def __str__(self):
        return f"{self.user.username} - {self.movie.title} ({self.rating}★)"


class ReviewReport(models.Model):
    REPORT_REASONS = [
        ('spam', 'Spam or Advertising'),
        ('harassment', 'Harassment or Hate Speech'),
        ('spoiler', 'Contains Unmarked Spoilers'),
        ('inappropriate', 'Inappropriate or Offensive Language'),
        ('fake', 'Fake or Misleading Content'),
        ('other', 'Other Violation'),
    ]

    REPORT_STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('reviewed', 'Reviewed'),
        ('dismissed', 'Dismissed'),
        ('action_taken', 'Action Taken (Review Hidden)'),
    ]

    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='reports')
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='review_reports')
    reason = models.CharField(max_length=50, choices=REPORT_REASONS)
    details = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=REPORT_STATUS_CHOICES, default='pending', db_index=True)
    moderator_notes = models.TextField(blank=True, default='')
    action_taken_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='moderated_reports'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['review', 'reporter'], name='unique_review_report_per_user'),
        ]

    def __str__(self):
        return f"Report #{self.id} on {self.review} ({self.get_status_display()})"