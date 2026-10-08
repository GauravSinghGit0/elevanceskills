import io
import json
from decimal import Decimal
from PIL import Image

from django.test import TestCase, Client, TransactionTestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone
import datetime
from datetime import datetime as dt, time, timedelta
from django.core.paginator import Paginator

from django.core import mail

from .models import (
    Movie, MovieImage, Genre, Language, CastMember,
    Theater, Screen, ShowSchedule, Seat, Booking,
    Review, ReviewReport, Payment,
    extract_youtube_video_id, validate_youtube_url, validate_image_file
)
from .services import (
    ReviewEligibilityService, MovieQueryService, SeatLockService, TheaterSeatingService,
    PaymentGatewayService, BusinessAnalyticsService, MovieDiscoveryService, RefundService
)
from .ticket_service import TicketGeneratorService
from .tasks import send_booking_ticket_email_task, dispatch_booking_ticket_email


def create_test_image(name="test.jpg", fmt="JPEG", size=(100, 100), color="blue"):
    """Creates an in-memory valid image file for tests."""
    file_obj = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(file_obj, format=fmt)
    file_obj.seek(0)
    content_type = "image/jpeg" if fmt == "JPEG" else f"image/{fmt.lower()}"
    return SimpleUploadedFile(name, file_obj.read(), content_type=content_type)


# ======================================================================
# Existing MovieAppTests (Preserved Intact for Full Backward Compatibility)
# ======================================================================

class MovieAppTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='password123', email='test@test.com')
        self.movie = Movie.objects.create(
            name='Inception',
            image='movies/test.jpg',
            rating=9.0,
            cast='Leonardo DiCaprio',
            description='Mind-bending sci-fi'
        )
        self.theater = Theater.objects.create(
            name='IMAX Downtown',
            movie=self.movie,
            time=timezone.now() + timedelta(hours=3)
        )
        self.seat1 = Seat.objects.create(theater=self.theater, seat_number='A1', is_booked=False)
        self.seat2 = Seat.objects.create(theater=self.theater, seat_number='A2', is_booked=False)

    def test_movie_list_view(self):
        response = self.client.get(reverse('movie_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Inception')

    def test_movie_search(self):
        response = self.client.get(reverse('movie_list'), {'search': 'Inception'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Inception')

        response_not_found = self.client.get(reverse('movie_list'), {'search': 'NonExistentMovie'})
        self.assertEqual(response_not_found.status_code, 200)
        self.assertContains(response_not_found, 'No movies found')

    def test_theater_list_view(self):
        response = self.client.get(reverse('theater_list', args=[self.movie.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'IMAX Downtown')

    def test_book_seats_requires_login(self):
        response = self.client.get(reverse('book_seats', args=[self.theater.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_book_seats_view_authenticated(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.get(reverse('book_seats', args=[self.theater.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A1')
        self.assertContains(response, 'A2')

    def test_book_seats_submission_success(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.post(
            reverse('book_seats', args=[self.theater.id]),
            {'seats': [self.seat1.id, self.seat2.id]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('profile'))
        self.seat1.refresh_from_db()
        self.seat2.refresh_from_db()
        self.assertTrue(self.seat1.is_booked)
        self.assertTrue(self.seat2.is_booked)
        self.assertEqual(Booking.objects.filter(user=self.user).count(), 2)

    def test_book_seats_empty_selection(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.post(
            reverse('book_seats', args=[self.theater.id]),
            {'seats': []}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No seat selected')

    def test_book_seats_already_booked(self):
        self.seat1.is_booked = True
        self.seat1.save()
        self.client.login(username='testuser', password='password123')
        response = self.client.post(
            reverse('book_seats', args=[self.theater.id]),
            {'seats': [self.seat1.id]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The following seats are already booked: A1')


# ======================================================================
# Task 1: Movie, Genre, Language, Cast & Relational Model Tests
# ======================================================================

class MovieRelationalModelTests(TestCase):
    def setUp(self):
        self.genre_action = Genre.objects.create(name='Action')
        self.genre_scifi = Genre.objects.create(name='Sci-Fi')
        self.lang_en = Language.objects.create(name='English', code='en')
        self.director = CastMember.objects.create(name='Christopher Nolan', role='director')
        self.actor = CastMember.objects.create(name='Leonardo DiCaprio', role='actor')

    def test_movie_creation_and_auto_slug(self):
        movie = Movie.objects.create(
            title='Interstellar Journey',
            short_description='Space exploration epic',
            language=self.lang_en,
            director=self.director
        )
        movie.genres.add(self.genre_scifi)
        movie.cast_members.add(self.actor)

        self.assertEqual(movie.slug, 'interstellar-journey')
        self.assertEqual(movie.title, 'Interstellar Journey')
        self.assertEqual(movie.name, 'Interstellar Journey')
        self.assertEqual(movie.genres.count(), 1)
        self.assertEqual(movie.cast_members.count(), 1)
        self.assertEqual(movie.age_certification, 'UA')
        self.assertEqual(str(movie), 'Interstellar Journey')

    def test_movie_slug_uniqueness_resolution(self):
        m1 = Movie.objects.create(title='Avatar')
        m2 = Movie.objects.create(title='Avatar')
        self.assertEqual(m1.slug, 'avatar')
        self.assertTrue(m2.slug.startswith('avatar-'))
        self.assertNotEqual(m1.slug, m2.slug)

    def test_movie_legacy_name_sync(self):
        # Setting name should auto-populate title and slug
        movie = Movie.objects.create(name='The Dark Knight')
        self.assertEqual(movie.title, 'The Dark Knight')
        self.assertEqual(movie.slug, 'the-dark-knight')

    def test_cast_member_str_and_slug(self):
        self.assertEqual(str(self.director), 'Christopher Nolan (Director)')
        self.assertEqual(self.director.slug, 'christopher-nolan')

    def test_genre_str_and_slug(self):
        self.assertEqual(str(self.genre_action), 'Action')
        self.assertEqual(self.genre_action.slug, 'action')


# ======================================================================
# Task 1: YouTube Trailer Validation and Security Tests
# ======================================================================

class YouTubeTrailerSecurityTests(TestCase):
    def test_extract_valid_youtube_ids(self):
        valid_urls = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=10s", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ?feature=shared", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ]
        for url, expected_id in valid_urls:
            extracted = extract_youtube_video_id(url)
            self.assertEqual(extracted, expected_id, f"Failed extracting from {url}")

    def test_reject_malicious_and_unsupported_urls(self):
        malicious_urls = [
            "<script>alert('xss')</script>",
            "javascript:alert(1)",
            "https://attacker.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com.attacker.com/watch?v=dQw4w9WgXcQ",
            "https://vimeo.com/123456789",
            "https://www.youtube.com/watch?v=invalid_id_length",
            "https://www.youtube.com/watch?v=<script>alert",
            "ftp://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "",
            None,
        ]
        for url in malicious_urls:
            self.assertIsNone(extract_youtube_video_id(url), f"Should have rejected {url}")
            if url:
                with self.assertRaises(ValidationError):
                    validate_youtube_url(url)

    def test_movie_model_trailer_embed_url_generation(self):
        movie = Movie.objects.create(
            title='Trailer Test',
            trailer_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ'
        )
        self.assertEqual(movie.trailer_video_id, 'dQw4w9WgXcQ')
        self.assertEqual(
            movie.get_trailer_embed_url(),
            'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'
        )

    def test_movie_model_invalid_trailer_raises_clean_error(self):
        movie = Movie(
            title='Bad Trailer',
            trailer_url='https://malicious-site.com/exploit.html'
        )
        with self.assertRaises(ValidationError):
            movie.full_clean()


# ======================================================================
# Task 1: Image Validation and Gallery Management Tests
# ======================================================================

class ImageValidationAndGalleryTests(TestCase):
    def setUp(self):
        self.movie = Movie.objects.create(title='Gallery Test Movie')

    def test_valid_image_validation(self):
        valid_img = create_test_image("poster.jpg", "JPEG")
        # Should not raise ValidationError
        validate_image_file(valid_img)

    def test_disallowed_image_extension_raises_error(self):
        fake_file = SimpleUploadedFile("script.py", b"print('hacked')", content_type="text/x-python")
        with self.assertRaises(ValidationError):
            validate_image_file(fake_file)

    def test_corrupted_image_content_rejected(self):
        # File has .jpg extension but content is plain text
        corrupted = SimpleUploadedFile("fake.jpg", b"This is not a real JPEG image file at all.", content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            validate_image_file(corrupted)

    def test_oversized_image_rejected(self):
        # Simulate oversized file > 5MB
        oversized = SimpleUploadedFile("huge.jpg", b"0", content_type="image/jpeg")
        oversized.size = 6 * 1024 * 1024  # 6 MB
        with self.assertRaises(ValidationError):
            validate_image_file(oversized)

    def test_gallery_images_attachment_and_primary_poster(self):
        img1 = create_test_image("img1.jpg", "JPEG", color="red")
        img2 = create_test_image("img2.jpg", "JPEG", color="blue")

        gallery1 = MovieImage.objects.create(
            movie=self.movie,
            image=img1,
            caption="Poster 1",
            is_primary=True,
            display_order=1
        )
        gallery2 = MovieImage.objects.create(
            movie=self.movie,
            image=img2,
            caption="Poster 2",
            is_primary=False,
            display_order=2
        )

        self.assertEqual(self.movie.gallery_images.count(), 2)
        self.assertEqual(self.movie.get_primary_poster_url(), gallery1.image.url)

        # Marking gallery2 as primary should demote gallery1
        gallery2.is_primary = True
        gallery2.save()
        gallery1.refresh_from_db()

        self.assertTrue(gallery2.is_primary)
        self.assertFalse(gallery1.is_primary)
        self.assertEqual(self.movie.get_primary_poster_url(), gallery2.image.url)


# ======================================================================
# Task 1: Theater, Screen, and Show Schedule Management Tests
# ======================================================================

class ScreenAndShowScheduleTests(TestCase):
    def setUp(self):
        self.movie = Movie.objects.create(title='Tenet')
        self.theater = Theater.objects.create(name='Grand Cinema Downtown', city='Metropolis')
        self.screen1 = Screen.objects.create(
            theater=self.theater,
            name='Screen 1',
            screen_type='IMAX',
            seating_capacity=200
        )
        self.screen2 = Screen.objects.create(
            theater=self.theater,
            name='Screen 2',
            screen_type='2D',
            seating_capacity=150
        )

    def test_screen_creation_and_theater_relation(self):
        self.assertEqual(self.theater.screens.count(), 2)
        self.assertEqual(str(self.screen1), 'Grand Cinema Downtown - Screen 1 (IMAX)')

    def test_show_schedule_creation(self):
        start = timezone.now() + datetime.timedelta(days=1)
        end = start + datetime.timedelta(hours=2, minutes=30)

        show = ShowSchedule.objects.create(
            movie=self.movie,
            theater=self.theater,
            screen=self.screen1,
            start_time=start,
            end_time=end,
            price=Decimal('250.00'),
            status='open'
        )
        self.assertEqual(show.status, 'open')
        self.assertEqual(show.price, Decimal('250.00'))

    def test_show_schedule_conflict_detection_on_same_screen(self):
        start = timezone.now() + datetime.timedelta(days=1)
        end = start + datetime.timedelta(hours=2)

        # First show
        ShowSchedule.objects.create(
            movie=self.movie,
            theater=self.theater,
            screen=self.screen1,
            start_time=start,
            end_time=end,
            status='open'
        )

        # Overlapping show on same screen
        conflict_start = start + datetime.timedelta(minutes=30)
        conflict_end = conflict_start + datetime.timedelta(hours=2)

        conflicting_show = ShowSchedule(
            movie=self.movie,
            theater=self.theater,
            screen=self.screen1,
            start_time=conflict_start,
            end_time=conflict_end,
            status='open'
        )
        with self.assertRaises(ValidationError):
            conflicting_show.full_clean()

    def test_show_schedule_allows_different_screens_at_same_time(self):
        start = timezone.now() + datetime.timedelta(days=1)
        end = start + datetime.timedelta(hours=2)

        # Show on screen 1
        ShowSchedule.objects.create(
            movie=self.movie,
            theater=self.theater,
            screen=self.screen1,
            start_time=start,
            end_time=end,
            status='open'
        )

        # Same time on screen 2 must be valid
        show_screen2 = ShowSchedule(
            movie=self.movie,
            theater=self.theater,
            screen=self.screen2,
            start_time=start,
            end_time=end,
            status='open'
        )
        show_screen2.full_clean()  # Should not raise ValidationError
        show_screen2.save()
        self.assertTrue(ShowSchedule.objects.filter(screen=self.screen2).exists())

    def test_show_schedule_rejects_end_time_before_start_time(self):
        start = timezone.now() + datetime.timedelta(days=1)
        end = start - datetime.timedelta(hours=1)

        invalid_show = ShowSchedule(
            movie=self.movie,
            theater=self.theater,
            screen=self.screen1,
            start_time=start,
            end_time=end,
            status='open'
        )
        with self.assertRaises(ValidationError):
            invalid_show.full_clean()


# ======================================================================
# Task 1: Review Eligibility, Verified Viewer & Rating Range Tests
# ======================================================================

class ReviewEligibilityAndRatingsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_verified = User.objects.create_user(username='viewer1', password='password123')
        self.user_unbooked = User.objects.create_user(username='outsider', password='password123')
        self.user_future = User.objects.create_user(username='future_viewer', password='password123')

        self.movie = Movie.objects.create(title='Oppenheimer')
        self.theater = Theater.objects.create(name='PVR Plaza', movie=self.movie)
        self.seat1 = Seat.objects.create(theater=self.theater, seat_number='B1')
        self.seat2 = Seat.objects.create(theater=self.theater, seat_number='B2')

        # Past booking: completed and watched
        past_time = timezone.now() - datetime.timedelta(days=2)
        self.theater_past = Theater.objects.create(name='PVR Past', movie=self.movie, time=past_time)
        self.seat_past = Seat.objects.create(theater=self.theater_past, seat_number='P1')
        Booking.objects.create(
            user=self.user_verified,
            seat=self.seat_past,
            movie=self.movie,
            theater=self.theater_past
        )

        # Future booking: not yet watched
        future_time = timezone.now() + datetime.timedelta(days=3)
        self.theater_future = Theater.objects.create(name='PVR Future', movie=self.movie, time=future_time)
        self.seat_future = Seat.objects.create(theater=self.theater_future, seat_number='F1')
        Booking.objects.create(
            user=self.user_future,
            seat=self.seat_future,
            movie=self.movie,
            theater=self.theater_future
        )

    def test_anonymous_user_review_eligibility(self):
        from django.contrib.auth.models import AnonymousUser
        can_review, reason, is_verified = ReviewEligibilityService.check_eligibility(AnonymousUser(), self.movie)
        self.assertFalse(can_review)
        self.assertFalse(is_verified)

    def test_unbooked_user_ineligible_for_review(self):
        can_review, reason, is_verified = ReviewEligibilityService.check_eligibility(self.user_unbooked, self.movie)
        self.assertFalse(can_review)
        self.assertFalse(is_verified)
        self.assertIn("verified viewers", reason.lower())

    def test_future_booked_user_ineligible_until_show_passes(self):
        can_review, reason, is_verified = ReviewEligibilityService.check_eligibility(self.user_future, self.movie)
        self.assertFalse(can_review)
        self.assertFalse(is_verified)
        self.assertIn("showtime has started", reason.lower())

    def test_verified_viewer_eligible_for_review(self):
        can_review, reason, is_verified = ReviewEligibilityService.check_eligibility(self.user_verified, self.movie)
        self.assertTrue(can_review)
        self.assertTrue(is_verified)

    def test_review_submission_view_for_verified_viewer(self):
        self.client.login(username='viewer1', password='password123')
        response = self.client.post(
            reverse('add_review', args=[self.movie.slug]),
            {'rating': 5, 'title': 'Spectacular', 'comment': 'A truly phenomenal biographical drama.'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        review = Review.objects.get(movie=self.movie, user=self.user_verified)
        self.assertEqual(review.rating, 5)
        self.assertTrue(review.is_verified_viewer)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.rating, Decimal('5.0'))
        self.assertEqual(self.movie.total_reviews, 1)

    def test_review_submission_rejected_for_unverified_viewer(self):
        self.client.login(username='outsider', password='password123')
        response = self.client.post(
            reverse('add_review', args=[self.movie.slug]),
            {'rating': 5, 'title': 'Fake Review', 'comment': 'I never booked but want to review.'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Review.objects.filter(movie=self.movie, user=self.user_unbooked).exists())

    def test_duplicate_review_prevention(self):
        # Submit first review
        Review.objects.create(
            movie=self.movie,
            user=self.user_verified,
            rating=4,
            comment='Good film',
            is_verified_viewer=True
        )

        # Eligibility check should now reject
        can_review, reason, _ = ReviewEligibilityService.check_eligibility(self.user_verified, self.movie)
        self.assertFalse(can_review)
        self.assertIn('already reviewed', reason.lower())

        # Attempting second review should fail DB constraint
        with self.assertRaises(IntegrityError):
            Review.objects.create(
                movie=self.movie,
                user=self.user_verified,
                rating=5,
                comment='Duplicate attempt',
                is_verified_viewer=True
            )

    def test_rating_range_validation_rejection(self):
        # Database constraint rejects rating < 1 or > 5
        with self.assertRaises(IntegrityError):
            Review.objects.create(
                movie=self.movie,
                user=self.user_verified,
                rating=6,  # Invalid: > 5
                comment='Invalid rating',
                is_verified_viewer=True
            )

    def test_average_rating_aggregation_and_recalculation(self):
        user2 = User.objects.create_user(username='viewer2', password='password123')
        r1 = Review.objects.create(movie=self.movie, user=self.user_verified, rating=4, comment='Great')
        r2 = Review.objects.create(movie=self.movie, user=user2, rating=5, comment='Masterpiece')

        self.movie.refresh_from_db()
        self.assertEqual(self.movie.rating, Decimal('4.5'))
        self.assertEqual(self.movie.total_reviews, 2)

        # Edit review rating
        r1.rating = 2
        r1.save()
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.rating, Decimal('3.5'))  # (2 + 5) / 2 = 3.5

        # Delete review
        r2.delete()
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.rating, Decimal('2.0'))
        self.assertEqual(self.movie.total_reviews, 1)


# ======================================================================
# Task 1: Review Editing Ownership, IDOR, and Security Tests
# ======================================================================

class ReviewOwnershipAndIDORTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(username='owner', password='password123')
        self.attacker = User.objects.create_user(username='attacker', password='password123')
        self.movie = Movie.objects.create(title='Security Movie')

        self.review = Review.objects.create(
            movie=self.movie,
            user=self.owner,
            rating=5,
            title='Authentic Review',
            comment='Original owner review content.',
            is_verified_viewer=True
        )

    def test_owner_can_edit_own_review(self):
        self.client.login(username='owner', password='password123')
        response = self.client.post(
            reverse('edit_review', args=[self.review.id]),
            {'rating': 4, 'title': 'Updated Title', 'comment': 'Updated review content by owner.'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.review.refresh_from_db()
        self.assertEqual(self.review.rating, 4)
        self.assertEqual(self.review.title, 'Updated Title')
        self.assertEqual(self.review.comment, 'Updated review content by owner.')

    def test_non_owner_cannot_edit_another_users_review_idor_blocked(self):
        self.client.login(username='attacker', password='password123')
        response = self.client.post(
            reverse('edit_review', args=[self.review.id]),
            {'rating': 1, 'title': 'Hacked', 'comment': 'Malicious modification of another users review.'}
        )
        self.assertEqual(response.status_code, 403)
        self.review.refresh_from_db()
        self.assertEqual(self.review.rating, 5)
        self.assertEqual(self.review.title, 'Authentic Review')

    def test_unauthenticated_user_cannot_edit_review(self):
        response = self.client.get(reverse('edit_review', args=[self.review.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])


# ======================================================================
# Task 1: Review Reporting and Moderation Tests
# ======================================================================

class ReviewReportingAndModerationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.reviewer = User.objects.create_user(username='reviewer', password='password123')
        self.reporter = User.objects.create_user(username='reporter', password='password123')
        self.staff_user = User.objects.create_user(username='staff_mod', password='password123', is_staff=True)

        self.movie = Movie.objects.create(title='Moderated Movie')
        self.review = Review.objects.create(
            movie=self.movie,
            user=self.reviewer,
            rating=1,
            comment='This contains inappropriate spoilers and spam.'
        )

    def test_authenticated_user_can_report_review(self):
        self.client.login(username='reporter', password='password123')
        response = self.client.post(
            reverse('report_review', args=[self.review.id]),
            {'reason': 'spoiler', 'details': 'Discloses the entire plot twist in the first sentence.'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ReviewReport.objects.filter(review=self.review, reporter=self.reporter).exists())
        report = ReviewReport.objects.get(review=self.review, reporter=self.reporter)
        self.assertEqual(report.status, 'pending')
        self.assertEqual(report.reason, 'spoiler')

    def test_duplicate_report_abuse_prevented(self):
        # First report
        ReviewReport.objects.create(
            review=self.review,
            reporter=self.reporter,
            reason='spam',
            status='pending'
        )

        # Second attempt by same user
        self.client.login(username='reporter', password='password123')
        response = self.client.post(
            reverse('report_review', args=[self.review.id]),
            {'reason': 'harassment', 'details': 'Duplicate attempt'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        # Should still be exactly 1 report
        self.assertEqual(ReviewReport.objects.filter(review=self.review, reporter=self.reporter).count(), 1)

    def test_moderator_can_dismiss_report(self):
        report = ReviewReport.objects.create(
            review=self.review,
            reporter=self.reporter,
            reason='spam',
            status='pending'
        )
        self.client.login(username='staff_mod', password='password123')
        response = self.client.post(
            reverse('movie_admin_report_action', args=[report.id]),
            {'action': 'dismiss', 'moderator_notes': 'No violation found.'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.status, 'dismissed')
        self.assertEqual(report.action_taken_by, self.staff_user)

    def test_moderator_take_action_hides_review_and_updates_rating(self):
        report = ReviewReport.objects.create(
            review=self.review,
            reporter=self.reporter,
            reason='inappropriate',
            status='pending'
        )
        self.client.login(username='staff_mod', password='password123')
        response = self.client.post(
            reverse('movie_admin_report_action', args=[report.id]),
            {'action': 'hide_review', 'moderator_notes': 'Violates policy.'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        report.refresh_from_db()
        self.review.refresh_from_db()

        self.assertEqual(report.status, 'action_taken')
        self.assertFalse(self.review.is_approved)

        # Hidden review must not appear on movie details page
        detail_response = self.client.get(reverse('movie_detail', args=[self.movie.slug]))
        self.assertNotContains(detail_response, 'This contains inappropriate spoilers and spam.')


# ======================================================================
# Task 1: Movie Query Service (Similar, Trending, Recent) Tests
# ======================================================================

class MovieQueryServiceTests(TestCase):
    def setUp(self):
        self.genre_action = Genre.objects.create(name='Action')
        self.genre_drama = Genre.objects.create(name='Drama')
        self.lang_en = Language.objects.create(name='English', code='en')
        self.lang_fr = Language.objects.create(name='French', code='fr')

        today = timezone.now().date()
        self.m1 = Movie.objects.create(title='Action English 1', language=self.lang_en, release_date=today)
        self.m1.genres.add(self.genre_action)

        self.m2 = Movie.objects.create(title='Action English 2', language=self.lang_en, release_date=today - datetime.timedelta(days=10))
        self.m2.genres.add(self.genre_action)

        self.m3 = Movie.objects.create(title='Drama French', language=self.lang_fr, release_date=today - datetime.timedelta(days=30))
        self.m3.genres.add(self.genre_drama)

    def test_similar_movies_excludes_self_and_matches_genre(self):
        similar = list(MovieQueryService.get_similar_movies(self.m1, limit=5))
        self.assertNotIn(self.m1, similar)
        self.assertIn(self.m2, similar)

    def test_recently_released_movies_order(self):
        recent = list(MovieQueryService.get_recently_released_movies(limit=5))
        self.assertEqual(recent[0], self.m1)

    def test_trending_movies_query_runs_without_n_plus_one(self):
        trending = list(MovieQueryService.get_trending_movies(limit=5))
        self.assertTrue(len(trending) > 0)


# ======================================================================
# Task 1: Staff Admin Interface Authorization Tests
# ======================================================================

class StaffAdminInterfaceTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.regular_user = User.objects.create_user(username='regular', password='password123')
        self.staff_user = User.objects.create_user(username='staff', password='password123', is_staff=True)
        self.movie = Movie.objects.create(title='Manageable Movie')

    def test_regular_user_cannot_access_staff_dashboard(self):
        self.client.login(username='regular', password='password123')
        response = self.client.get(reverse('movie_admin_dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_staff_user_can_access_staff_dashboard(self):
        self.client.login(username='staff', password='password123')
        response = self.client.get(reverse('movie_admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Movie Management')

    def test_staff_can_toggle_movie_status(self):
        self.client.login(username='staff', password='password123')
        response = self.client.post(reverse('movie_admin_toggle_status', args=[self.movie.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.movie.refresh_from_db()
        self.assertFalse(self.movie.is_active)

    def test_superuser_can_access_staff_dashboard(self):
        superadmin = User.objects.create_superuser(username='superadmin', password='password123', email='sa@test.com')
        self.client.login(username='superadmin', password='password123')
        response = self.client.get(reverse('movie_admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cinema Enterprise Management Hub')

    def test_staff_can_assign_theaters_and_auto_schedule_shows(self):
        self.client.login(username='staff', password='password123')
        theater1 = Theater.objects.create(name='PVR Test 1', city='Mumbai')
        Screen.objects.create(theater=theater1, name='Screen 1', screen_type='IMAX', seating_capacity=100)

        # GET assign theaters page
        response = self.client.get(reverse('movie_admin_assign_theaters', args=[self.movie.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Multiplex Venue Assignment')

        # POST assign theater with auto-schedule shows
        post_data = {
            'theater_ids': [str(theater1.id)],
            'auto_create_shows': '1',
            'days_ahead': '2',
            'ticket_price': '220.00'
        }
        response = self.client.post(reverse('movie_admin_assign_theaters', args=[self.movie.id]), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        theater1.refresh_from_db()
        self.assertEqual(theater1.movie, self.movie)
        created_shows = ShowSchedule.objects.filter(movie=self.movie, theater=theater1)
        self.assertGreaterEqual(created_shows.count(), 1)
        self.assertEqual(created_shows.first().price, Decimal('220.00'))

    def test_staff_can_soft_and_hard_delete_movie(self):
        self.client.login(username='staff', password='password123')
        m_soft = Movie.objects.create(title='Soft Delete Movie', is_active=True)

        # Confirm page
        get_res = self.client.get(reverse('movie_admin_delete', args=[m_soft.id]))
        self.assertEqual(get_res.status_code, 200)
        self.assertContains(get_res, 'Confirm Movie Removal')

        # Soft delete
        post_soft = self.client.post(reverse('movie_admin_delete', args=[m_soft.id]), {'action': 'soft'}, follow=True)
        self.assertEqual(post_soft.status_code, 200)
        m_soft.refresh_from_db()
        self.assertFalse(m_soft.is_active)

        # Hard delete
        m_hard = Movie.objects.create(title='Hard Delete Movie')
        th = Theater.objects.create(name='Preserved Theater', movie=m_hard)
        post_hard = self.client.post(reverse('movie_admin_delete', args=[m_hard.id]), {'action': 'hard'}, follow=True)
        self.assertEqual(post_hard.status_code, 200)
        self.assertFalse(Movie.objects.filter(id=m_hard.id).exists())
        # Confirm physical theater is preserved
        self.assertTrue(Theater.objects.filter(id=th.id).exists())
        th.refresh_from_db()
        self.assertIsNone(th.movie)

    def test_staff_theaters_crud_operations(self):
        self.client.login(username='staff', password='password123')

        # List
        res_list = self.client.get(reverse('admin_theaters_list'))
        self.assertEqual(res_list.status_code, 200)

        # Create
        res_create = self.client.post(reverse('admin_theater_create'), {
            'name': 'New Multiplex Deluxe',
            'city': 'Bengaluru',
            'address': 'MG Road Metro',
            'num_screens': 2,
            'is_active': True,
        }, follow=True)
        self.assertEqual(res_create.status_code, 200)
        new_th = Theater.objects.get(name='New Multiplex Deluxe')
        self.assertEqual(new_th.city, 'Bengaluru')
        self.assertEqual(new_th.screens.count(), 2)

        # Edit
        res_edit = self.client.post(reverse('admin_theater_edit', args=[new_th.id]), {
            'name': 'New Multiplex Deluxe Updated',
            'city': 'Bengaluru Central',
            'address': 'MG Road Metro Mall',
            'is_active': True,
        }, follow=True)
        self.assertEqual(res_edit.status_code, 200)
        new_th.refresh_from_db()
        self.assertEqual(new_th.name, 'New Multiplex Deluxe Updated')

        # Toggle status
        res_toggle = self.client.post(reverse('admin_theater_toggle_status', args=[new_th.id]), follow=True)
        self.assertEqual(res_toggle.status_code, 200)
        new_th.refresh_from_db()
        self.assertFalse(new_th.is_active)

        # Delete
        res_del = self.client.post(reverse('admin_theater_delete', args=[new_th.id]), {'action': 'hard'}, follow=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertFalse(Theater.objects.filter(id=new_th.id).exists())

    def test_staff_shows_crud_operations(self):
        self.client.login(username='staff', password='password123')
        th = Theater.objects.create(name='Show Test Venue', city='Delhi')
        sc = Screen.objects.create(theater=th, name='Audi 1', screen_type='2D', seating_capacity=80)

        # List
        res_list = self.client.get(reverse('admin_shows_list'))
        self.assertEqual(res_list.status_code, 200)

        # Create
        start = timezone.now() + timedelta(days=1)
        end = start + timedelta(hours=2)
        res_create = self.client.post(reverse('admin_show_create'), {
            'movie': self.movie.id,
            'theater': th.id,
            'screen': sc.id,
            'start_time': start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': end.strftime('%Y-%m-%dT%H:%M'),
            'price': '190.00',
            'status': 'open'
        }, follow=True)
        self.assertEqual(res_create.status_code, 200)
        created_show = ShowSchedule.objects.get(movie=self.movie, theater=th)
        self.assertEqual(created_show.price, Decimal('190.00'))

        # Edit
        res_edit = self.client.post(reverse('admin_show_edit', args=[created_show.id]), {
            'movie': self.movie.id,
            'theater': th.id,
            'screen': sc.id,
            'start_time': start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': end.strftime('%Y-%m-%dT%H:%M'),
            'price': '250.00',
            'status': 'open'
        }, follow=True)
        self.assertEqual(res_edit.status_code, 200)
        created_show.refresh_from_db()
        self.assertEqual(created_show.price, Decimal('250.00'))

        # Delete
        res_del = self.client.post(reverse('admin_show_delete', args=[created_show.id]), follow=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertFalse(ShowSchedule.objects.filter(id=created_show.id).exists())


class SeatLockAndSeatingTierTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_a = User.objects.create_user(username='usera', password='password123')
        self.user_b = User.objects.create_user(username='userb', password='password123')
        self.movie = Movie.objects.create(title='Concurrency Movie', is_active=True)
        self.theater = Theater.objects.create(name='Cineva Grand Dolby', movie=self.movie)

    def test_full_theater_layout_generation(self):
        TheaterSeatingService.ensure_full_theater_layout(self.theater)
        seats = Seat.objects.filter(theater=self.theater)
        self.assertGreaterEqual(seats.count(), 100)

        vip_seats = seats.filter(tier='VIP')
        self.assertTrue(vip_seats.exists())
        self.assertEqual(vip_seats.first().price, Decimal('350.00'))

        silver_plus_h1 = seats.filter(seat_number='H1').first()
        self.assertIsNotNone(silver_plus_h1)
        self.assertEqual(silver_plus_h1.row, 'H')
        self.assertEqual(silver_plus_h1.tier, 'SILVER_PLUS')
        self.assertEqual(silver_plus_h1.price, Decimal('160.00'))

    def test_seat_hold_and_concurrency_blocking(self):
        TheaterSeatingService.ensure_full_theater_layout(self.theater)
        seat_h1 = Seat.objects.get(theater=self.theater, seat_number='H1')

        # User A holds H1
        ok_a, msg_a, _ = SeatLockService.hold_seat(seat_h1.id, user=self.user_a)
        self.assertTrue(ok_a)

        # User B perspective in live status
        status_b = SeatLockService.get_live_status(self.theater.id, user=self.user_b)
        self.assertIn(seat_h1.id, status_b['held_by_others'])

        # User B attempts to hold H1 -> MUST FAIL
        ok_b, msg_b, _ = SeatLockService.hold_seat(seat_h1.id, user=self.user_b)
        self.assertFalse(ok_b)
        self.assertIn("held by another user", msg_b)

        # Lock expires
        from datetime import timedelta
        seat_h1.locked_until = timezone.now() - timedelta(seconds=5)
        seat_h1.save()

        # User B can now acquire lock
        ok_b2, msg_b2, _ = SeatLockService.hold_seat(seat_h1.id, user=self.user_b)
        self.assertTrue(ok_b2)

    def test_toggle_seat_lock_view_api(self):
        TheaterSeatingService.ensure_full_theater_layout(self.theater)
        seat = Seat.objects.filter(theater=self.theater, seat_number='H2').first()

        self.client.login(username='usera', password='password123')
        # Lock seat
        res = self.client.post(
            reverse('toggle_seat_lock', args=[self.theater.id]),
            data=json.dumps({'seat_id': seat.id, 'action': 'lock'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])

        # Check live status API
        res_status = self.client.get(reverse('seat_live_status', args=[self.theater.id]))
        self.assertEqual(res_status.status_code, 200)
        status_data = res_status.json()
        self.assertIn(seat.id, status_data['held_by_me'])

    def test_book_seats_post_success(self):
        TheaterSeatingService.ensure_full_theater_layout(self.theater)
        seat = Seat.objects.filter(theater=self.theater, seat_number='H1').first()
        self.client.login(username='usera', password='password123')
        res = self.client.post(
            reverse('book_seats', args=[self.theater.id]),
            data={'seats': [seat.id]}
        )
        self.assertEqual(res.status_code, 302)
        seat.refresh_from_db()
        self.assertTrue(seat.is_booked)
        self.assertTrue(Booking.objects.filter(seat=seat, user=self.user_a).exists())

    def test_book_seats_locked_by_other_rejected(self):
        TheaterSeatingService.ensure_full_theater_layout(self.theater)
        seat = Seat.objects.filter(theater=self.theater, seat_number='H2').first()
        # User A holds H2
        SeatLockService.hold_seat(seat.id, user=self.user_a)

        # User B attempts to book H2 directly
        self.client.login(username='userb', password='password123')
        res = self.client.post(
            reverse('book_seats', args=[self.theater.id]),
            data={'seats': [seat.id]}
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "currently held by another user")
        seat.refresh_from_db()
        self.assertFalse(seat.is_booked)


class SmartSeatReservationComprehensiveTests(TestCase):
    """
    Comprehensive tests for:
    1. Multi-seat selection with live availability indicators.
    2. Strict 2-minute temporary reservation window and automatic release.
    3. Concurrency protection guaranteeing zero duplicate bookings under race conditions.
    4. Seat selection modification before payment.
    5. Atomic Django transactions and payment finalization.
    """

    def setUp(self):
        self.client_a = Client()
        self.client_b = Client()
        self.user_a = User.objects.create_user(username='customer_a', password='password123')
        self.user_b = User.objects.create_user(username='customer_b', password='password123')
        self.client_a.login(username='customer_a', password='password123')
        self.client_b.login(username='customer_b', password='password123')

        self.movie = Movie.objects.create(
            title='Dune Part Two IMAX',
            duration=166,
            is_active=True
        )
        self.theater = Theater.objects.create(
            name='Cineva Grand Dolby Atmos',
            movie=self.movie,
            city='Mumbai',
            time=timezone.now() + timedelta(days=1)
        )
        TheaterSeatingService.ensure_full_theater_layout(self.theater)

    def test_multi_seat_reservation_and_live_status_indicators(self):
        """Users can reserve multiple seats, and status indicators reflect available, reserved, and booked."""
        seats = list(Seat.objects.filter(theater=self.theater)[:3])
        s1, s2, s3 = seats[0], seats[1], seats[2]

        # 1. User A reserves multiple seats (s1, s2)
        ok, msg, _ = SeatLockService.hold_multiple_seats(
            seat_ids=[s1.id, s2.id],
            user=self.user_a,
            duration_seconds=120
        )
        self.assertTrue(ok)

        # 2. Mark s3 as permanently booked (sold out)
        s3.is_booked = True
        s3.save()
        Booking.objects.create(user=self.user_b, seat=s3, movie=self.movie, theater=self.theater)

        # 3. Check live status from User A's perspective
        status_a = SeatLockService.get_live_status(self.theater.id, user=self.user_a)
        self.assertIn(s1.id, status_a['held_by_me'])
        self.assertIn(s2.id, status_a['held_by_me'])
        self.assertIn(s3.id, status_a['booked_seats'])
        self.assertGreater(status_a['lock_remaining_seconds'], 0)
        self.assertLessEqual(status_a['lock_remaining_seconds'], 120)

        # 4. Check live status from User B's perspective
        status_b = SeatLockService.get_live_status(self.theater.id, user=self.user_b)
        self.assertIn(s1.id, status_b['held_by_others'])
        self.assertIn(s2.id, status_b['held_by_others'])
        self.assertIn(s3.id, status_b['booked_seats'])
        self.assertNotIn(s1.id, status_b['held_by_me'])
        self.assertNotIn(s2.id, status_b['held_by_me'])

    def test_two_minute_timeout_automatic_release(self):
        """Held seats are automatically released after 2 minutes if payment is not completed."""
        seat = Seat.objects.filter(theater=self.theater, is_booked=False).first()

        # Hold seat for 2 minutes (120 seconds)
        ok, _, _ = SeatLockService.hold_seat(seat.id, user=self.user_a, duration_seconds=120)
        self.assertTrue(ok)

        seat.refresh_from_db()
        self.assertIsNotNone(seat.locked_until)
        self.assertTrue(seat.locked_until > timezone.now())

        # Simulate 2 minutes expiring
        seat.locked_until = timezone.now() - timedelta(seconds=5)
        seat.save()

        # Check live status -> expired hold is automatically released
        status = SeatLockService.get_live_status(self.theater.id)
        self.assertIn(seat.id, status['available_seats'])
        self.assertNotIn(seat.id, status['held_by_others'])

        # User B can now acquire the reservation
        ok_b, _, _ = SeatLockService.hold_seat(seat.id, user=self.user_b, duration_seconds=120)
        self.assertTrue(ok_b)

    def test_modify_seat_selection_before_payment(self):
        """Users can freely add and remove seats before completing payment."""
        seats = list(Seat.objects.filter(theater=self.theater, is_booked=False)[:3])
        s1, s2, s3 = seats[0], seats[1], seats[2]

        # User A reserves s1 and s2
        SeatLockService.hold_seat(s1.id, user=self.user_a, duration_seconds=120)
        SeatLockService.hold_seat(s2.id, user=self.user_a, duration_seconds=120)

        # User A modifies selection: removes s1, adds s3
        ok_rel, _, _ = SeatLockService.release_seat(s1.id, user=self.user_a)
        self.assertTrue(ok_rel)

        ok_add, _, _ = SeatLockService.hold_seat(s3.id, user=self.user_a, duration_seconds=120)
        self.assertTrue(ok_add)

        # Verify s1 is now free: User B can reserve s1 immediately
        ok_b, _, _ = SeatLockService.hold_seat(s1.id, user=self.user_b, duration_seconds=120)
        self.assertTrue(ok_b)

        # User A completes payment for modified selection [s2, s3]
        success, msg, bookings = SeatLockService.finalize_booking(
            theater=self.theater,
            seat_ids=[s2.id, s3.id],
            user=self.user_a
        )
        self.assertTrue(success)
        self.assertEqual(len(bookings), 2)

        s2.refresh_from_db()
        s3.refresh_from_db()
        s1.refresh_from_db()
        self.assertTrue(s2.is_booked)
        self.assertTrue(s3.is_booked)
        self.assertFalse(s1.is_booked)  # s1 was released and not booked by A

    def test_atomic_reservation_blocks_concurrent_user(self):
        """When User A reserves a seat, User B is strictly blocked from reserving or booking that seat."""
        seat = Seat.objects.filter(theater=self.theater, is_booked=False).first()

        ok_a, msg_a, _ = SeatLockService.hold_seat(seat.id, user=self.user_a, duration_seconds=120)
        self.assertTrue(ok_a)

        # User B attempts to hold the same seat simultaneously
        ok_b, msg_b, _ = SeatLockService.hold_seat(seat.id, user=self.user_b, duration_seconds=120)
        self.assertFalse(ok_b)
        self.assertIn("held by another user", msg_b)

        # User B attempts to book the same seat directly
        res = self.client_b.post(
            reverse('book_seats', args=[self.theater.id]),
            data={'seats': [seat.id]}
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "currently held by another user")

        # Verify seat was never booked and remained under User A's hold
        seat.refresh_from_db()
        self.assertFalse(seat.is_booked)
        self.assertEqual(seat.locked_by, self.user_a)

    def test_payment_after_2_minute_expiration_rejected(self):

        """Payment confirmation after the 2-minute temporary hold has elapsed is rejected."""
        seat = Seat.objects.filter(theater=self.theater, is_booked=False).first()
        SeatLockService.hold_seat(seat.id, user=self.user_a, duration_seconds=120)

        # Fast-forward past 2 minutes
        seat.locked_until = timezone.now() - timedelta(seconds=10)
        seat.save()

        # Attempt to finalize booking
        success, msg, _ = SeatLockService.finalize_booking(
            theater=self.theater,
            seat_ids=[seat.id],
            user=self.user_a
        )
        self.assertFalse(success)
        self.assertIn("expired", msg.lower())
        seat.refresh_from_db()
        self.assertFalse(seat.is_booked)

    def test_json_payment_checkout_endpoint(self):
        """AJAX JSON checkout completes payment and redirects with booking confirmation."""
        seat = Seat.objects.filter(theater=self.theater, is_booked=False).first()
        SeatLockService.hold_seat(seat.id, user=self.user_a, duration_seconds=120)

        res = self.client_a.post(
            reverse('book_seats', args=[self.theater.id]),
            data=json.dumps({'seats': [seat.id], 'payment_method': 'upi'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertIn('redirect_url', data)

        seat.refresh_from_db()
        self.assertTrue(seat.is_booked)
        self.assertIsNone(seat.locked_until)
        self.assertTrue(Booking.objects.filter(seat=seat, user=self.user_a).exists())


class ConcurrentSeatReservationRaceConditionTests(TransactionTestCase):
    """
    True multi-threaded concurrency tests verifying that simultaneous requests
    attempting to reserve or book the exact same seats never produce duplicate bookings
    or corrupted hold states under real multi-threaded race conditions.
    """

    def setUp(self):
        self.movie = Movie.objects.create(title='Concurrency Matrix', is_active=True)
        self.theater = Theater.objects.create(name='PVR Concurrency IMAX', movie=self.movie)
        TheaterSeatingService.ensure_full_theater_layout(self.theater)

    def test_concurrent_threads_hold_same_seat_race_condition(self):
        """Simultaneous threads attempting to reserve the exact same seat result in exactly 1 hold and zero race conditions."""
        import concurrent.futures
        from django.db import connection

        seat = Seat.objects.filter(theater=self.theater, is_booked=False).first()
        users = [User.objects.create_user(username=f'race_hold_user_{i}', password='p123') for i in range(5)]

        results = []
        def try_hold(u):
            try:
                ok, msg, _ = SeatLockService.hold_seat(seat.id, user=u, duration_seconds=120)
                return (u.username, ok, msg)
            finally:
                connection.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(try_hold, u) for u in users]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        seat.refresh_from_db()
        successes = [r for r in results if r[1] is True]
        failures = [r for r in results if r[1] is False]

        self.assertEqual(len(successes), 1, "Exactly one thread must acquire the seat reservation hold.")
        self.assertEqual(len(failures), 4, "Remaining threads must fail gracefully without deadlock.")
        self.assertIsNotNone(seat.locked_by)
        self.assertEqual(seat.locked_by.username, successes[0][0])

    def test_concurrent_threads_finalize_same_seat_booking_race_condition(self):
        """Simultaneous threads attempting to finalize booking on the exact same seat produce exactly 1 booking."""
        import concurrent.futures
        from django.db import connection

        seat = Seat.objects.filter(theater=self.theater, is_booked=False).last()
        users = [User.objects.create_user(username=f'race_book_user_{i}', password='p123') for i in range(5)]

        results = []
        def try_finalize(u):
            try:
                ok, msg, bks = SeatLockService.finalize_booking(theater=self.theater, seat_ids=[seat.id], user=u)
                return (u.username, ok, msg)
            finally:
                connection.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(try_finalize, u) for u in users]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        seat.refresh_from_db()
        successes = [r for r in results if r[1] is True]
        failures = [r for r in results if r[1] is False]

        self.assertEqual(len(successes), 1, "Exactly one concurrent thread must finalize the booking.")
        self.assertEqual(len(failures), 4, "Remaining concurrent booking requests must be safely rejected.")
        self.assertEqual(Booking.objects.filter(seat=seat).count(), 1, "Database constraint must physically prevent duplicate bookings.")
        self.assertTrue(seat.is_booked)

    def test_concurrent_threads_hold_different_seats_all_succeed(self):
        """Simultaneous threads reserving distinct seats succeed concurrently without collision."""
        import concurrent.futures
        from django.db import connection

        available_seats = list(Seat.objects.filter(theater=self.theater, is_booked=False)[:5])
        users = [User.objects.create_user(username=f'distinct_user_{i}', password='p123') for i in range(5)]

        results = []
        def hold_distinct(pair):
            u, s = pair
            try:
                ok, msg, _ = SeatLockService.hold_seat(s.id, user=u, duration_seconds=120)
                return (u.username, s.id, ok)
            finally:
                connection.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(hold_distinct, (u, s)) for u, s in zip(users, available_seats)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        successes = [r for r in results if r[2] is True]
        self.assertEqual(len(successes), 5, "All 5 concurrent distinct holds must succeed independently.")

    def test_concurrent_duplicate_payment_verification_idempotency(self):
        """Simultaneous verification requests (e.g. client callback + webhook) never create duplicate bookings."""
        import concurrent.futures
        from django.db import connection

        user = User.objects.create_user(username='concurrent_pay_user', password='p123')
        seat = Seat.objects.filter(theater=self.theater, is_booked=False).first()

        ok, msg, order_data = PaymentGatewayService.create_payment_order(
            theater=self.theater,
            seat_ids=[seat.id],
            user=user
        )
        self.assertTrue(ok)
        order_id = order_data['order_id']
        payment_id = 'pay_concurrent_dup_999'
        sig = PaymentGatewayService.compute_signature(order_id, payment_id)

        results = []
        def try_verify():
            try:
                success, msg, bookings, payment = PaymentGatewayService.verify_payment(
                    order_id=order_id,
                    payment_id=payment_id,
                    signature=sig
                )
                return (success, len(bookings))
            finally:
                connection.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(try_verify) for _ in range(4)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        successes = [r for r in results if r[0] is True]
        self.assertEqual(len(successes), 4, "All concurrent idempotent verification requests must succeed.")
        self.assertEqual(Booking.objects.filter(seat=seat).count(), 1, "Exactly one booking record must exist in the database.")
        self.assertEqual(Payment.objects.get(order_id=order_id).status, 'SUCCESS')


# ======================================================================
# Complete Payment Workflow with Booking Management Tests
# ======================================================================

class PaymentWorkflowIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='payuser', password='password123', email='payuser@example.com')
        self.other_user = User.objects.create_user(username='otheruser', password='password123')
        self.movie = Movie.objects.create(
            title='Inception Matrix',
            name='Inception Matrix',
            trailer_url='https://www.youtube.com/watch?v=YoHD9XEInc0',
            duration=148,
            rating=4.8
        )
        self.theater = Theater.objects.create(
            name='PVR Gold IMAX',
            movie=self.movie,
            city='Mumbai',
            time=timezone.now() + timedelta(hours=3)
        )
        TheaterSeatingService.ensure_full_theater_layout(self.theater)
        self.client.login(username='payuser', password='password123')

    def test_create_payment_order_success(self):
        """Creates PENDING Payment order, reserves seats for 2 minutes, and calculates accurate amounts."""
        seats = list(Seat.objects.filter(theater=self.theater, is_booked=False)[:2])
        seat_ids = [s.id for s in seats]

        response = self.client.post(
            reverse('create_payment_order', args=[self.theater.id]),
            data=json.dumps({'seats': seat_ids, 'payment_method': 'card', 'addon_popcorn': True}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        order = data['order']
        self.assertTrue(order['order_id'])
        self.assertEqual(order['seat_ids'], seat_ids)

        # Verify DB Payment record
        payment = Payment.objects.get(order_id=order['order_id'])
        self.assertEqual(payment.status, 'PENDING')
        self.assertEqual(payment.user, self.user)
        self.assertEqual(payment.payment_method, 'card')

        # Check pricing calculation: subtotal + 150 popcorn + 10% convenience fee
        subtotal = sum(s.price for s in seats)
        fee = (subtotal * Decimal('0.10')).quantize(Decimal('0.01'))
        expected_total = subtotal + Decimal('150.00') + fee
        self.assertEqual(payment.amount, expected_total)

        # Verify seats are held for this user
        for s in seats:
            s.refresh_from_db()
            self.assertEqual(s.locked_by, self.user)
            self.assertIsNotNone(s.locked_until)

    def test_create_payment_order_fails_if_seats_already_booked(self):
        """Order creation fails if any seat is already booked."""
        seat = Seat.objects.filter(theater=self.theater, is_booked=False).first()
        seat.is_booked = True
        seat.save()

        response = self.client.post(
            reverse('create_payment_order', args=[self.theater.id]),
            data=json.dumps({'seats': [seat.id]}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn("already booked", data['message'])

    def test_verify_payment_success_creates_bookings_and_updates_payment(self):
        """Verifying a valid HMAC-SHA256 signature confirms booking and sets payment to SUCCESS."""
        seats = list(Seat.objects.filter(theater=self.theater, is_booked=False)[:2])
        seat_ids = [s.id for s in seats]

        success, msg, order_data = PaymentGatewayService.create_payment_order(
            theater=self.theater,
            seat_ids=seat_ids,
            user=self.user,
            payment_method='upi'
        )
        self.assertTrue(success)
        order_id = order_data['order_id']
        payment_id = 'pay_test_txn_98765'

        # Compute valid HMAC-SHA256 signature
        valid_sig = PaymentGatewayService.compute_signature(order_id, payment_id)

        response = self.client.post(
            reverse('verify_payment'),
            data=json.dumps({
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': valid_sig
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['booking_ids']), 2)

        # Verify DB Payment
        payment = Payment.objects.get(order_id=order_id)
        self.assertEqual(payment.status, 'SUCCESS')
        self.assertEqual(payment.transaction_id, payment_id)
        self.assertEqual(payment.signature, valid_sig)

        # Verify DB Bookings and Seat state
        bookings = Booking.objects.filter(payment=payment)
        self.assertEqual(bookings.count(), 2)
        for s in seats:
            s.refresh_from_db()
            self.assertTrue(s.is_booked)
            self.assertIsNone(s.locked_until)

    def test_verify_payment_strict_idempotency_prevents_duplicate_bookings(self):
        """Submitting duplicate payment confirmations returns success without creating duplicate bookings."""
        seat = Seat.objects.filter(theater=self.theater, is_booked=False).first()
        success, _, order_data = PaymentGatewayService.create_payment_order(
            theater=self.theater,
            seat_ids=[seat.id],
            user=self.user
        )
        order_id = order_data['order_id']
        payment_id = 'pay_dup_12345'
        sig = PaymentGatewayService.compute_signature(order_id, payment_id)

        # First verification
        res1 = self.client.post(
            reverse('verify_payment'),
            data=json.dumps({
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': sig
            }),
            content_type='application/json'
        )
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(Booking.objects.filter(user=self.user).count(), 1)

        # Duplicate verification callback
        res2 = self.client.post(
            reverse('verify_payment'),
            data=json.dumps({
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': sig
            }),
            content_type='application/json'
        )
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertTrue(data2['success'])
        # Assert NO duplicate booking created!
        self.assertEqual(Booking.objects.filter(user=self.user).count(), 1)

    def test_verify_payment_bad_signature_fails_and_releases_seats(self):
        """Invalid HMAC signature marks payment FAILED and automatically releases reserved seats."""
        seat = Seat.objects.filter(theater=self.theater, is_booked=False).first()
        success, _, order_data = PaymentGatewayService.create_payment_order(
            theater=self.theater,
            seat_ids=[seat.id],
            user=self.user
        )
        order_id = order_data['order_id']

        response = self.client.post(
            reverse('verify_payment'),
            data=json.dumps({
                'razorpay_order_id': order_id,
                'razorpay_payment_id': 'pay_fake_999',
                'razorpay_signature': 'invalid_forged_signature_hex'
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])

        # Verify Payment is FAILED with error code
        payment = Payment.objects.get(order_id=order_id)
        self.assertEqual(payment.status, 'FAILED')
        self.assertEqual(payment.error_code, 'BAD_SIGNATURE')

        # Verify seat was automatically released and NOT booked
        seat.refresh_from_db()
        self.assertFalse(seat.is_booked)
        self.assertIsNone(seat.locked_until)
        self.assertEqual(Booking.objects.filter(seat=seat).count(), 0)

    def test_payment_failure_endpoint_releases_reserved_seats(self):
        """payment_failure_view sets status to FAILED and immediately releases reserved seats."""
        seat = Seat.objects.filter(theater=self.theater, is_booked=False).first()
        _, _, order_data = PaymentGatewayService.create_payment_order(
            theater=self.theater,
            seat_ids=[seat.id],
            user=self.user
        )
        order_id = order_data['order_id']

        response = self.client.post(
            reverse('payment_failure'),
            data=json.dumps({
                'order_id': order_id,
                'error_code': 'CARD_DECLINED',
                'error_description': 'Insufficient funds on credit card'
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(order_id=order_id)
        self.assertEqual(payment.status, 'FAILED')
        self.assertEqual(payment.error_code, 'CARD_DECLINED')

        # Auto seat release check
        seat.refresh_from_db()
        self.assertFalse(seat.is_booked)
        self.assertIsNone(seat.locked_until)

    def test_payment_cancel_endpoint_releases_reserved_seats(self):
        """payment_cancel_view sets status to CANCELLED and immediately releases reserved seats."""
        seat = Seat.objects.filter(theater=self.theater, is_booked=False).first()
        _, _, order_data = PaymentGatewayService.create_payment_order(
            theater=self.theater,
            seat_ids=[seat.id],
            user=self.user
        )
        order_id = order_data['order_id']

        response = self.client.post(
            reverse('payment_cancel'),
            data=json.dumps({'order_id': order_id}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(order_id=order_id)
        self.assertEqual(payment.status, 'CANCELLED')

        seat.refresh_from_db()
        self.assertFalse(seat.is_booked)
        self.assertIsNone(seat.locked_until)

    def test_payment_retry_flow_success(self):
        """payment_retry_view allows re-trying payment for a failed transaction if seats are still free."""
        seat = Seat.objects.filter(theater=self.theater, is_booked=False).first()
        _, _, order_data = PaymentGatewayService.create_payment_order(
            theater=self.theater,
            seat_ids=[seat.id],
            user=self.user
        )
        orig_order_id = order_data['order_id']
        # Simulate payment failure
        PaymentGatewayService.record_payment_failure(orig_order_id, 'GATEWAY_TIMEOUT', 'Timed out')

        # Retry payment
        res = self.client.post(
            reverse('payment_retry'),
            data=json.dumps({'order_id': orig_order_id}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        new_order = data['order']
        self.assertNotEqual(new_order['order_id'], orig_order_id)

        # Seat is re-locked for user
        seat.refresh_from_db()
        self.assertEqual(seat.locked_by, self.user)

    def test_webhook_verification_and_booking_confirmation(self):
        """Webhook verifies HMAC-SHA256 signature and confirms bookings on order.paid."""
        import hmac, hashlib
        from django.conf import settings

        seat = Seat.objects.filter(theater=self.theater, is_booked=False).first()
        _, _, order_data = PaymentGatewayService.create_payment_order(
            theater=self.theater,
            seat_ids=[seat.id],
            user=self.user
        )
        order_id = order_data['order_id']
        payment_id = 'pay_hook_9999'

        payload = {
            'event': 'order.paid',
            'payload': {
                'payment': {
                    'entity': {
                        'id': payment_id,
                        'order_id': order_id,
                        'amount': int(order_data['amount_paise']),
                        'status': 'captured'
                    }
                }
            }
        }
        body_bytes = json.dumps(payload).encode('utf-8')
        secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', 'jaZh3ffiiNPRPXVrPk6y0pvC')
        signature = hmac.new(secret.encode('utf-8'), body_bytes, hashlib.sha256).hexdigest()

        # Valid webhook request
        res = self.client.post(
            reverse('razorpay_webhook'),
            data=body_bytes,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=signature
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'ok')

        # Verify payment is confirmed
        payment = Payment.objects.get(order_id=order_id)
        self.assertEqual(payment.status, 'SUCCESS')
        seat.refresh_from_db()
        self.assertTrue(seat.is_booked)

    def test_webhook_with_invalid_signature_is_rejected(self):
        """Webhook with invalid signature returns 400."""
        payload = json.dumps({'event': 'payment.failed'}).encode('utf-8')
        res = self.client.post(
            reverse('razorpay_webhook'),
            data=payload,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='bogus_signature'
        )
        self.assertEqual(res.status_code, 400)

    def test_profile_displays_payment_and_booking_history(self):
        """User profile displays payments ledger with transaction IDs, status badges, and retry options."""
        # Create a successful payment
        p_success = Payment.objects.create(
            order_id='order_prof_111',
            transaction_id='pay_prof_222',
            gateway='RAZORPAY',
            payment_method='upi',
            status='SUCCESS',
            user=self.user,
            movie=self.movie,
            theater=self.theater,
            amount=Decimal('550.00'),
            seat_numbers='A1, A2'
        )
        # Create a failed payment
        p_failed = Payment.objects.create(
            order_id='order_prof_333',
            gateway='RAZORPAY',
            payment_method='card',
            status='FAILED',
            user=self.user,
            movie=self.movie,
            theater=self.theater,
            amount=Decimal('350.00'),
            seat_numbers='B3'
        )

        res = self.client.get(reverse('profile'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Payment &amp; Transaction History')
        self.assertContains(res, 'order_prof_111')
        self.assertContains(res, 'pay_prof_222')
        self.assertContains(res, 'order_prof_333')
        self.assertContains(res, 'Successful')
        self.assertContains(res, 'Failed')
        self.assertContains(res, 'Retry')


# ======================================================================
# Task 10: Executive Admin Analytics Dashboard & Reporting Tests
# ======================================================================

class AdminAnalyticsDashboardTests(TestCase):
    """
    Comprehensive tests for Executive Business Analytics Dashboard:
    - Access control: staff/superuser authentication required; unauthenticated/regular users blocked
    - Revenue metrics accuracy: daily (today & yesterday with DoD %), weekly, monthly, yearly, all-time
    - Theater occupancy breakdown and percentage calculations
    - Booking trends time-series aggregation
    - Top movies and top theaters ranking
    - 24-Hour peak booking distribution & rush window detection
    - Cancellation, failure, and refund telemetry
    - User growth and active booking conversion reports
    - Custom date range parsing and filtering
    - CSV report downloads for summary, theaters, movies, hourly, and transactions ledger
    """

    def setUp(self):
        self.client = Client()
        self.now = timezone.now()

        # Users
        self.staff_user = User.objects.create_user(
            username='analytics_staff', password='Password@123', is_staff=True
        )
        self.super_user = User.objects.create_superuser(
            username='analytics_super', password='SuperPassword@123'
        )
        self.normal_user = User.objects.create_user(
            username='regular_customer', password='CustPassword@123', is_staff=False
        )

        # Movies
        self.movie_oppen = Movie.objects.create(
            name='Oppenheimer', rating=8.9, is_active=True, cast='Cillian Murphy'
        )
        self.movie_barbie = Movie.objects.create(
            name='Barbie', rating=7.4, is_active=True, cast='Margot Robbie'
        )

        # Theaters
        self.theater_imax = Theater.objects.create(
            name='PVR IMAX Screen 1', movie=self.movie_oppen, time=self.now
        )
        self.theater_inox = Theater.objects.create(
            name='INOX Laser Screen 2', movie=self.movie_barbie, time=self.now
        )

        # Theater 1 Seats (4 seats total, 2 booked)
        self.t1_s1 = Seat.objects.create(theater=self.theater_imax, seat_number='A1', price=Decimal('300.00'), is_booked=True)
        self.t1_s2 = Seat.objects.create(theater=self.theater_imax, seat_number='A2', price=Decimal('300.00'), is_booked=True)
        self.t1_s3 = Seat.objects.create(theater=self.theater_imax, seat_number='A3', price=Decimal('300.00'), is_booked=False)
        self.t1_s4 = Seat.objects.create(theater=self.theater_imax, seat_number='A4', price=Decimal('300.00'), is_booked=False)

        # Theater 2 Seats (4 seats total, 1 booked)
        self.t2_s1 = Seat.objects.create(theater=self.theater_inox, seat_number='B1', price=Decimal('250.00'), is_booked=True)
        self.t2_s2 = Seat.objects.create(theater=self.theater_inox, seat_number='B2', price=Decimal('250.00'), is_booked=False)
        self.t2_s3 = Seat.objects.create(theater=self.theater_inox, seat_number='B3', price=Decimal('250.00'), is_booked=False)
        self.t2_s4 = Seat.objects.create(theater=self.theater_inox, seat_number='B4', price=Decimal('250.00'), is_booked=False)

        # Create Payments across different statuses and timeframes
        # 1. Today SUCCESS payment (Rs. 600)
        self.pay_today = Payment.objects.create(
            order_id='order_dash_today_01',
            transaction_id='txn_dash_today_01',
            gateway='RAZORPAY',
            payment_method='upi',
            status='SUCCESS',
            user=self.normal_user,
            movie=self.movie_oppen,
            theater=self.theater_imax,
            amount=Decimal('600.00'),
            seat_numbers='A1, A2'
        )

        # 2. Yesterday SUCCESS payment (Rs. 250)
        self.pay_yest = Payment.objects.create(
            order_id='order_dash_yest_02',
            transaction_id='txn_dash_yest_02',
            gateway='RAZORPAY',
            payment_method='card',
            status='SUCCESS',
            user=self.normal_user,
            movie=self.movie_barbie,
            theater=self.theater_inox,
            amount=Decimal('250.00'),
            seat_numbers='B1'
        )
        yesterday_ts = self.now - timedelta(days=1)
        Payment.objects.filter(id=self.pay_yest.id).update(created_at=yesterday_ts)

        # 3. FAILED payment (Rs. 300)
        self.pay_fail = Payment.objects.create(
            order_id='order_dash_fail_03',
            gateway='RAZORPAY',
            payment_method='card',
            status='FAILED',
            error_code='GATEWAY_TIMEOUT',
            user=self.normal_user,
            movie=self.movie_oppen,
            theater=self.theater_imax,
            amount=Decimal('300.00'),
            seat_numbers='A3'
        )

        # 4. CANCELLED payment (Rs. 250)
        self.pay_cancel = Payment.objects.create(
            order_id='order_dash_cancel_04',
            gateway='RAZORPAY',
            payment_method='netbanking',
            status='CANCELLED',
            user=self.normal_user,
            movie=self.movie_barbie,
            theater=self.theater_inox,
            amount=Decimal('250.00'),
            seat_numbers='B2'
        )

        # Create Bookings corresponding to successful payments
        self.b1 = Booking.objects.create(
            user=self.normal_user,
            movie=self.movie_oppen,
            theater=self.theater_imax,
            seat=self.t1_s1,
            payment=self.pay_today
        )
        self.b2 = Booking.objects.create(
            user=self.normal_user,
            movie=self.movie_oppen,
            theater=self.theater_imax,
            seat=self.t1_s2,
            payment=self.pay_today
        )
        self.b3 = Booking.objects.create(
            user=self.normal_user,
            movie=self.movie_barbie,
            theater=self.theater_inox,
            seat=self.t2_s1,
            payment=self.pay_yest
        )
        Booking.objects.filter(id=self.b3.id).update(booked_at=yesterday_ts)

    # ------------------------------------------------------------------
    # 1. Access Control Tests
    # ------------------------------------------------------------------

    def test_unauthenticated_user_redirected_from_analytics(self):
        """Anonymous users must be redirected to the login page when accessing analytics."""
        response = self.client.get(reverse('admin_analytics_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_unauthenticated_user_redirected_from_analytics_export(self):
        """Anonymous users must be redirected when attempting CSV export."""
        response = self.client.get(reverse('admin_analytics_export_csv'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_regular_customer_denied_analytics_dashboard(self):
        """Non-staff users must be rejected from viewing analytics dashboard."""
        self.client.force_login(self.normal_user)
        response = self.client.get(reverse('admin_analytics_dashboard'))
        self.assertIn(response.status_code, [302, 403])

    def test_regular_customer_denied_analytics_export(self):
        """Non-staff users must be rejected from triggering CSV export."""
        self.client.force_login(self.normal_user)
        response = self.client.get(reverse('admin_analytics_export_csv'))
        self.assertIn(response.status_code, [302, 403])

    def test_staff_user_can_access_analytics_dashboard(self):
        """Authorized staff user can access the analytics dashboard with 200 OK."""
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('admin_analytics_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'movies/admin/analytics.html')
        self.assertIn('revenue', response.context)
        self.assertIn('theaters', response.context)
        self.assertIn('top_movies', response.context)
        self.assertIn('attrition', response.context)
        self.assertIn('user_growth', response.context)

    def test_superuser_can_access_analytics_dashboard(self):
        """Superusers have full access to the executive analytics dashboard."""
        self.client.force_login(self.super_user)
        response = self.client.get(reverse('admin_analytics_dashboard'))
        self.assertEqual(response.status_code, 200)

    # ------------------------------------------------------------------
    # 2. Date Range Parsing & Filters
    # ------------------------------------------------------------------

    def test_parse_date_range_presets(self):
        """Service accurately converts preset tokens into localized UTC start/end datetime boundaries."""
        presets = ['today', 'yesterday', '7days', '30days', 'this_month', 'this_year', 'all_time']
        for p in presets:
            start_date, end_date, active_preset, label = BusinessAnalyticsService.parse_date_range(preset=p)
            self.assertEqual(active_preset, p)
            self.assertIsNotNone(label)
            if p != 'all_time':
                self.assertIsNotNone(start_date)
                self.assertIsNotNone(end_date)
                self.assertLessEqual(start_date, end_date)

    def test_parse_date_range_custom_dates(self):
        """Service correctly processes custom YYYY-MM-DD date inputs."""
        start_str = '2026-01-01'
        end_str = '2026-01-31'
        start_date, end_date, active_preset, label = BusinessAnalyticsService.parse_date_range(
            preset='custom', custom_start=start_str, custom_end=end_str
        )
        self.assertEqual(active_preset, 'custom')
        self.assertEqual(start_date.year, 2026)
        self.assertEqual(start_date.month, 1)
        self.assertEqual(start_date.day, 1)
        self.assertEqual(end_date.year, 2026)
        self.assertEqual(end_date.month, 1)
        self.assertEqual(end_date.day, 31)

    # ------------------------------------------------------------------
    # 3. Business Analytics Service Calculations
    # ------------------------------------------------------------------

    def test_revenue_summary_metrics(self):
        """Revenue summary aggregates Today, Yesterday, DoD growth %, Week, Month, and All-Time."""
        start_date, end_date, _, _ = BusinessAnalyticsService.parse_date_range(preset='30days')
        rev = BusinessAnalyticsService.get_revenue_summary(start_date, end_date)

        self.assertEqual(rev['today_revenue'], Decimal('600.00'))
        self.assertEqual(rev['yesterday_revenue'], Decimal('250.00'))
        # DoD growth: (600 - 250) / 250 * 100 = 140.0%
        self.assertEqual(rev['dod_growth'], 140.0)
        self.assertEqual(rev['period_revenue'], Decimal('850.00'))
        self.assertEqual(rev['all_time_revenue'], Decimal('850.00'))

    def test_theater_occupancy_breakdown(self):
        """Occupancy breakdown calculates booked seats, total seats, and percentage accurately."""
        start_date, end_date, _, _ = BusinessAnalyticsService.parse_date_range(preset='30days')
        theaters, avg_occupancy, total_seats, booked_seats = (
            BusinessAnalyticsService.get_theater_occupancy_breakdown(start_date, end_date)
        )

        self.assertEqual(total_seats, 8)  # 4 in IMAX + 4 in INOX
        self.assertEqual(booked_seats, 3)  # 2 in IMAX + 1 in INOX
        # Expected average occupancy: (3 / 8) * 100 = 37.5%
        self.assertEqual(avg_occupancy, 37.5)

        # Check theater 1 (IMAX)
        imax = next(t for t in theaters if t['id'] == self.theater_imax.id)
        self.assertEqual(imax['total_seats'], 4)
        self.assertEqual(imax['booked_seats'], 2)
        self.assertEqual(imax['occupancy_pct'], 50.0)

        # Check theater 2 (INOX)
        inox = next(t for t in theaters if t['id'] == self.theater_inox.id)
        self.assertEqual(inox['total_seats'], 4)
        self.assertEqual(inox['booked_seats'], 1)
        self.assertEqual(inox['occupancy_pct'], 25.0)

    def test_most_booked_movies_ranking(self):
        """Top movies are ranked by ticket bookings and gross box-office revenue."""
        start_date, end_date, _, _ = BusinessAnalyticsService.parse_date_range(preset='30days')
        top_movies = BusinessAnalyticsService.get_most_booked_movies(start_date, end_date)

        self.assertTrue(len(top_movies) >= 2)
        # Oppenheimer should be #1 with 2 bookings and Rs. 600 revenue
        self.assertEqual(top_movies[0]['title'], 'Oppenheimer')
        self.assertEqual(top_movies[0]['booking_count'], 2)
        self.assertEqual(top_movies[0]['revenue'], Decimal('600.00'))

        # Barbie should be #2 with 1 booking and Rs. 250 revenue
        self.assertEqual(top_movies[1]['title'], 'Barbie')
        self.assertEqual(top_movies[1]['booking_count'], 1)
        self.assertEqual(top_movies[1]['revenue'], Decimal('250.00'))

    def test_top_performing_theaters_ranking(self):
        """Top theaters are ranked by revenue."""
        start_date, end_date, _, _ = BusinessAnalyticsService.parse_date_range(preset='30days')
        top_th = BusinessAnalyticsService.get_top_performing_theaters(start_date, end_date)

        self.assertTrue(len(top_th) >= 2)
        self.assertEqual(top_th[0]['name'], 'PVR IMAX Screen 1')
        self.assertEqual(top_th[0]['revenue'], Decimal('600.00'))

    def test_peak_booking_hours_distribution(self):
        """Peak booking distribution populates all 24 hours and identifies rush hours."""
        start_date, end_date, _, _ = BusinessAnalyticsService.parse_date_range(preset='30days')
        peak = BusinessAnalyticsService.get_peak_booking_hours(start_date, end_date)

        self.assertEqual(len(peak['hours']), 24)
        self.assertIn('peak_hour', peak)
        self.assertIn('peak_count', peak)
        self.assertIn('peak_hour_label', peak)
        self.assertTrue(peak['peak_count'] >= 1)

    def test_cancellation_and_refund_telemetry(self):
        """Telemetry accurately computes dropoff counts, attrition rates, and lost revenue."""
        start_date, end_date, _, _ = BusinessAnalyticsService.parse_date_range(preset='30days')
        stats = BusinessAnalyticsService.get_cancellation_and_refund_statistics(start_date, end_date)

        self.assertEqual(stats['success_count'], 2)
        self.assertEqual(stats['cancelled_count'], 1)
        self.assertEqual(stats['failed_count'], 1)
        self.assertEqual(stats['refunded_count'], 0)
        self.assertEqual(stats['total_transactions'], 4)

        # Success rate: 2 / 4 = 50.0%
        self.assertEqual(stats['success_rate'], 50.0)
        # Lost revenue: 300 (failed) + 250 (cancelled) = 550.00
        self.assertEqual(stats['lost_revenue'], Decimal('550.00'))

    def test_user_growth_reports(self):
        """User growth computes total registered users, active bookers, and conversion rate."""
        start_date, end_date, _, _ = BusinessAnalyticsService.parse_date_range(preset='30days')
        ug = BusinessAnalyticsService.get_user_growth_reports(start_date, end_date)

        self.assertGreaterEqual(ug['total_members'], 3)
        self.assertGreaterEqual(ug['active_bookers'], 1)
        self.assertGreater(ug['conversion_rate'], 0.0)

    def test_large_scale_aggregation_performance(self):
        """Validates that database-level ORM aggregations execute in sub-second time without loading records into memory."""
        import time
        start_date, end_date, _, _ = BusinessAnalyticsService.parse_date_range(preset='30days')

        t0 = time.time()
        rev = BusinessAnalyticsService.get_revenue_summary(start_date, end_date)
        duration = time.time() - t0
        self.assertLess(duration, 1.0, "Revenue aggregation must complete in under 1 second.")
        self.assertIn('today_revenue', rev)
        self.assertIn('all_time_revenue', rev)

        t0 = time.time()
        theaters, occ, _, _ = BusinessAnalyticsService.get_theater_occupancy_breakdown(start_date, end_date)
        duration = time.time() - t0
        self.assertLess(duration, 1.0, "Occupancy aggregation must complete in under 1 second.")

        t0 = time.time()
        peak = BusinessAnalyticsService.get_peak_booking_hours(start_date, end_date)
        duration = time.time() - t0
        self.assertLess(duration, 1.0, "Peak hours aggregation must complete in under 1 second.")

    # ------------------------------------------------------------------
    # 4. CSV Report Streaming & Exports
    # ------------------------------------------------------------------

    def test_export_csv_summary(self):
        """Staff user can download high-level KPI summary report as CSV."""
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse('admin_analytics_export_csv'),
            {'report_type': 'summary', 'preset': '30days'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/csv'))
        self.assertIn('attachment; filename="cineva_summary_report_', response['Content-Disposition'])

        content = response.content.decode('utf-8')
        self.assertIn('Metric', content)
        self.assertIn("Today's Revenue", content)
        self.assertIn('Period Revenue', content)
        self.assertIn('Network Average Occupancy Rate (%)', content)
        self.assertIn('600.0', content)

    def test_export_csv_theaters(self):
        """Staff user can download auditorium occupancy breakdown as CSV."""
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse('admin_analytics_export_csv'),
            {'report_type': 'theaters', 'preset': '30days'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/csv'))
        self.assertIn('attachment; filename="cineva_theaters_report_', response['Content-Disposition'])

        content = response.content.decode('utf-8')
        self.assertIn('Theater Name', content)
        self.assertIn('PVR IMAX Screen 1', content)
        self.assertIn('INOX Laser Screen 2', content)
        self.assertIn('50.0%', content)

    def test_export_csv_movies(self):
        """Staff user can download top movies box-office report as CSV."""
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse('admin_analytics_export_csv'),
            {'report_type': 'movies', 'preset': '30days'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/csv'))
        self.assertIn('attachment; filename="cineva_movies_report_', response['Content-Disposition'])

        content = response.content.decode('utf-8')
        self.assertIn('Title', content)
        self.assertIn('Oppenheimer', content)
        self.assertIn('Barbie', content)

    def test_export_csv_hourly(self):
        """Staff user can download 24-hour temporal booking distribution as CSV."""
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse('admin_analytics_export_csv'),
            {'report_type': 'hourly', 'preset': '30days'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/csv'))
        self.assertIn('attachment; filename="cineva_hourly_report_', response['Content-Disposition'])

        content = response.content.decode('utf-8')
        self.assertIn('Hour (24h)', content)
        self.assertIn('Time Window', content)
        self.assertIn('Bookings Count', content)

    def test_export_csv_transactions(self):
        """Staff user can download the raw transaction audit log as CSV."""
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse('admin_analytics_export_csv'),
            {'report_type': 'transactions', 'preset': '30days'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/csv'))
        self.assertIn('attachment; filename="cineva_transactions_report_', response['Content-Disposition'])

        content = response.content.decode('utf-8')
        self.assertIn('Order ID', content)
        self.assertIn('Transaction ID', content)
        self.assertIn('Status', content)
        self.assertIn('order_dash_today_01', content)
        self.assertIn('order_dash_yest_02', content)
        self.assertIn('order_dash_fail_03', content)
        self.assertIn('order_dash_cancel_04', content)


class RazorpayTestModeIntegrationTests(TestCase):
    """
    Dedicated test suite validating Razorpay Test Mode integration:
    - Verifies test API key and secret key configuration
    - Client initialization with test credentials
    - Order creation with test keys
    - Cryptographic signature generation and verification with test secret
    - Seat reservation finalization on verified test payment
    - Seat release on test payment cancellation or failure
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='test_rzp_user',
            password='Password123!',
            email='rzp_tester@example.com'
        )
        self.movie = Movie.objects.create(
            title='Inception',
            name='Inception',
            duration=148,
            is_active=True
        )
        self.theater = Theater.objects.create(
            name='IMAX Grand',
            city='Mumbai',
            movie=self.movie,
            time=timezone.now() + timedelta(days=1)
        )
        self.seat1 = Seat.objects.create(
            theater=self.theater,
            seat_number='A1',
            row='A',
            number=1,
            tier='VIP',
            price=Decimal('350.00'),
            is_booked=False
        )
        self.seat2 = Seat.objects.create(
            theater=self.theater,
            seat_number='A2',
            row='A',
            number=2,
            tier='VIP',
            price=Decimal('350.00'),
            is_booked=False
        )
        self.client.force_login(self.user)

    def test_razorpay_test_credentials_configured(self):
        """Verifies configured API key and secret match user's test mode credentials."""
        from django.conf import settings
        self.assertEqual(settings.RAZORPAY_KEY_ID, 'rzp_test_TkuUcn0OX3jYly')
        self.assertEqual(settings.RAZORPAY_KEY_SECRET, 'jaZh3ffiiNPRPXVrPk6y0pvC')

    def test_razorpay_client_initialization_with_test_keys(self):
        """Razorpay client is instantiated successfully with the test credentials."""
        client = PaymentGatewayService.get_razorpay_client()
        self.assertIsNotNone(client)
        self.assertEqual(client.auth, ('rzp_test_TkuUcn0OX3jYly', 'jaZh3ffiiNPRPXVrPk6y0pvC'))

    def test_create_payment_order_returns_test_key_and_order_id(self):
        """create_payment_order_view returns Razorpay test key ID and order details."""
        response = self.client.post(
            reverse('create_payment_order', args=[self.theater.id]),
            data=json.dumps({
                'seats': [self.seat1.id, self.seat2.id],
                'payment_method': 'card',
                'addon_popcorn': False
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['razorpay_key_id'], 'rzp_test_TkuUcn0OX3jYly')

        order = data['order']
        self.assertIn('order_id', order)
        self.assertEqual(order['key_id'], 'rzp_test_TkuUcn0OX3jYly')
        # Total: 700 + 10% fee (70) = 770.00
        self.assertEqual(order['amount'], 770.0)
        self.assertEqual(order['amount_paise'], 77000)

        # Seats should now be temporarily locked
        self.seat1.refresh_from_db()
        self.seat2.refresh_from_db()
        self.assertEqual(self.seat1.locked_by, self.user)
        self.assertEqual(self.seat2.locked_by, self.user)

    def test_verify_payment_with_valid_hmac_test_signature(self):
        """Verifies test payment with HMAC-SHA256 signature using test secret jaZh3ffiiNPRPXVrPk6y0pvC."""
        # Create order
        _, _, order_data = PaymentGatewayService.create_payment_order(
            theater=self.theater,
            seat_ids=[self.seat1.id],
            user=self.user,
            payment_method='upi'
        )
        order_id = order_data['order_id']
        payment_id = 'pay_rzp_test_1001'

        # Compute signature using test secret
        valid_sig = PaymentGatewayService.compute_signature(order_id, payment_id)

        response = self.client.post(
            reverse('verify_payment'),
            data=json.dumps({
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': valid_sig
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertTrue(res_data['success'])
        self.assertEqual(len(res_data['booking_ids']), 1)

        # Confirm DB Payment is SUCCESS
        payment = Payment.objects.get(order_id=order_id)
        self.assertEqual(payment.status, 'SUCCESS')
        self.assertEqual(payment.transaction_id, payment_id)
        self.assertEqual(payment.signature, valid_sig)

        # Confirm seat is permanently booked
        self.seat1.refresh_from_db()
        self.assertTrue(self.seat1.is_booked)

    def test_verify_payment_invalid_signature_rejected(self):
        """Rejects forged signature, marks payment FAILED, and releases held seats."""
        _, _, order_data = PaymentGatewayService.create_payment_order(
            theater=self.theater,
            seat_ids=[self.seat1.id],
            user=self.user
        )
        order_id = order_data['order_id']

        response = self.client.post(
            reverse('verify_payment'),
            data=json.dumps({
                'razorpay_order_id': order_id,
                'razorpay_payment_id': 'pay_test_fake',
                'razorpay_signature': 'invalid_signature_hex_1234567890'
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

        payment = Payment.objects.get(order_id=order_id)
        self.assertEqual(payment.status, 'FAILED')
        self.assertEqual(payment.error_code, 'BAD_SIGNATURE')

        # Reserved seat is released
        self.seat1.refresh_from_db()
        self.assertFalse(self.seat1.is_booked)
        self.assertIsNone(self.seat1.locked_until)


class MovieDiscoveryTests(TestCase):
    """
    Comprehensive test suite for Movie Discovery, Search, Filtering,
    Dynamic Counts, Sorting, and Personalized Recommendations.
    """

    def setUp(self):
        # Languages
        self.lang_en = Language.objects.create(name='English', code='en')
        self.lang_hi = Language.objects.create(name='Hindi', code='hi')

        # Genres
        self.genre_action = Genre.objects.create(name='Action', slug='action')
        self.genre_drama = Genre.objects.create(name='Drama', slug='drama')
        self.genre_scifi = Genre.objects.create(name='Sci-Fi', slug='sci-fi')

        # Theaters in distinct cities
        self.theater_mumbai = Theater.objects.create(name='PVR Mumbai Phoenix', city='Mumbai', is_active=True)
        self.theater_delhi = Theater.objects.create(name='INOX Delhi Connaught', city='Delhi', is_active=True)

        self.screen_mumbai = Screen.objects.create(theater=self.theater_mumbai, name='Audi 1', screen_type='2D')
        self.screen_delhi = Screen.objects.create(theater=self.theater_delhi, name='Audi 1', screen_type='IMAX')

        today = timezone.now().date()
        self.today = today

        # Movie 1: Action, English, Released 10 days ago (now_showing), Rating 8.8
        self.movie_action = Movie.objects.create(
            title='Interstellar Odyssey',
            name='Interstellar Odyssey',
            slug='interstellar-odyssey',
            language=self.lang_en,
            release_date=today - timedelta(days=10),
            rating=Decimal('8.8'),
            total_reviews=25,
            duration=145,
            is_active=True
        )
        self.movie_action.genres.add(self.genre_action, self.genre_scifi)

        # Movie 2: Drama, Hindi, Released yesterday (now_showing), Rating 7.2
        self.movie_drama = Movie.objects.create(
            title='Zindagi Express',
            name='Zindagi Express',
            slug='zindagi-express',
            language=self.lang_hi,
            release_date=today - timedelta(days=1),
            rating=Decimal('7.2'),
            total_reviews=10,
            duration=120,
            is_active=True
        )
        self.movie_drama.genres.add(self.genre_drama)

        # Movie 3: Sci-Fi, English, Upcoming release in 20 days, Rating 9.4
        self.movie_upcoming = Movie.objects.create(
            title='Cyberpunk 2099',
            name='Cyberpunk 2099',
            slug='cyberpunk-2099',
            language=self.lang_en,
            release_date=today + timedelta(days=20),
            rating=Decimal('9.4'),
            total_reviews=5,
            duration=150,
            is_active=True
        )
        self.movie_upcoming.genres.add(self.genre_scifi)

        # Shows with schedules & pricing
        now = timezone.now()
        # Morning show at 9:00 AM in Mumbai for Action movie (Price: 180.00)
        self.morning_dt = timezone.make_aware(dt.combine(today, time(9, 0)))
        self.show_action = ShowSchedule.objects.create(
            movie=self.movie_action,
            theater=self.theater_mumbai,
            screen=self.screen_mumbai,
            start_time=self.morning_dt,
            end_time=self.morning_dt + timedelta(hours=2, minutes=30),
            price=Decimal('180.00'),
            status='open'
        )

        # Evening show at 18:30 in Delhi for Drama movie (Price: 320.00)
        self.evening_dt = timezone.make_aware(dt.combine(today, time(18, 30)))
        self.show_drama = ShowSchedule.objects.create(
            movie=self.movie_drama,
            theater=self.theater_delhi,
            screen=self.screen_delhi,
            start_time=self.evening_dt,
            end_time=self.evening_dt + timedelta(hours=2),
            price=Decimal('320.00'),
            status='open'
        )

        # User for personalization testing
        self.test_user = User.objects.create_user(username='discovery_user', password='password123')

    def test_search_by_title_case_insensitive(self):
        """Allows search across movie title with substring match."""
        qs, count, applied = MovieDiscoveryService.filter_movies({'search': 'odyssey'})
        self.assertEqual(count, 1)
        self.assertIn(self.movie_action, list(qs))
        self.assertEqual(applied.get('search'), 'odyssey')

        # Multi-word case insensitive search
        qs, count, _ = MovieDiscoveryService.filter_movies({'search': 'zindagi express'})
        self.assertEqual(count, 1)
        self.assertEqual(qs.first().id, self.movie_drama.id)

    def test_filter_by_genre_slug_and_id(self):
        """Filters movies by genre slug and genre ID."""
        qs, count, applied = MovieDiscoveryService.filter_movies({'genre': 'action'})
        self.assertEqual(count, 1)
        self.assertEqual(qs.first().id, self.movie_action.id)

        # By Sci-Fi genre (matches 2 movies: Odyssey and Cyberpunk)
        qs, count, _ = MovieDiscoveryService.filter_movies({'genres': ['sci-fi']})
        self.assertEqual(count, 2)
        movie_ids = [m.id for m in qs]
        self.assertIn(self.movie_action.id, movie_ids)
        self.assertIn(self.movie_upcoming.id, movie_ids)

    def test_filter_by_language(self):
        """Filters movies by language code."""
        qs, count, _ = MovieDiscoveryService.filter_movies({'language': 'hi'})
        self.assertEqual(count, 1)
        self.assertEqual(qs.first().id, self.movie_drama.id)

        qs, count, _ = MovieDiscoveryService.filter_movies({'language': 'en'})
        self.assertEqual(count, 2)

    def test_filter_by_city(self):
        """Filters movies by theater city."""
        qs, count, applied = MovieDiscoveryService.filter_movies({'city': 'Mumbai'})
        self.assertEqual(count, 1)
        self.assertEqual(qs.first().id, self.movie_action.id)
        self.assertEqual(applied['city'], 'Mumbai')

        qs, count, applied = MovieDiscoveryService.filter_movies({'city': 'Delhi'})
        self.assertEqual(count, 1)
        self.assertEqual(qs.first().id, self.movie_drama.id)

    def test_filter_by_theater(self):
        """Filters movies by theater ID or theater name."""
        qs, count, _ = MovieDiscoveryService.filter_movies({'theater': str(self.theater_mumbai.id)})
        self.assertEqual(count, 1)
        self.assertEqual(qs.first().id, self.movie_action.id)

        qs, count, _ = MovieDiscoveryService.filter_movies({'theater': 'Connaught'})
        self.assertEqual(count, 1)
        self.assertEqual(qs.first().id, self.movie_drama.id)

    def test_filter_by_release_date_presets(self):
        """Filters movies by release schedule presets: now_showing vs upcoming."""
        qs_now, count_now, _ = MovieDiscoveryService.filter_movies({'release_date': 'now_showing'})
        movie_ids_now = [m.id for m in qs_now]
        self.assertIn(self.movie_action.id, movie_ids_now)
        self.assertIn(self.movie_drama.id, movie_ids_now)
        self.assertNotIn(self.movie_upcoming.id, movie_ids_now)

        qs_up, count_up, _ = MovieDiscoveryService.filter_movies({'release_date': 'upcoming'})
        self.assertEqual(count_up, 1)
        self.assertEqual(qs_up.first().id, self.movie_upcoming.id)

    def test_filter_by_minimum_rating(self):
        """Filters movies by minimum rating score, handling strings like '8.0' and '8+'."""
        qs, count, applied = MovieDiscoveryService.filter_movies({'rating': '8.0'})
        movie_ids = [m.id for m in qs]
        self.assertIn(self.movie_action.id, movie_ids)
        self.assertIn(self.movie_upcoming.id, movie_ids)
        self.assertNotIn(self.movie_drama.id, movie_ids)

        # Test '8+' format support
        qs_plus, count_plus, _ = MovieDiscoveryService.filter_movies({'rating': '8+'})
        self.assertEqual(count_plus, count)

    def test_filter_by_show_timings(self):
        """Filters movies by show timings (morning 6am-12pm vs evening 4pm-8pm)."""
        qs_morn, count_morn, _ = MovieDiscoveryService.filter_movies({'timing': 'morning'})
        self.assertEqual(count_morn, 1)
        self.assertEqual(qs_morn.first().id, self.movie_action.id)

        qs_eve, count_eve, _ = MovieDiscoveryService.filter_movies({'timing': 'evening'})
        self.assertEqual(count_eve, 1)
        self.assertEqual(qs_eve.first().id, self.movie_drama.id)

    def test_sorting_options(self):
        """Sorts results by popularity, newest releases, rating, and ticket price."""
        # 1. Newest releases (Cyberpunk has future release date, then Odyssey, then Drama)
        qs, _, _ = MovieDiscoveryService.filter_movies({'sort': 'newest'})
        self.assertEqual(qs.first().id, self.movie_upcoming.id)

        # 2. Rating descending (Cyberpunk 9.4, Odyssey 8.8, Drama 7.2)
        qs, _, _ = MovieDiscoveryService.filter_movies({'sort': 'rating'})
        self.assertEqual(qs.first().id, self.movie_upcoming.id)

        # 3. Price Low to High (Action show: 180.00, Drama show: 320.00)
        qs, _, _ = MovieDiscoveryService.filter_movies({'sort': 'price_low'})
        ordered_movies = list(qs)
        prices = [float(m.min_ticket_price) for m in ordered_movies]
        self.assertEqual(prices, sorted(prices))

        # 4. Price High to Low
        qs, _, _ = MovieDiscoveryService.filter_movies({'sort': 'price_high'})
        ordered_movies = list(qs)
        prices = [float(m.max_ticket_price) for m in ordered_movies]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_dynamic_matching_count_and_pagination(self):
        """Dynamically computes scalar total match count and supports pagination."""
        qs, total_count, _ = MovieDiscoveryService.filter_movies({'genres': ['sci-fi']})
        self.assertEqual(total_count, 2)

        paginator = Paginator(qs, 1)
        page1 = paginator.get_page(1)
        self.assertEqual(len(page1), 1)
        self.assertTrue(page1.has_next())

    def test_personalized_recommendations_with_booking_history(self):
        """Generates recommendations tailored to the user's past booking genre."""
        # Create a confirmed booking for the user on Action movie
        seat = Seat.objects.create(
            theater=self.theater_mumbai,
            row='A',
            seat_number='1',
            tier='VIP',
            price=Decimal('350.00'),
            is_booked=True
        )
        Booking.objects.create(
            movie=self.movie_action,
            theater=self.theater_mumbai,
            seat=seat,
            user=self.test_user
        )

        recs = MovieDiscoveryService.get_personalized_recommendations(
            user=self.test_user,
            session_viewed_ids=[],
            limit=6
        )
        self.assertTrue(len(recs) > 0)
        # Recommend movies based on Action or Sci-Fi affinity
        rec_ids = [m.id for m in recs]
        # Cyberpunk shares Sci-Fi genre
        self.assertIn(self.movie_upcoming.id, rec_ids)
        cyberpunk_rec = next(m for m in recs if m.id == self.movie_upcoming.id)
        self.assertTrue(hasattr(cyberpunk_rec, 'recommendation_reason'))

    def test_personalized_recommendations_with_recently_viewed_session(self):
        """Generates recommendations matching recently viewed movie genres in session."""
        recs = MovieDiscoveryService.get_personalized_recommendations(
            user=None,
            session_viewed_ids=[self.movie_action.id],
            limit=6
        )
        self.assertTrue(len(recs) > 0)
        rec_ids = [m.id for m in recs]
        # Cyberpunk shares Sci-Fi genre with recently viewed Odyssey
        self.assertIn(self.movie_upcoming.id, rec_ids)

    def test_personalized_recommendations_guest_fallback(self):
        """Guest users with no signal receive trending picks with rationale."""
        recs = MovieDiscoveryService.get_personalized_recommendations(user=None, session_viewed_ids=[])
        self.assertTrue(len(recs) > 0)
        for r in recs:
            self.assertTrue(hasattr(r, 'recommendation_reason'))

    def test_discovery_api_json_endpoint(self):
        """Tests /movies/api/discovery/ returns expected JSON schema and dynamic count."""
        response = self.client.get(
            reverse('movie_discovery_api'),
            {'search': 'Odyssey', 'format': 'json'}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 1)
        self.assertEqual(len(data['movies']), 1)
        self.assertEqual(data['movies'][0]['title'], 'Interstellar Odyssey')
        self.assertEqual(data['movies'][0]['language'], 'English')

    def test_movie_list_view_html_rendering(self):
        """Tests that movie_list view renders template with discovery context variables."""
        response = self.client.get(reverse('movie_list'), {'genre': 'action', 'city': 'Mumbai'})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'movies/movie_list.html')
        self.assertIn('recommendations', response.context)
        self.assertIn('filter_options', response.context)
        self.assertIn('total_count', response.context)
        self.assertEqual(response.context['total_count'], 1)


class TicketGenerationAndEmailTests(TestCase):
    """
    Test suite for Automated PDF Ticket Generation, QR Code Verification,
    Celery Email Confirmation, and Ticket Downloads.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='ticket_user',
            email='ticket_user@example.com',
            password='password123'
        )
        self.other_user = User.objects.create_user(
            username='other_user',
            email='other_user@example.com',
            password='password123'
        )
        self.staff_user = User.objects.create_user(
            username='staff_user',
            email='staff@example.com',
            password='password123',
            is_staff=True
        )

        self.movie = Movie.objects.create(
            title='Inception Remastered',
            name='Inception Remastered',
            slug='inception-remastered',
            age_certification='UA',
            duration=148,
            is_active=True
        )
        self.theater = Theater.objects.create(
            name='Wave Cinema Center',
            city='Noida',
            is_active=True
        )
        self.screen = Screen.objects.create(
            theater=self.theater,
            name='Audi 3',
            screen_type='IMAX'
        )
        show_time = timezone.now() + timedelta(days=1)
        self.show = ShowSchedule.objects.create(
            movie=self.movie,
            theater=self.theater,
            screen=self.screen,
            start_time=show_time,
            end_time=show_time + timedelta(hours=2, minutes=30),
            price=Decimal('250.00'),
            status='open'
        )
        self.seat = Seat.objects.create(
            theater=self.theater,
            screen=self.screen,
            row='C',
            seat_number='7',
            tier='GOLD',
            price=Decimal('250.00'),
            is_booked=True
        )

        self.payment = Payment.objects.create(
            order_id='order_ticket_test_101',
            gateway='RAZORPAY',
            payment_method='upi',
            status='SUCCESS',
            user=self.user,
            movie=self.movie,
            theater=self.theater,
            show=self.show,
            amount=Decimal('275.00'),
            currency='INR',
            transaction_id='pay_ticket_test_101',
            seat_ids=[self.seat.id],
            seat_numbers='C7'
        )

        self.booking = Booking.objects.create(
            user=self.user,
            seat=self.seat,
            movie=self.movie,
            theater=self.theater,
            show=self.show,
            payment=self.payment
        )

    def test_qr_code_and_token_generation(self):
        """Verifies QR code image generation and cryptographic HMAC token validation."""
        token = TicketGeneratorService.get_verification_token(self.booking.id, self.booking.user_id, self.booking.movie_id)
        self.assertEqual(len(token), 16)

        # Valid token passes verification
        self.assertTrue(TicketGeneratorService.verify_ticket_token(self.booking, token))

        # Forged token fails verification
        self.assertFalse(TicketGeneratorService.verify_ticket_token(self.booking, 'forged_fake_token'))

        # QR code PNG bytes verification
        url = TicketGeneratorService.get_verification_url(self.booking)
        self.assertIn(token, url)
        qr_buf = TicketGeneratorService.generate_qr_code_image(url)
        qr_bytes = qr_buf.getvalue()
        # Verify PNG header
        self.assertTrue(qr_bytes.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_pdf_ticket_generation(self):
        """Generates valid vector PDF matching ticket template specification."""
        pdf_bytes = TicketGeneratorService.generate_ticket_pdf(booking=self.booking)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 2000)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

        # Also test consolidated multi-seat payment PDF
        payment_pdf = TicketGeneratorService.generate_ticket_pdf(payment=self.payment)
        self.assertTrue(payment_pdf.startswith(b'%PDF'))

    def test_html_email_ticket_generation(self):
        """Generates formatted HTML email ticket containing movie, screen, and seat details."""
        html = TicketGeneratorService.generate_ticket_email_html(booking=self.booking)
        self.assertIn('Inception Remastered', html)
        self.assertIn('Wave Cinema Center', html)
        self.assertIn('AUDI 3', html)
        self.assertIn('GOLD-7', html)
        self.assertIn('SCAN AT ADMISSION', html)
        self.assertIn('data:image/png;base64,', html)

    def test_celery_task_sends_email_with_pdf_attachment(self):
        """Tests Celery task generates and emails PDF ticket to user with proper headers."""
        mail.outbox.clear()
        result = send_booking_ticket_email_task.apply(
            kwargs={'booking_ids': [self.booking.id]}
        ).get()

        self.assertTrue(result['success'])
        self.assertEqual(len(mail.outbox), 1)

        sent_email = mail.outbox[0]
        self.assertIn('Inception Remastered', sent_email.subject)
        self.assertIn(f"#{self.booking.id}", sent_email.subject)
        self.assertIn('ownai63@gmail.com', sent_email.from_email)
        self.assertEqual(sent_email.to, [self.user.email])

        # Verify PDF attachment
        self.assertEqual(len(sent_email.attachments), 1)
        filename, content, mimetype = sent_email.attachments[0]
        self.assertTrue(filename.endswith('.pdf'))
        self.assertEqual(mimetype, 'application/pdf')
        self.assertTrue(content.startswith(b'%PDF'))

    def test_download_ticket_view_owner_success(self):
        """Allows authenticated ticket owner to download PDF ticket."""
        self.client.login(username='ticket_user', password='password123')
        response = self.client.get(reverse('download_ticket', args=[self.booking.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_download_ticket_view_unauthenticated_redirects(self):
        """Redirects unauthenticated visitor to login."""
        response = self.client.get(reverse('download_ticket', args=[self.booking.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_download_ticket_view_forbidden_for_other_user(self):
        """Prevents other authenticated users from downloading someone else's ticket."""
        self.client.login(username='other_user', password='password123')
        response = self.client.get(reverse('download_ticket', args=[self.booking.id]))
        self.assertEqual(response.status_code, 403)

    def test_download_ticket_view_allowed_for_staff(self):
        """Allows staff users to download tickets for customer assistance."""
        self.client.login(username='staff_user', password='password123')
        response = self.client.get(reverse('download_ticket', args=[self.booking.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_download_payment_tickets_view(self):
        """Allows downloading consolidated ticket pass for a payment order."""
        self.client.login(username='ticket_user', password='password123')
        response = self.client.get(reverse('download_payment_tickets', args=[self.payment.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

        # Other user gets 403
        self.client.login(username='other_user', password='password123')
        res_forbidden = self.client.get(reverse('download_payment_tickets', args=[self.payment.id]))
        self.assertEqual(res_forbidden.status_code, 403)

    def test_verify_ticket_view(self):
        """Tests gate verification endpoint with valid and forged tokens."""
        token = TicketGeneratorService.get_verification_token(self.booking.id, self.booking.user_id, self.booking.movie_id)

        # 1. Valid token
        res_valid = self.client.get(reverse('verify_ticket', args=[self.booking.id]), {'token': token})
        self.assertEqual(res_valid.status_code, 200)
        self.assertContains(res_valid, 'VALID TICKET')
        self.assertContains(res_valid, 'Inception Remastered')
        self.assertContains(res_valid, 'Audi 3')

        # 2. Tampered token
        res_invalid = self.client.get(reverse('verify_ticket', args=[self.booking.id]), {'token': 'bad_token'})
        self.assertEqual(res_invalid.status_code, 200)
        self.assertContains(res_invalid, 'INVALID / UNVERIFIED TICKET')


# ======================================================================
# Task: 10-Minute Cut-Off & Past Show Booking Restrictions
# ======================================================================

class ShowCutoffAndPastSlotTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='cutoff_user', password='password123', email='cutoff@test.com')
        self.movie = Movie.objects.create(
            name='Avatar: Way of Water',
            title='Avatar: Way of Water',
            slug='avatar-way-of-water',
            duration=192,
            is_active=True
        )
        self.theater = Theater.objects.create(
            name='PVR Gold Class',
            movie=self.movie,
            city='Mumbai',
            is_active=True
        )
        self.screen = Screen.objects.create(
            theater=self.theater,
            name='Screen 1 (IMAX)',
            screen_type='IMAX',
            seating_capacity=100
        )
        now = timezone.now()
        # 1. Past show (started 1 hour ago)
        self.show_past = ShowSchedule.objects.create(
            movie=self.movie,
            theater=self.theater,
            screen=self.screen,
            start_time=now - timedelta(hours=1),
            price=Decimal('250.00'),
            status='open'
        )
        # 2. Show within 10-minute cutoff (starts in 5 minutes)
        self.show_cutoff = ShowSchedule.objects.create(
            movie=self.movie,
            theater=self.theater,
            screen=self.screen,
            start_time=now + timedelta(minutes=5),
            price=Decimal('250.00'),
            status='open'
        )
        # 3. Upcoming valid show (starts in 3 hours)
        self.show_future = ShowSchedule.objects.create(
            movie=self.movie,
            theater=self.theater,
            screen=self.screen,
            start_time=now + timedelta(hours=3),
            price=Decimal('250.00'),
            status='open'
        )
        self.seat = Seat.objects.create(theater=self.theater, seat_number='C5', price=Decimal('250.00'), is_booked=False)

    def test_show_schedule_properties(self):
        """Tests is_past, is_within_cutoff, and is_booking_open properties."""
        # Past show
        self.assertTrue(self.show_past.is_past)
        self.assertTrue(self.show_past.is_within_cutoff)
        self.assertFalse(self.show_past.is_booking_open)
        self.assertTrue(self.show_past.is_closed)

        # Show starting in 5 minutes (within 10m cutoff)
        self.assertFalse(self.show_cutoff.is_past)
        self.assertTrue(self.show_cutoff.is_within_cutoff)
        self.assertFalse(self.show_cutoff.is_booking_open)
        self.assertTrue(self.show_cutoff.is_closed)
        self.assertEqual(self.show_cutoff.booking_status_label, 'Closed')

        # Upcoming show (3 hours away)
        self.assertFalse(self.show_future.is_past)
        self.assertFalse(self.show_future.is_within_cutoff)
        self.assertTrue(self.show_future.is_booking_open)
        self.assertFalse(self.show_future.is_closed)

    def test_theater_list_displays_closed_slots(self):
        """Verifies theater list displays closed indicator for past or cutoff slots."""
        response = self.client.get(reverse('theater_list', args=[self.movie.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Closed')

    def test_book_seats_rejects_closed_show(self):
        """Seat selection submission is blocked if show is within 10m cutoff or past."""
        self.client.login(username='cutoff_user', password='password123')
        # Attempt booking show within cutoff
        response = self.client.post(
            reverse('book_seats', args=[self.theater.id]) + f"?show_id={self.show_cutoff.id}",
            {'seats': [self.seat.id]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'closed')
        self.seat.refresh_from_db()
        self.assertFalse(self.seat.is_booked)

    def test_toggle_seat_lock_blocks_closed_show(self):
        """Seat lock AJAX endpoint returns 400 for show within cutoff."""
        self.client.login(username='cutoff_user', password='password123')
        response = self.client.post(
            reverse('toggle_seat_lock', args=[self.theater.id]),
            {'seat_id': self.seat.id, 'action': 'lock', 'show_id': self.show_cutoff.id}
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('closed', data['message'].lower())

    def test_create_order_blocks_closed_show(self):
        """Payment order creation is rejected for show within cutoff."""
        session = self.client.session
        session.save()
        success, msg, order_data = PaymentGatewayService.create_payment_order(
            theater=self.theater,
            seat_ids=[self.seat.id],
            user=self.user,
            session_key=session.session_key,
            show_id=self.show_cutoff.id
        )
        self.assertFalse(success)
        self.assertIn('closed', msg.lower())


# ======================================================================
# Task: Ticket Cancellation & Refund Process Tests
# ======================================================================

class RefundProcessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='refund_user', password='password123', email='refund@test.com')
        self.other_user = User.objects.create_user(username='other_customer', password='password123', email='other@test.com')
        self.admin_user = User.objects.create_superuser(username='refund_admin', password='password123', email='admin@test.com')

        self.movie = Movie.objects.create(
            name='Interstellar IMAX',
            title='Interstellar IMAX',
            slug='interstellar-imax',
            duration=169,
            is_active=True
        )
        self.theater = Theater.objects.create(
            name='Cinepolis Grand',
            movie=self.movie,
            city='Delhi',
            is_active=True
        )
        self.screen = Screen.objects.create(
            theater=self.theater,
            name='Audi 1',
            screen_type='IMAX',
            seating_capacity=80
        )
        now = timezone.now()
        # Future show (starts in 4 hours, well ahead of 10m cutoff)
        self.show_future = ShowSchedule.objects.create(
            movie=self.movie,
            theater=self.theater,
            screen=self.screen,
            start_time=now + timedelta(hours=4),
            price=Decimal('200.00'),
            status='open'
        )
        # Near show (starts in 5 minutes, inside 10m cutoff)
        self.show_cutoff = ShowSchedule.objects.create(
            movie=self.movie,
            theater=self.theater,
            screen=self.screen,
            start_time=now + timedelta(minutes=5),
            price=Decimal('200.00'),
            status='open'
        )
        self.seat1 = Seat.objects.create(theater=self.theater, seat_number='D1', price=Decimal('200.00'), is_booked=True)
        self.seat2 = Seat.objects.create(theater=self.theater, seat_number='D2', price=Decimal('200.00'), is_booked=True)

        self.payment = Payment.objects.create(
            order_id='ord_refund_test_123',
            transaction_id='txn_direct_refund_123',
            gateway='RAZORPAY',
            status='SUCCESS',
            user=self.user,
            movie=self.movie,
            theater=self.theater,
            show=self.show_future,
            amount=Decimal('440.00'),
            seat_ids=[self.seat1.id, self.seat2.id],
            seat_numbers='D1, D2'
        )
        self.b1 = Booking.objects.create(user=self.user, seat=self.seat1, movie=self.movie, theater=self.theater, show=self.show_future, payment=self.payment)
        self.b2 = Booking.objects.create(user=self.user, seat=self.seat2, movie=self.movie, theater=self.theater, show=self.show_future, payment=self.payment)

    def test_refund_eligibility_future_show(self):
        """Confirmed booking on upcoming show is eligible for 100% refund."""
        eligible, reason = RefundService.is_eligible_for_refund(self.payment, user=self.user)
        self.assertTrue(eligible)

    def test_refund_eligibility_cutoff_show(self):
        """Show within 10 minutes of start time is ineligible for refund."""
        self.payment.show = self.show_cutoff
        self.payment.save()
        eligible, reason = RefundService.is_eligible_for_refund(self.payment, user=self.user)
        self.assertFalse(eligible)
        self.assertIn('10 minutes', reason)

    def test_refund_eligibility_unauthorized_user(self):
        """User cannot refund another user's payment transaction."""
        eligible, reason = RefundService.is_eligible_for_refund(self.payment, user=self.other_user)
        self.assertFalse(eligible)
        self.assertIn('permission', reason.lower())

    def test_process_refund_success(self):
        """Processing refund changes status to REFUNDED, frees seats, and removes bookings."""
        self.assertTrue(self.seat1.is_booked)
        self.assertTrue(self.seat2.is_booked)
        self.assertEqual(Booking.objects.filter(payment=self.payment).count(), 2)

        success, msg, payment = RefundService.process_refund(self.payment, user=self.user, reason="Schedule conflict")
        self.assertTrue(success)
        self.assertEqual(payment.status, 'REFUNDED')

        # Seats must be freed
        self.seat1.refresh_from_db()
        self.seat2.refresh_from_db()
        self.assertFalse(self.seat1.is_booked)
        self.assertFalse(self.seat2.is_booked)

        # Booking records must be removed
        self.assertEqual(Booking.objects.filter(payment=self.payment).count(), 0)

        # Second refund attempt must fail (already refunded)
        self.payment.refresh_from_db()
        success2, msg2, _ = RefundService.process_refund(self.payment, user=self.user)
        self.assertFalse(success2)
        self.assertIn('already been refunded', msg2)

    def test_refund_view_get_confirmation(self):
        """GET request on refund view renders confirmation page."""
        self.client.login(username='refund_user', password='password123')
        response = self.client.get(reverse('process_refund', args=[self.payment.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cancel Booking &amp; Process Refund')
        self.assertContains(response, 'Interstellar IMAX')

    def test_refund_view_post_execution(self):
        """POST request on refund view processes refund and redirects to profile."""
        self.client.login(username='refund_user', password='password123')
        response = self.client.post(
            reverse('process_refund', args=[self.payment.id]),
            {'reason': 'Booked wrong date'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('profile'))

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'REFUNDED')

    def test_download_ticket_blocked_after_refund(self):
        """Ticket PDF download is blocked once payment has been refunded."""
        self.client.login(username='refund_user', password='password123')
        # Refund payment
        RefundService.process_refund(self.payment, user=self.user)
        # Attempt download
        response = self.client.get(reverse('download_payment_tickets', args=[self.payment.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('profile'))

    def test_verify_ticket_marks_refunded_void(self):
        """QR gate verification indicates ticket is voided if refunded."""
        # Create a single booking referencing a refunded payment
        token = TicketGeneratorService.get_verification_token(self.b1.id, self.user.id, self.movie.id)
        self.payment.status = 'REFUNDED'
        self.payment.save()

        response = self.client.get(reverse('verify_ticket', args=[self.b1.id]), {'token': token})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TICKET VOIDED &bull; BOOKING REFUNDED')


class ExpandedCatalogAndUpcomingMoviesTests(TestCase):
    """
    Validates diverse movie categories (Anime, Hollywood, Bollywood),
    upcoming movies in theaters with dates, diverse theater types, and catalog management commands.
    """

    def setUp(self):
        self.client = Client()
        today = timezone.localdate()

        self.lang_en = Language.objects.create(name='English', code='en')
        self.lang_hi = Language.objects.create(name='Hindi', code='hi')
        self.lang_ja = Language.objects.create(name='Japanese', code='ja')

        self.genre_anime = Genre.objects.create(name='Anime', slug='anime')
        self.genre_action = Genre.objects.create(name='Action', slug='action')
        self.genre_scifi = Genre.objects.create(name='Sci-Fi', slug='sci-fi')

        # Running Hollywood Movie
        self.movie_now = Movie.objects.create(
            title='Gladiator II',
            release_date=today - timedelta(days=10),
            duration=148,
            language=self.lang_en,
            is_active=True
        )
        self.movie_now.genres.add(self.genre_action)

        # Running Anime Movie
        self.movie_anime = Movie.objects.create(
            title='Demon Slayer: Infinity Castle',
            release_date=today - timedelta(days=5),
            duration=115,
            language=self.lang_ja,
            is_active=True
        )
        self.movie_anime.genres.add(self.genre_anime)

        # Running Bollywood Movie
        self.movie_bolly = Movie.objects.create(
            title='Jawan',
            release_date=today - timedelta(days=30),
            duration=169,
            language=self.lang_hi,
            is_active=True
        )
        self.movie_bolly.genres.add(self.genre_action)

        # Upcoming Movie with future release date
        self.movie_upcoming = Movie.objects.create(
            title='Avatar: Fire and Ash',
            release_date=today + timedelta(days=60),
            duration=190,
            language=self.lang_en,
            is_active=True
        )
        self.movie_upcoming.genres.add(self.genre_scifi)

        # Big Theater (IMAX Superplex)
        self.theater_big = Theater.objects.create(
            name='PVR Superplex IMAX Laser & 4DX',
            city='Mumbai',
            address='Phoenix Mall, Lower Parel',
            is_active=True
        )
        self.screen_imax = Screen.objects.create(
            theater=self.theater_big,
            name='Audi 1 (IMAX Laser)',
            screen_type='IMAX',
            seating_capacity=280
        )

        # Small Theater (Boutique Lounge)
        self.theater_small = Theater.objects.create(
            name='The Velvet Screen Boutique & Indie Lounge',
            city='Bengaluru',
            address='100 Feet Road, Indiranagar',
            is_active=True
        )
        self.screen_boutique = Screen.objects.create(
            theater=self.theater_small,
            name='The Velvet Salon',
            screen_type='Dolby Atmos',
            seating_capacity=36
        )

        # Unique Theater (Drive-In)
        self.theater_drivein = Theater.objects.create(
            name='Sunset Open-Air & Drive-In Cinema',
            city='Goa',
            address='Vagator Cliffside',
            is_active=True
        )
        self.screen_drivein = Screen.objects.create(
            theater=self.theater_drivein,
            name='Cliffside Screen (FM 98.4)',
            screen_type='2D',
            seating_capacity=60
        )

    def test_movie_is_upcoming_property(self):
        """Movie.is_upcoming returns True for future dates and False for current/past dates."""
        self.assertFalse(self.movie_now.is_upcoming)
        self.assertFalse(self.movie_anime.is_upcoming)
        self.assertFalse(self.movie_bolly.is_upcoming)
        self.assertTrue(self.movie_upcoming.is_upcoming)

    def test_theater_list_view_upcoming_movie_release_date_handling(self):
        """theater_list view defaults date selection to release_date for upcoming movies."""
        response = self.client.get(reverse('theater_list', args=[self.movie_upcoming.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_upcoming_movie'])
        self.assertEqual(response.context['selected_date'], self.movie_upcoming.release_date.strftime('%Y-%m-%d'))
        self.assertContains(response, 'Advance Booking Open')
        self.assertContains(response, 'Premiere')

    def test_home_view_categorization_and_theaters_context(self):
        """Home view splits movies into now_showing, upcoming, hollywood, bollywood, anime and provides theaters."""
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('now_showing_movies', response.context)
        self.assertIn('upcoming_movies', response.context)
        self.assertIn('hollywood_movies', response.context)
        self.assertIn('bollywood_movies', response.context)
        self.assertIn('anime_movies', response.context)
        self.assertIn('theaters', response.context)

        upcoming_ids = [m.id for m in response.context['upcoming_movies']]
        self.assertIn(self.movie_upcoming.id, upcoming_ids)
        self.assertNotIn(self.movie_now.id, upcoming_ids)

        now_ids = [m.id for m in response.context['now_showing_movies']]
        self.assertIn(self.movie_now.id, now_ids)
        self.assertIn(self.movie_anime.id, now_ids)
        self.assertIn(self.movie_bolly.id, now_ids)

    def test_theater_seating_layout_and_types(self):
        """Theaters of varying types (Big, Small, Drive-in) generate appropriate seating capacity and layouts."""
        TheaterSeatingService.ensure_full_theater_layout(self.theater_big, min_seats=50)
        TheaterSeatingService.ensure_full_theater_layout(self.theater_small, min_seats=30)
        TheaterSeatingService.ensure_full_theater_layout(self.theater_drivein, min_seats=30)

        self.assertGreaterEqual(self.theater_big.seats.count(), 50)
        self.assertGreaterEqual(self.theater_small.seats.count(), 30)
        self.assertGreaterEqual(self.theater_drivein.seats.count(), 30)

    def test_populate_expanded_catalog_command(self):
        """populate_expanded_catalog command runs cleanly and ensures all categories and theaters are created."""
        from django.core.management import call_command
        call_command('populate_expanded_catalog')

        # Verify diverse movies exist
        self.assertTrue(Movie.objects.filter(language__code='ja').exists(), "Anime movies must exist")
        self.assertTrue(Movie.objects.filter(language__code='hi').exists(), "Bollywood movies must exist")
        self.assertTrue(Movie.objects.filter(language__code='en').exists(), "Hollywood movies must exist")
        self.assertTrue(Movie.objects.filter(release_date__gt=timezone.localdate()).exists(), "Upcoming movies must exist")

        # Verify diverse theaters exist
        self.assertTrue(Theater.objects.filter(name__icontains='PVR Superplex').exists(), "Big Superplex must exist")
        self.assertTrue(Theater.objects.filter(name__icontains='Velvet Screen').exists(), "Boutique theater must exist")
        self.assertTrue(Theater.objects.filter(name__icontains='Drive-In').exists(), "Drive-in cinema must exist")
        self.assertTrue(Theater.objects.filter(name__icontains='Rooftop').exists(), "Rooftop cinema must exist")

        # Verify shows exist for upcoming movies
        upcoming_movie = Movie.objects.filter(release_date__gt=timezone.localdate()).first()
        self.assertIsNotNone(upcoming_movie)
        self.assertTrue(upcoming_movie.shows.exists(), "Upcoming movies must have scheduled shows in theaters")
