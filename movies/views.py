from datetime import datetime, time, date, timedelta
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q, Avg, Count, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse, HttpResponseBadRequest
from django.urls import reverse
from django.utils import timezone

from django.core.exceptions import PermissionDenied
from django.views.decorators.csrf import csrf_exempt

from .models import (
    Movie, MovieImage, Genre, Language, CastMember,
    Theater, Screen, ShowSchedule, Seat, Booking,
    Review, ReviewReport, Payment
)
from .forms import (
    MovieForm, MovieImageForm, ReviewForm, ReviewReportForm, ShowScheduleForm,
    TheaterForm, AssignTheatersForm
)
from .services import (
    ReviewEligibilityService, MovieQueryService, SeatLockService, TheaterSeatingService,
    PaymentGatewayService, BusinessAnalyticsService, MovieDiscoveryService, RefundService
)
from .ticket_service import TicketGeneratorService
from .tasks import dispatch_booking_ticket_email


# ----------------------------------------------------------------------
# Public Movie Views
# ----------------------------------------------------------------------

def movie_list(request):
    """
    Commercial-grade movie discovery with multi-criteria search, filtering, and sorting:
    - Search by title, name, cast, or director
    - Filters: genre, language, city, theater, release date, rating, and show timings
    - Sorting: popularity, newest releases, rating, and ticket price (low / high)
    - Dynamic count of matching movies
    - Personalized 'Recommended for You' section based on booking history and recently viewed titles
    - Recently viewed shelf
    - Fast JSON API support when requested asynchronously
    """
    raw_params = request.GET.dict()
    if 'genres' in request.GET:
        raw_params['genres'] = request.GET.getlist('genres')
    if 'languages' in request.GET:
        raw_params['languages'] = request.GET.getlist('languages')
    if 'timings' in request.GET:
        raw_params['timings'] = request.GET.getlist('timings')

    current_user = getattr(request, 'user', None)
    movies_qs, total_count, applied_filters = MovieDiscoveryService.filter_movies(
        params=raw_params, user=current_user
    )

    per_page = int(request.GET.get('per_page', 12))
    paginator = Paginator(movies_qs, per_page)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # If JSON response requested (e.g. dynamic live search/filtering preview)
    is_json = (
        request.GET.get('format') == 'json' or
        request.headers.get('x-requested-with') == 'XMLHttpRequest' or
        request.headers.get('accept', '').startswith('application/json')
    )

    if is_json:
        movie_items = []
        for m in page_obj:
            movie_items.append({
                'id': m.id,
                'title': m.title or m.name,
                'slug': m.slug or f"movie-{m.id}",
                'rating': float(m.rating) if m.rating else 0.0,
                'total_reviews': m.total_reviews,
                'age_certification': m.age_certification,
                'duration': m.duration,
                'language': m.language.name if m.language else 'English',
                'language_code': m.language.code if m.language else 'en',
                'genres': [g.name for g in m.genres.all()[:3]],
                'poster_url': m.get_primary_poster_url(),
                'min_price': float(m.min_ticket_price) if hasattr(m, 'min_ticket_price') else 150.0,
                'release_date': m.release_date.strftime('%Y-%m-%d') if m.release_date else '',
                'detail_url': reverse('movie_detail', args=[m.slug]) if m.slug else f'/movies/{m.id}/theaters/',
                'booking_url': reverse('theater_list', args=[m.id]),
                'trailer_video_id': m.get_youtube_video_id() or '',
            })
        return JsonResponse({
            'success': True,
            'count': total_count,
            'current_page': page_obj.number,
            'num_pages': paginator.num_pages,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'applied_filters': applied_filters,
            'movies': movie_items,
        })

    # Filter Options & Metadata for Filter Sidebar
    filter_options = MovieDiscoveryService.get_filter_options()

    # Recommendations & Recently Viewed Shelves
    session_viewed_ids = getattr(request, 'session', {}).get('recently_viewed_movies', []) if hasattr(request, 'session') else []
    recommendations = MovieDiscoveryService.get_personalized_recommendations(
        user=current_user, session_viewed_ids=session_viewed_ids, limit=6
    )
    recently_viewed = MovieDiscoveryService.get_recently_viewed_movies(request, limit=6) if hasattr(request, 'session') else []

    context = {
        'movies': page_obj,
        'page_obj': page_obj,
        'total_count': total_count,
        'applied_filters': applied_filters,
        'filter_options': filter_options,
        'recommendations': recommendations,
        'recently_viewed': recently_viewed,
        # Backward compatibility for template variables
        'search_query': applied_filters.get('search', ''),
        'selected_genre': request.GET.get('genre', ''),
        'selected_language': request.GET.get('language', ''),
        'selected_city': applied_filters.get('city', ''),
        'selected_theater': applied_filters.get('theater', ''),
        'selected_timing': applied_filters.get('timing', ''),
        'selected_release': applied_filters.get('release_date', ''),
        'selected_rating': applied_filters.get('rating', ''),
        'selected_sort': applied_filters.get('sort', 'popularity'),
        'all_genres': filter_options['genres'],
        'all_languages': filter_options['languages'],
    }
    return render(request, 'movies/movie_list.html', context)


def movie_discovery_api(request):
    """
    Dedicated JSON API endpoint for dynamic movie discovery, live match counts,
    and client-side filter updates without page reloads.
    """
    raw_params = request.GET.dict()
    if 'genres' in request.GET:
        raw_params['genres'] = request.GET.getlist('genres')
    if 'languages' in request.GET:
        raw_params['languages'] = request.GET.getlist('languages')
    if 'timings' in request.GET:
        raw_params['timings'] = request.GET.getlist('timings')

    current_user = getattr(request, 'user', None)
    movies_qs, total_count, applied_filters = MovieDiscoveryService.filter_movies(
        params=raw_params, user=current_user
    )

    per_page = int(request.GET.get('per_page', 12))
    paginator = Paginator(movies_qs, per_page)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    movie_items = []
    for m in page_obj:
        movie_items.append({
            'id': m.id,
            'title': m.title or m.name,
            'slug': m.slug or f"movie-{m.id}",
            'rating': float(m.rating) if m.rating else 0.0,
            'total_reviews': m.total_reviews,
            'age_certification': m.age_certification,
            'duration': m.duration,
            'language': m.language.name if m.language else 'English',
            'language_code': m.language.code if m.language else 'en',
            'genres': [g.name for g in m.genres.all()[:3]],
            'poster_url': m.get_primary_poster_url(),
            'min_price': float(m.min_ticket_price) if hasattr(m, 'min_ticket_price') else 150.0,
            'release_date': m.release_date.strftime('%Y-%m-%d') if m.release_date else '',
            'detail_url': reverse('movie_detail', args=[m.slug]) if m.slug else f'/movies/{m.id}/theaters/',
            'booking_url': reverse('theater_list', args=[m.id]),
            'trailer_video_id': m.get_youtube_video_id() or '',
        })

    return JsonResponse({
        'success': True,
        'count': total_count,
        'current_page': page_obj.number,
        'num_pages': paginator.num_pages,
        'has_next': page_obj.has_next(),
        'has_previous': page_obj.has_previous(),
        'applied_filters': applied_filters,
        'movies': movie_items,
    })


def movie_detail(request, slug):
    """
    Commercial-grade movie details page with poster/gallery, specs, trailer,
    verified reviews, ratings, and recommendation sections.
    """
    movie = get_object_or_404(
        Movie.objects.select_related('language', 'director')
                     .prefetch_related('genres', 'languages', 'cast_members', 'gallery_images'),
        slug=slug,
        is_active=True
    )

    # Approved reviews with reviewer details
    reviews_qs = (
        movie.reviews.filter(is_approved=True)
                     .select_related('user')
                     .order_by('-created_at')
    )
    reviews_paginator = Paginator(reviews_qs, 6)
    page_number = request.GET.get('page', 1)
    reviews_page = reviews_paginator.get_page(page_number)

    # Review eligibility & status check for current user
    can_review = False
    review_eligibility_reason = ""
    is_verified_viewer = False
    existing_user_review = None

    if request.user.is_authenticated:
        existing_user_review = Review.objects.filter(movie=movie, user=request.user).first()
        can_review, review_eligibility_reason, is_verified_viewer = (
            ReviewEligibilityService.check_eligibility(request.user, movie)
        )

    # Related movie sections (optimized via service)
    similar_movies = MovieQueryService.get_similar_movies(movie, limit=6)
    trending_movies = MovieQueryService.get_trending_movies(limit=6, exclude_movie_id=movie.id)
    recent_movies = MovieQueryService.get_recently_released_movies(limit=6, exclude_movie_id=movie.id)

    # Track recently viewed in user session
    MovieDiscoveryService.track_recently_viewed_movie(request, movie.id)

    # Forms for modals
    review_form = ReviewForm()
    report_form = ReviewReportForm()

    context = {
        'movie': movie,
        'reviews': reviews_page,
        'reviews_count': reviews_qs.count(),
        'can_review': can_review,
        'review_eligibility_reason': review_eligibility_reason,
        'is_verified_viewer': is_verified_viewer,
        'existing_user_review': existing_user_review,
        'similar_movies': similar_movies,
        'trending_movies': trending_movies,
        'recent_movies': recent_movies,
        'review_form': review_form,
        'report_form': report_form,
        'gallery_images': movie.gallery_images.all(),
    }
    return render(request, 'movies/movie_detail.html', context)


def movie_detail_by_id(request, movie_id):
    """
    Convenience view redirecting movie ID to canonical slug URL.
    """
    movie = get_object_or_404(Movie, id=movie_id, is_active=True)
    MovieDiscoveryService.track_recently_viewed_movie(request, movie.id)
    return redirect('movie_detail', slug=movie.slug)


# ----------------------------------------------------------------------
# Legacy Views (Preserved for compatibility)
# ----------------------------------------------------------------------

def theater_list(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    theaters = Theater.objects.filter(Q(movie=movie) | Q(shows__movie=movie), is_active=True).distinct()
    if not theaters.exists():
        theaters = Theater.objects.filter(is_active=True)

    today = timezone.localdate()
    is_upcoming_movie = bool(movie.release_date and movie.release_date > today)

    # For upcoming movies without an explicit date parameter, default to the premiere release date
    default_start_date = movie.release_date if is_upcoming_movie else today
    selected_date_str = request.GET.get('date', default_start_date.strftime('%Y-%m-%d'))
    selected_format = request.GET.get('format', 'all')
    selected_slot = request.GET.get('slot', 'all')

    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        selected_date = default_start_date
        selected_date_str = default_start_date.strftime('%Y-%m-%d')

    is_past_date = selected_date < today
    now = timezone.now()
    cutoff_delta = timedelta(minutes=10)

    # Base date for the 7-day strip
    if 'date' not in request.GET:
        base_strip_date = default_start_date
    else:
        if selected_date < today:
            base_strip_date = selected_date
        elif is_upcoming_movie and selected_date >= movie.release_date:
            base_strip_date = movie.release_date
        else:
            base_strip_date = today

    dates = []
    for i in range(7):
        d = base_strip_date + timedelta(days=i)
        d_str = d.strftime('%Y-%m-%d')
        if d == today:
            day_label = "Today"
        elif d == today + timedelta(days=1):
            day_label = "Tomorrow"
        elif movie.release_date and d == movie.release_date and is_upcoming_movie:
            day_label = "Premiere"
        else:
            day_label = d.strftime('%a')

        dates.append({
            'date': d,
            'date_str': d_str,
            'day_name': day_label,
            'day_num': d.strftime('%d'),
            'month_name': d.strftime('%b'),
            'is_selected': (d_str == selected_date_str)
        })

    from collections import defaultdict
    schedules_by_theater = defaultdict(list)
    schedules_qs = ShowSchedule.objects.filter(
        theater__in=theaters,
        movie=movie,
        start_time__date=selected_date
    ).select_related('screen').order_by('start_time')
    if selected_format != 'all':
        schedules_qs = schedules_qs.filter(screen__screen_type__icontains=selected_format)

    for s in schedules_qs:
        schedules_by_theater[s.theater_id].append(s)

    theater_data = []
    for th in theaters:
        th_schedules = schedules_by_theater.get(th.id, [])
        slots = []
        if th_schedules:
            for s in th_schedules:
                slot_hour = timezone.localtime(s.start_time).hour
                if selected_slot == 'morning' and not (slot_hour < 12):
                    continue
                elif selected_slot == 'afternoon' and not (12 <= slot_hour < 16):
                    continue
                elif selected_slot == 'evening' and not (16 <= slot_hour < 20):
                    continue
                elif selected_slot == 'night' and not (slot_hour >= 20):
                    continue

                is_closed = is_past_date or (s.start_time <= now + cutoff_delta) or (s.status not in ['open', 'scheduled'])
                is_started = is_past_date or (s.start_time <= now)

                if is_started:
                    status_text = 'Show Started' if not is_past_date else 'Closed'
                elif is_closed:
                    status_text = 'Closed'
                else:
                    status_text = 'Fast Filling' if (s.id % 2 == 0) else 'Available'

                slots.append({
                    'id': s.id,
                    'show_id': s.id,
                    'time_str': timezone.localtime(s.start_time).strftime('%I:%M %p'),
                    'screen_type': s.screen.screen_type if s.screen else '2D Standard',
                    'screen_name': s.screen.name if s.screen else 'Screen 1',
                    'price': s.price,
                    'status': status_text,
                    'is_closed': is_closed,
                    'is_started': is_started,
                    'theater_id': th.id,
                })
        else:
            fallback_times = [
                ('10:15 AM', 'IMAX 3D', 'Audi 1 (IMAX)', Decimal('180.00'), 10, 15),
                ('01:45 PM', 'Dolby Atmos', 'Audi 2 (Atmos)', Decimal('160.00'), 13, 45),
                ('05:30 PM', '4DX Laser', 'Audi 3 (4DX)', Decimal('220.00'), 17, 30),
                ('09:30 PM', '2D Standard', 'Audi 4 (Digital)', Decimal('140.00'), 21, 30),
            ]
            for t_str, scr_type, scr_name, pr, hr, mn in fallback_times:
                if selected_format != 'all' and selected_format.lower() not in scr_type.lower():
                    continue
                if selected_slot == 'morning' and not (hr < 12):
                    continue
                elif selected_slot == 'afternoon' and not (12 <= hr < 16):
                    continue
                elif selected_slot == 'evening' and not (16 <= hr < 20):
                    continue
                elif selected_slot == 'night' and not (hr >= 20):
                    continue

                slot_dt = timezone.make_aware(datetime.combine(selected_date, time(hr, mn)))
                is_closed = is_past_date or (slot_dt <= now + cutoff_delta)
                is_started = is_past_date or (slot_dt <= now)

                if is_started:
                    status_text = 'Show Started' if not is_past_date else 'Closed'
                elif is_closed:
                    status_text = 'Closed'
                else:
                    status_text = 'Available'

                slots.append({
                    'id': None,
                    'show_id': None,
                    'time_str': t_str,
                    'screen_type': scr_type,
                    'screen_name': scr_name,
                    'price': pr,
                    'status': status_text,
                    'is_closed': is_closed,
                    'is_started': is_started,
                    'theater_id': th.id,
                })

        theater_data.append({
            'theater': th,
            'slots': slots,
        })

    context = {
        'movie': movie,
        'theaters': theaters,
        'theater_data': theater_data,
        'dates': dates,
        'selected_date': selected_date_str,
        'selected_format': selected_format,
        'selected_slot': selected_slot,
        'is_past_date': is_past_date,
        'is_upcoming_movie': is_upcoming_movie,
        'movie_release_date': movie.release_date,
    }
    return render(request, 'movies/theater_list.html', context)


@login_required(login_url='/login/')
def book_seats(request, theater_id):
    theater = get_object_or_404(Theater, id=theater_id)
    # Ensure full realistic multi-tier auditorium layout if needed
    TheaterSeatingService.ensure_full_theater_layout(theater)

    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key

    seats = Seat.objects.filter(theater=theater).order_by('row', 'number', 'seat_number')

    show_id = request.GET.get('show_id') or request.POST.get('show_id')
    show = None
    if show_id:
        show = ShowSchedule.objects.filter(id=show_id, theater=theater).select_related('movie', 'screen').first()

    if not show and hasattr(theater, 'shows'):
        show = theater.shows.filter(
            start_time__gt=timezone.now() + timedelta(minutes=10),
            status__in=['open', 'scheduled']
        ).order_by('start_time').first()

    is_show_closed = False
    closed_reason = ""
    if show:
        if not show.is_booking_open:
            is_show_closed = True
            local_start = timezone.localtime(show.start_time)
            local_cutoff = timezone.localtime(show.cutoff_time)
            if show.is_past:
                closed_reason = f"Screening at {local_start.strftime('%I:%M %p')} has already started or completed. Ticket booking is closed."
            else:
                closed_reason = f"Ticket booking for {local_start.strftime('%I:%M %p')} closed 10 minutes prior to showtime (cutoff was {local_cutoff.strftime('%I:%M %p')}). Online booking is not available."
    elif theater.time and not theater.is_booking_open:
        is_show_closed = True
        local_time = timezone.localtime(theater.time)
        closed_reason = f"Screening at {local_time.strftime('%I:%M %p')} is within the 10-minute cutoff or has already passed. Ticket booking is closed."

    if request.method == 'POST':
        import json
        is_json = request.content_type == 'application/json'
        if is_json:
            try:
                data = json.loads(request.body.decode('utf-8'))
            except json.JSONDecodeError:
                data = {}
            selected_seats = data.get('seats', [])
            payment_method = data.get('payment_method', 'card')
            post_show_id = data.get('show_id')
            if post_show_id and not show:
                show = ShowSchedule.objects.filter(id=post_show_id, theater=theater).first()
                if show and not show.is_booking_open:
                    is_show_closed = True
                    closed_reason = f"Booking for {timezone.localtime(show.start_time).strftime('%I:%M %p')} has closed (10-minute cutoff reached)."
        else:
            selected_seats = request.POST.getlist('seats')
            payment_method = request.POST.get('payment_method', 'card')

        if is_show_closed:
            err = closed_reason or "Booking for this screening has closed (online bookings close 10 minutes prior to showtime)."
            if is_json:
                return JsonResponse({'success': False, 'message': err}, status=400)
            return render(request, "movies/seat_selection.html", {
                'theater': theater,
                'theaters': theater,
                'show': show,
                'is_show_closed': True,
                'closed_reason': closed_reason,
                'seats': seats,
                'error': err
            })

        if not selected_seats:
            err = "No seat selected. Please pick at least one seat to proceed with booking."
            if is_json:
                return JsonResponse({'success': False, 'message': err}, status=400)
            return render(request, "movies/seat_selection.html", {
                'theater': theater,
                'theaters': theater,
                'show': show,
                'is_show_closed': is_show_closed,
                'closed_reason': closed_reason,
                'seats': seats,
                'error': err
            })

        # Atomic booking and payment finalization
        success, message, bookings = SeatLockService.finalize_booking(
            theater=theater,
            seat_ids=selected_seats,
            user=request.user,
            session_key=session_key,
            payment_method=payment_method,
            show=show
        )

        if not success:
            if is_json:
                return JsonResponse({'success': False, 'message': message}, status=400)
            return render(request, 'movies/seat_selection.html', {
                'theater': theater,
                'theaters': theater,
                'show': show,
                'is_show_closed': is_show_closed,
                'closed_reason': closed_reason,
                'seats': seats,
                'error': message
            })

        messages.success(request, f"Booking confirmed! {len(bookings)} ticket(s) reserved successfully. E-ticket issued.")
        # Asynchronously generate and send PDF ticket email via Celery
        dispatch_booking_ticket_email(bookings=bookings)

        if is_json:
            return JsonResponse({
                'success': True,
                'message': message,
                'redirect_url': reverse('profile'),
                'booking_ids': [b.id for b in bookings]
            })

        return redirect('profile')

    return render(request, 'movies/seat_selection.html', {
        'theater': theater,
        'theaters': theater,
        'show': show,
        'is_show_closed': is_show_closed,
        'closed_reason': closed_reason,
        'seats': seats,
    })


def toggle_seat_lock(request, theater_id):
    """
    AJAX endpoint to temporarily reserve (lock) or release seats.
    Enforces a 2-minute (120-second) reservation window with Django transactions.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    theater = get_object_or_404(Theater, id=theater_id)

    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key

    import json
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            data = {}
    else:
        data = request.POST

    action = data.get('action', 'lock')
    show_id = data.get('show_id') or request.GET.get('show_id')
    if action == 'lock':
        if show_id:
            show = ShowSchedule.objects.filter(id=show_id, theater=theater).first()
            if show and not show.is_booking_open:
                return JsonResponse({
                    'success': False,
                    'message': 'Booking for this screening has closed (online bookings close 10 minutes prior to showtime).'
                }, status=400)
        elif theater.time and not theater.is_booking_open:
            return JsonResponse({
                'success': False,
                'message': 'Screening booking has closed (online bookings close 10 minutes prior to showtime).'
            }, status=400)

    # Handle release_all action
    if action == 'release_all':
        SeatLockService.release_all_user_holds(
            user=request.user,
            session_key=session_key,
            theater_id=theater.id
        )
        return JsonResponse({'success': True, 'message': 'All seat holds released.'})

    seat_id = data.get('seat_id')
    seat_ids = data.get('seat_ids')

    # Batch reservation support
    if seat_ids and isinstance(seat_ids, list):
        if action == 'lock':
            success, message, locked_seats = SeatLockService.hold_multiple_seats(
                seat_ids=seat_ids,
                user=request.user,
                session_key=session_key,
                duration_seconds=120
            )
        else:
            for sid in seat_ids:
                SeatLockService.release_seat(seat_id=sid, user=request.user, session_key=session_key)
            success, message = True, "Seats released."
        return JsonResponse({'success': success, 'message': message, 'action': action})

    if not seat_id:
        return JsonResponse({'success': False, 'message': 'seat_id required.'}, status=400)

    try:
        seat = Seat.objects.get(id=seat_id, theater=theater)
    except Seat.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Seat not found in this theater.'}, status=404)

    if action == 'lock':
        success, message, _ = SeatLockService.hold_seat(
            seat_id=seat.id,
            user=request.user,
            session_key=session_key,
            duration_seconds=120
        )
    else:
        success, message, _ = SeatLockService.release_seat(
            seat_id=seat.id,
            user=request.user,
            session_key=session_key
        )

    return JsonResponse({
        'success': success,
        'message': message,
        'seat_id': seat.id,
        'seat_number': seat.seat_number,
        'action': action,
        'tier': seat.tier,
        'price': str(seat.price),
        'duration_seconds': 120
    })


def seat_live_status(request, theater_id):
    """
    Polling endpoint for real-time live seat synchronization.
    Returns real-time lists of booked seats, seats held by others, and seats held by me,
    along with the remaining countdown time for the current user's 2-minute reservation hold.
    """
    theater = get_object_or_404(Theater, id=theater_id)

    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key

    status = SeatLockService.get_live_status(
        theater_id=theater.id,
        user=request.user,
        session_key=session_key
    )
    return JsonResponse({'success': True, **status})


# ----------------------------------------------------------------------
# Payment Gateway & Online Booking Workflow Views
# ----------------------------------------------------------------------

@login_required(login_url='/login/')
def create_payment_order_view(request, theater_id):
    """
    API endpoint: Initializes a Razorpay / online payment order for reserved seats.
    Secures seats with 2-minute hold and records a PENDING Payment entry.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST method required.'}, status=405)

    theater = get_object_or_404(Theater, id=theater_id)

    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key

    import json
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            data = {}
    else:
        data = request.POST

    seats = data.get('seats', [])
    payment_method = data.get('payment_method', 'upi')
    addon_popcorn = bool(data.get('addon_popcorn', False))
    food_total = data.get('food_total', 0.0)
    try:
        from decimal import Decimal
        food_total = Decimal(str(food_total))
    except Exception:
        food_total = Decimal('0.00')
    show_id = data.get('show_id')

    if not seats:
        return JsonResponse({'success': False, 'message': 'Please select at least one seat to proceed.'}, status=400)

    success, message, order_data = PaymentGatewayService.create_payment_order(
        theater=theater,
        seat_ids=seats,
        user=request.user,
        session_key=session_key,
        payment_method=payment_method,
        addon_popcorn=addon_popcorn,
        show_id=show_id,
        food_total=food_total
    )

    if not success:
        return JsonResponse({'success': False, 'message': message}, status=400)

    return JsonResponse({
        'success': True,
        'message': message,
        'order': order_data,
        'razorpay_key_id': order_data.get('key_id')
    })


@login_required(login_url='/login/')
def verify_payment_view(request):
    """
    API endpoint: Cryptographically verifies online payment (Razorpay signature) on the server.
    Ensures idempotency (duplicate confirmations never create duplicate bookings).
    Confirms bookings and marks seats permanently booked.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST method required.'}, status=405)

    import json
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            data = {}
    else:
        data = request.POST

    order_id = data.get('razorpay_order_id') or data.get('order_id')
    payment_id = data.get('razorpay_payment_id') or data.get('payment_id') or data.get('transaction_id')
    signature = data.get('razorpay_signature') or data.get('signature')

    if not order_id or not payment_id or not signature:
        return JsonResponse({
            'success': False,
            'message': 'Incomplete verification parameters: order_id, payment_id, and signature required.'
        }, status=400)

    success, message, bookings, payment = PaymentGatewayService.verify_payment(
        order_id=order_id,
        payment_id=payment_id,
        signature=signature,
        user=request.user
    )

    if not success:
        return JsonResponse({'success': False, 'message': message}, status=400)

    messages.success(request, f"Payment verified successfully! {len(bookings)} ticket(s) confirmed.")
    # Asynchronously generate and send PDF ticket email via Celery
    dispatch_booking_ticket_email(payment=payment, bookings=bookings)

    return JsonResponse({
        'success': True,
        'message': message,
        'redirect_url': reverse('profile'),
        'order_id': order_id,
        'transaction_id': payment_id,
        'booking_ids': [b.id for b in bookings]
    })


@login_required(login_url='/login/')
def download_ticket_view(request, booking_id):
    """
    Downloads an authentic, print-ready PDF admission ticket pass for a confirmed booking.
    Verifies that the requesting user owns the booking (or is staff).
    """
    booking = get_object_or_404(
        Booking.objects.select_related('movie', 'theater', 'seat', 'show', 'payment', 'user'),
        id=booking_id
    )

    if booking.user != request.user and not request.user.is_staff:
        raise PermissionDenied("You do not have permission to download this ticket.")

    if booking.payment and booking.payment.status == 'REFUNDED':
        messages.error(request, "This booking has been refunded and the ticket is voided.")
        return redirect('profile')

    pdf_bytes = TicketGeneratorService.generate_ticket_pdf(booking=booking, request=request)
    movie_slug = booking.movie.slug or 'movie'
    filename = f"ticket_{movie_slug}_{booking.id}.pdf"

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required(login_url='/login/')
def download_payment_tickets_view(request, payment_id):
    """
    Downloads a consolidated PDF admission ticket pass for all seats in a payment transaction.
    """
    payment = get_object_or_404(
        Payment.objects.select_related('movie', 'theater', 'show', 'user'),
        id=payment_id
    )

    if payment.user != request.user and not request.user.is_staff:
        raise PermissionDenied("You do not have permission to download tickets for this transaction.")

    if payment.status == 'REFUNDED':
        messages.error(request, "This transaction has been refunded and the ticket pass is voided.")
        return redirect('profile')

    pdf_bytes = TicketGeneratorService.generate_ticket_pdf(payment=payment, request=request)
    filename = f"tickets_order_{payment.order_id}.pdf"

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def verify_ticket_view(request, booking_id):
    """
    Public ticket verification endpoint invoked when QR codes are scanned at the cinema entrance.
    Validates cryptographic HMAC-SHA256 token against booking records.
    """
    booking = Booking.objects.filter(id=booking_id).select_related('movie', 'theater', 'seat', 'show', 'payment', 'user').first()
    token = request.GET.get('token', '')

    is_valid = False
    is_refunded = False
    if booking:
        if booking.payment and booking.payment.status == 'REFUNDED':
            is_valid = False
            is_refunded = True
        elif TicketGeneratorService.verify_ticket_token(booking, token):
            is_valid = True
        elif request.user.is_authenticated and request.user.is_staff:
            is_valid = True

    return render(request, 'movies/verify_ticket.html', {
        'booking': booking,
        'is_valid': is_valid,
        'is_refunded': is_refunded,
        'token': token,
    })


@login_required(login_url='/login/')
def payment_failure_view(request):
    """
    API endpoint: Records a failed transaction on the server and automatically releases reserved seats.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST method required.'}, status=405)

    import json
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            data = {}
    else:
        data = request.POST

    order_id = data.get('order_id') or data.get('razorpay_order_id')
    error_code = data.get('error_code', 'PAYMENT_FAILED')
    error_description = data.get('error_description', 'Payment failed.')
    transaction_id = data.get('transaction_id', '')

    if not order_id:
        return JsonResponse({'success': False, 'message': 'order_id required.'}, status=400)

    success, message, payment = PaymentGatewayService.record_payment_failure(
        order_id=order_id,
        error_code=error_code,
        error_description=error_description,
        transaction_id=transaction_id
    )

    return JsonResponse({'success': success, 'message': message})


@login_required(login_url='/login/')
def payment_cancel_view(request):
    """
    API endpoint: Records payment cancellation by the user and immediately releases held seats back to availability.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST method required.'}, status=405)

    import json
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            data = {}
    else:
        data = request.POST

    order_id = data.get('order_id') or data.get('razorpay_order_id')
    if not order_id:
        return JsonResponse({'success': False, 'message': 'order_id required.'}, status=400)

    success, message, payment = PaymentGatewayService.record_payment_cancellation(
        order_id=order_id,
        user=request.user
    )

    return JsonResponse({'success': success, 'message': message})


@login_required(login_url='/login/')
def payment_retry_view(request):
    """
    API endpoint: Re-initiates payment for a failed or pending transaction.
    Re-acquires 2-minute lock if seats are still free and returns fresh order details.
    """
    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key

    order_id = request.GET.get('order_id')
    if not order_id:
        if request.content_type == 'application/json':
            try:
                import json
                data = json.loads(request.body.decode('utf-8'))
                order_id = data.get('order_id')
            except Exception:
                order_id = None
        else:
            order_id = request.POST.get('order_id')

    if not order_id:
        return JsonResponse({'success': False, 'message': 'order_id required for retry.'}, status=400)

    success, message, new_order = PaymentGatewayService.retry_payment(
        previous_order_id=order_id,
        user=request.user,
        session_key=session_key
    )

    if not success:
        if request.headers.get('Accept') == 'application/json' or request.content_type == 'application/json':
            return JsonResponse({'success': False, 'message': message}, status=400)
        messages.error(request, message)
        return redirect('profile')

    if request.headers.get('Accept') == 'application/json' or request.content_type == 'application/json':
        return JsonResponse({'success': True, 'message': message, 'order': new_order})

    prev_pay = Payment.objects.filter(order_id=order_id).first()
    if prev_pay:
        return redirect('book_seats', theater_id=prev_pay.theater.id)
    return redirect('profile')


@csrf_exempt
def razorpay_webhook_view(request):
    """
    Webhook receiver: Handles asynchronous server-to-server notifications from Razorpay.
    Verifies HMAC-SHA256 signature against settings.RAZORPAY_WEBHOOK_SECRET.
    Dispatches:
      - payment.captured / order.paid -> verifies and books
      - payment.failed -> records failure and auto-releases seats
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    signature_header = request.headers.get('X-Razorpay-Signature', '')
    if not signature_header:
        signature_header = request.META.get('HTTP_X_RAZORPAY_SIGNATURE', '')

    success, message, result = PaymentGatewayService.verify_webhook(
        payload_body=request.body,
        signature_header=signature_header
    )

    if not success:
        return JsonResponse({'error': message}, status=400)

    return JsonResponse({'status': 'ok', 'message': message, 'result': result})


# ----------------------------------------------------------------------
# Cancellation & Refund Management Views
# ----------------------------------------------------------------------

@login_required(login_url='/login/')
def process_refund_view(request, payment_id):
    """
    Processes ticket cancellation and 100% payment refund.
    Strictly verifies user ownership and 10-minute showtime cutoff.
    Releases reserved seats back to real-time inventory and updates status to REFUNDED.
    """
    payment = get_object_or_404(
        Payment.objects.select_related('movie', 'theater', 'show', 'user'),
        id=payment_id
    )

    if payment.user != request.user and not request.user.is_staff and not request.user.is_superuser:
        raise PermissionDenied("You do not have permission to refund this booking.")

    if request.method == 'POST':
        import json
        is_json = request.content_type == 'application/json' or request.headers.get('x-requested-with') == 'XMLHttpRequest'
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                data = {}
            reason = data.get('reason', 'Customer requested cancellation')
        else:
            reason = request.POST.get('reason', 'Customer requested cancellation')

        success, message, _ = RefundService.process_refund(payment, user=request.user, reason=reason)
        if is_json:
            status_code = 200 if success else 400
            return JsonResponse({'success': success, 'message': message}, status=status_code)

        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect('profile')

    # GET request: render confirmation page
    eligible, reason = RefundService.is_eligible_for_refund(payment, user=request.user)
    return render(request, 'movies/refund_confirm.html', {
        'payment': payment,
        'eligible': eligible,
        'reason': reason,
    })


@login_required(login_url='/login/')
def process_booking_refund_view(request, booking_id):
    """
    Convenience endpoint: processes cancellation and refund by booking ID.
    Delegates to payment refund flow or releases individual booking.
    """
    booking = get_object_or_404(
        Booking.objects.select_related('payment', 'user', 'seat', 'theater', 'movie', 'show'),
        id=booking_id
    )
    if booking.user != request.user and not request.user.is_staff and not request.user.is_superuser:
        raise PermissionDenied("You do not have permission to refund this booking.")

    if booking.payment:
        return process_refund_view(request, booking.payment.id)

    # Legacy booking without payment record: check cutoff
    now = timezone.now()
    cutoff_delta = timedelta(minutes=10)
    if booking.show:
        if booking.show.is_past or booking.show.is_within_cutoff:
            messages.error(request, "Refund unavailable: Cancellations close 10 minutes prior to showtime.")
            return redirect('profile')
    elif booking.theater.time:
        if booking.theater.time <= now + cutoff_delta:
            messages.error(request, "Refund unavailable: Cancellations close 10 minutes prior to showtime.")
            return redirect('profile')

    with transaction.atomic():
        seat = booking.seat
        booking.delete()
        seat.is_booked = False
        seat.locked_by = None
        seat.lock_session_key = ''
        seat.locked_until = None
        seat.save()

    messages.success(request, f"Booking for seat {seat.seat_number} has been cancelled and refunded.")
    return redirect('profile')


# ----------------------------------------------------------------------
# Rating & Review Views
# ----------------------------------------------------------------------

@login_required(login_url='/login/')
def add_review(request, slug):
    """
    Submits a rating and review for a movie.
    Strictly verifies booking/watch eligibility on the server.
    """
    movie = get_object_or_404(Movie, slug=slug, is_active=True)

    if request.method != 'POST':
        return redirect('movie_detail', slug=slug)

    # Server-side eligibility verification
    can_review, reason, is_verified = ReviewEligibilityService.check_eligibility(request.user, movie)
    if not can_review:
        messages.error(request, reason)
        return redirect('movie_detail', slug=slug)

    form = ReviewForm(request.POST)
    if form.is_valid():
        try:
            with transaction.atomic():
                review = form.save(commit=False)
                review.movie = movie
                review.user = request.user
                # Never trust frontend for verified viewer status!
                review.is_verified_viewer = is_verified
                review.is_approved = True
                review.save()
            messages.success(request, "Your rating and review have been published successfully!")
        except IntegrityError:
            messages.error(request, "You have already submitted a review for this movie.")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field.title()}: {error}")

    return redirect('movie_detail', slug=slug)


@login_required(login_url='/login/')
def edit_review(request, review_id):
    """
    Enables review owners to edit their own rating and review.
    Strictly forbids non-owners (IDOR prevention).
    """
    review = get_object_or_404(Review, id=review_id)

    # Strict ownership check
    if review.user != request.user:
        return HttpResponseForbidden("You are not authorized to edit this review.")

    if request.method == 'POST':
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            review.movie.update_rating_stats()
            messages.success(request, "Your review has been successfully updated.")
            return redirect('movie_detail', slug=review.movie.slug)
    else:
        form = ReviewForm(instance=review)

    context = {
        'form': form,
        'review': review,
        'movie': review.movie,
    }
    return render(request, 'movies/review_edit.html', context)


@login_required(login_url='/login/')
def report_review(request, review_id):
    """
    Submits a moderation report against an inappropriate review.
    Prevents duplicate reporting by the same user.
    """
    review = get_object_or_404(Review, id=review_id)

    if request.method != 'POST':
        return redirect('movie_detail', slug=review.movie.slug)

    # Prevent duplicate report abuse
    if ReviewReport.objects.filter(review=review, reporter=request.user).exists():
        messages.warning(request, "You have already submitted a report for this review.")
        return redirect('movie_detail', slug=review.movie.slug)

    form = ReviewReportForm(request.POST)
    if form.is_valid():
        report = form.save(commit=False)
        report.review = review
        report.reporter = request.user
        report.status = 'pending'
        report.save()
        messages.success(request, "Thank you. Your report has been submitted to moderators.")
    else:
        messages.error(request, "Unable to submit report. Please check the provided information.")

    return redirect('movie_detail', slug=review.movie.slug)


# ----------------------------------------------------------------------
# Administrative Management Views (Restricted to Staff)
# ----------------------------------------------------------------------

def staff_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and (u.is_staff or u.is_superuser), login_url='/login/')(view_func)


@staff_required
def admin_dashboard(request):
    """
    Custom movie management control panel with search, filters, and actions.
    """
    search = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()
    language_filter = request.GET.get('language', '').strip()

    movies = Movie.objects.all().select_related('language', 'director').prefetch_related('genres')

    if search:
        movies = movies.filter(
            Q(title__icontains=search) |
            Q(name__icontains=search) |
            Q(director_name__icontains=search)
        )

    if status_filter == 'active':
        movies = movies.filter(is_active=True)
    elif status_filter == 'inactive':
        movies = movies.filter(is_active=False)

    if language_filter:
        movies = movies.filter(language__id=language_filter)

    paginator = Paginator(movies, 15)
    page = paginator.get_page(request.GET.get('page'))

    for m in page:
        m.theaters_count = Theater.objects.filter(Q(movie=m) | Q(shows__movie=m)).distinct().count()

    languages = Language.objects.filter(is_active=True)
    pending_reports_count = ReviewReport.objects.filter(status='pending').count()

    total_revenue_stats = Payment.objects.filter(status='SUCCESS').aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))

    context = {
        'movies': page,
        'search': search,
        'status_filter': status_filter,
        'language_filter': language_filter,
        'languages': languages,
        'total_movies': Movie.objects.count(),
        'total_reviews': Review.objects.count(),
        'pending_reports_count': pending_reports_count,
        'total_theaters': Theater.objects.count(),
        'total_screens': Screen.objects.count(),
        'total_shows': ShowSchedule.objects.count(),
        'total_bookings': Booking.objects.count(),
        'total_revenue': total_revenue_stats['total'],
    }
    return render(request, 'movies/admin/dashboard.html', context)


@staff_required
def admin_analytics_dashboard(request):
    """
    Comprehensive real-time business intelligence dashboard:
    - Revenue metrics: daily, weekly, monthly, yearly, filtered period, and all-time
    - Interactive date filtering (today, 7d, 30d, month, year, all, custom date range)
    - Booking time-series trends
    - Auditorium occupancy percentages per theater
    - Most booked movies & box office rankings
    - Top performing theater audis
    - Peak booking hours & rush windows
    - Cancellation, failure, and refund statistics
    - User growth velocity & active booker conversion
    """
    import json
    preset = request.GET.get('preset', '30days')
    custom_start = request.GET.get('start_date')
    custom_end = request.GET.get('end_date')

    start_date, end_date, active_preset, date_label = BusinessAnalyticsService.parse_date_range(
        preset=preset,
        custom_start=custom_start,
        custom_end=custom_end
    )

    revenue_summary = BusinessAnalyticsService.get_revenue_summary(start_date, end_date)
    booking_trends = BusinessAnalyticsService.get_booking_trends(start_date, end_date)
    theaters, avg_occupancy, total_network_seats, total_network_booked = (
        BusinessAnalyticsService.get_theater_occupancy_breakdown(start_date, end_date)
    )
    top_movies = BusinessAnalyticsService.get_most_booked_movies(start_date, end_date, limit=10)
    top_theaters = BusinessAnalyticsService.get_top_performing_theaters(start_date, end_date, limit=10)
    peak_hours = BusinessAnalyticsService.get_peak_booking_hours(start_date, end_date)
    attrition_stats = BusinessAnalyticsService.get_cancellation_and_refund_statistics(start_date, end_date)
    user_growth = BusinessAnalyticsService.get_user_growth_reports(start_date, end_date)

    pending_reports_count = ReviewReport.objects.filter(status='pending').count()

    context = {
        'start_date': start_date,
        'end_date': end_date,
        'start_date_str': start_date.strftime('%Y-%m-%d'),
        'end_date_str': end_date.strftime('%Y-%m-%d'),
        'active_preset': active_preset,
        'date_label': date_label,
        'revenue': revenue_summary,
        'booking_trends': booking_trends,
        'theaters': theaters,
        'avg_occupancy': avg_occupancy,
        'total_network_seats': total_network_seats,
        'total_network_booked': total_network_booked,
        'top_movies': top_movies,
        'top_theaters': top_theaters,
        'peak_hours': peak_hours,
        'attrition': attrition_stats,
        'user_growth': user_growth,
        'pending_reports_count': pending_reports_count,
        'booking_trends_json': json.dumps(booking_trends, default=str),
        'peak_hours_json': json.dumps(peak_hours['hours'], default=str),
    }
    return render(request, 'movies/admin/analytics.html', context)


@staff_required
def admin_analytics_export_csv(request):
    """
    Exports executive analytics and operational audit reports as CSV.
    Supports:
    - 'summary': High-level executive KPI brief
    - 'theaters': Theater capacities, occupancy rates, and revenue
    - 'movies': Movies performance, ticket volumes, box office
    - 'hourly': Temporal distribution across 24-hour cycle
    - 'transactions': Complete ledger of payment transactions
    """
    report_type = (request.GET.get('report_type') or request.GET.get('report') or 'summary').lower()
    preset = request.GET.get('preset', '30days')
    custom_start = request.GET.get('start_date')
    custom_end = request.GET.get('end_date')

    start_date, end_date, _, _ = BusinessAnalyticsService.parse_date_range(
        preset=preset,
        custom_start=custom_start,
        custom_end=custom_end
    )

    csv_data = BusinessAnalyticsService.export_csv(
        report_type=report_type,
        start_date=start_date,
        end_date=end_date
    )

    filename = f"cineva_{report_type}_report_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response = HttpResponse(csv_data, content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@staff_required
def admin_movie_create(request):
    """
    Creates a new movie with organized sections and secure validation.
    """
    if request.method == 'POST':
        form = MovieForm(request.POST, request.FILES)
        if form.is_valid():
            movie = form.save()
            messages.success(request, f"Movie '{movie.title}' created successfully!")
            return redirect('movie_admin_gallery', movie_id=movie.id)
    else:
        form = MovieForm()

    return render(request, 'movies/admin/movie_form.html', {
        'form': form,
        'action_title': 'Add New Movie',
    })


@staff_required
def admin_movie_edit(request, movie_id):
    """
    Edits an existing movie.
    """
    movie = get_object_or_404(Movie, id=movie_id)
    if request.method == 'POST':
        form = MovieForm(request.POST, request.FILES, instance=movie)
        if form.is_valid():
            movie = form.save()
            messages.success(request, f"Movie '{movie.title}' updated successfully!")
            return redirect('movie_admin_dashboard')
    else:
        form = MovieForm(instance=movie)

    return render(request, 'movies/admin/movie_form.html', {
        'form': form,
        'movie': movie,
        'action_title': f"Edit Movie: {movie.title}",
    })


@staff_required
def admin_movie_toggle_status(request, movie_id):
    """
    Quickly toggles movie active/inactive status.
    """
    if request.method == 'POST':
        movie = get_object_or_404(Movie, id=movie_id)
        movie.is_active = not movie.is_active
        movie.save(update_fields=['is_active'])
        status_str = "activated" if movie.is_active else "deactivated"
        messages.success(request, f"Movie '{movie.title}' has been {status_str}.")
    return redirect('movie_admin_dashboard')


@staff_required
def admin_movie_delete(request, movie_id):
    """
    Safely removes or permanently deletes a movie with protection for theaters and customer bookings.
    """
    movie = get_object_or_404(Movie, id=movie_id)
    bookings_count = Booking.objects.filter(movie=movie).count()
    shows_count = ShowSchedule.objects.filter(movie=movie).count()
    assigned_theaters = Theater.objects.filter(Q(movie=movie) | Q(shows__movie=movie)).distinct()

    if request.method == 'POST':
        action = request.POST.get('action', 'soft')
        if action == 'hard':
            # Detach any theaters so deleting movie never cascade-deletes physical theaters!
            Theater.objects.filter(movie=movie).update(movie=None)
            movie_title = movie.title
            movie.delete()
            messages.success(request, f"Movie '{movie_title}' has been permanently deleted from database.")
        else:
            # Soft delete: deactivate movie
            movie.is_active = False
            movie.save(update_fields=['is_active'])
            messages.success(request, f"Movie '{movie.title}' has been deactivated and removed from public listings.")
        return redirect('movie_admin_dashboard')

    return render(request, 'movies/admin/movie_confirm_delete.html', {
        'movie': movie,
        'bookings_count': bookings_count,
        'shows_count': shows_count,
        'assigned_theaters_count': assigned_theaters.count(),
        'assigned_theaters': assigned_theaters,
    })


@staff_required
def admin_movie_assign_theaters(request, movie_id):
    """
    Dedicated view to assign theaters to a movie and auto-schedule showtimes.
    """
    movie = get_object_or_404(Movie, id=movie_id)
    all_theaters = Theater.objects.all().order_by('city', 'name').prefetch_related('screens')

    # Theaters currently showing this movie
    currently_assigned_ids = set(
        Theater.objects.filter(Q(movie=movie) | Q(shows__movie=movie)).values_list('id', flat=True)
    )

    if request.method == 'POST':
        selected_theater_ids = [int(tid) for tid in request.POST.getlist('theater_ids') if tid.isdigit()]
        auto_create_shows = request.POST.get('auto_create_shows') == '1'
        try:
            days_ahead = int(request.POST.get('days_ahead', 3))
            days_ahead = max(1, min(7, days_ahead))
        except (ValueError, TypeError):
            days_ahead = 3

        try:
            ticket_price = Decimal(request.POST.get('ticket_price', '180.00'))
        except (ValueError, TypeError, InvalidOperation):
            ticket_price = Decimal('180.00')

        # 1. Update Theater.movie links
        for th in all_theaters:
            if th.id in selected_theater_ids:
                if not th.movie:
                    th.movie = movie
                    th.save(update_fields=['movie'])
                TheaterSeatingService.ensure_full_theater_layout(th)
            else:
                # If theater had this movie as its primary, detach it
                if th.movie_id == movie.id:
                    th.movie = None
                    th.save(update_fields=['movie'])

        # 2. If auto_create_shows requested, create show schedules for selected theaters
        created_shows_count = 0
        if auto_create_shows and selected_theater_ids:
            today = timezone.localdate()
            time_slots = [(10, 15), (13, 45), (17, 30), (21, 15)]
            duration_mins = movie.duration or 120

            for tid in selected_theater_ids:
                th = next((t for t in all_theaters if t.id == tid), None)
                if not th:
                    continue
                screens = list(th.screens.all())
                if not screens:
                    screen1 = Screen.objects.create(theater=th, name="Audi 1 (IMAX)", screen_type="IMAX", seating_capacity=100)
                    screens.append(screen1)

                for day_idx in range(days_ahead):
                    target_date = today + timedelta(days=day_idx)
                    for screen in screens:
                        for h, m in time_slots:
                            start_dt = timezone.make_aware(datetime.combine(target_date, time(h, m)))
                            end_dt = start_dt + timedelta(minutes=duration_mins + 20)

                            conflict = ShowSchedule.objects.filter(
                                screen=screen,
                                status__in=['scheduled', 'open'],
                                start_time__lt=end_dt,
                                end_time__gt=start_dt
                            ).exists()

                            if not conflict:
                                ShowSchedule.objects.create(
                                    movie=movie,
                                    theater=th,
                                    screen=screen,
                                    start_time=start_dt,
                                    end_time=end_dt,
                                    price=ticket_price,
                                    status='open'
                                )
                                created_shows_count += 1

        messages.success(
            request,
            f"Updated theater assignments for '{movie.title}'. "
            f"Assigned to {len(selected_theater_ids)} theaters. "
            f"{f'Generated {created_shows_count} show schedules.' if auto_create_shows else ''}"
        )
        return redirect('movie_admin_assign_theaters', movie_id=movie.id)

    # Active upcoming show schedules for this movie
    upcoming_shows = ShowSchedule.objects.filter(
        movie=movie,
        start_time__gte=timezone.now()
    ).select_related('theater', 'screen').order_by('start_time')[:30]

    return render(request, 'movies/admin/assign_theaters.html', {
        'movie': movie,
        'theaters': all_theaters,
        'currently_assigned_ids': currently_assigned_ids,
        'upcoming_shows': upcoming_shows,
    })


@staff_required
def admin_movie_gallery(request, movie_id):
    """
    Gallery manager: upload images, designate primary poster, change ordering, delete.
    """
    movie = get_object_or_404(Movie, id=movie_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'upload':
            form = MovieImageForm(request.POST, request.FILES)
            if form.is_valid():
                img = form.save(commit=False)
                img.movie = movie
                img.save()
                messages.success(request, "Image uploaded to gallery successfully.")
                return redirect('movie_admin_gallery', movie_id=movie.id)
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field.title()}: {error}")

        elif action == 'set_primary':
            image_id = request.POST.get('image_id')
            img = get_object_or_404(MovieImage, id=image_id, movie=movie)
            img.is_primary = True
            img.save()
            messages.success(request, "Primary poster updated.")
            return redirect('movie_admin_gallery', movie_id=movie.id)

        elif action == 'update_order':
            image_id = request.POST.get('image_id')
            order = request.POST.get('display_order', 0)
            try:
                order_val = int(order)
                img = get_object_or_404(MovieImage, id=image_id, movie=movie)
                img.display_order = max(0, order_val)
                img.save(update_fields=['display_order'])
                messages.success(request, "Display order updated.")
            except ValueError:
                messages.error(request, "Invalid order number.")
            return redirect('movie_admin_gallery', movie_id=movie.id)

        elif action == 'delete':
            image_id = request.POST.get('image_id')
            img = get_object_or_404(MovieImage, id=image_id, movie=movie)
            img.delete()
            messages.success(request, "Image removed from gallery.")
            return redirect('movie_admin_gallery', movie_id=movie.id)

    upload_form = MovieImageForm()
    images = movie.gallery_images.all().order_by('display_order', '-created_at')

    context = {
        'movie': movie,
        'images': images,
        'upload_form': upload_form,
    }
    return render(request, 'movies/admin/gallery_manager.html', context)


@staff_required
def admin_reports_list(request):
    """
    Moderation queue for reported user reviews.
    """
    status = request.GET.get('status', 'pending')
    reports = ReviewReport.objects.all().select_related('review__movie', 'review__user', 'reporter')

    if status in ['pending', 'reviewed', 'dismissed', 'action_taken']:
        reports = reports.filter(status=status)

    paginator = Paginator(reports, 20)
    page = paginator.get_page(request.GET.get('page'))

    context = {
        'reports': page,
        'current_status': status,
        'pending_count': ReviewReport.objects.filter(status='pending').count(),
    }
    return render(request, 'movies/admin/reports_list.html', context)


@staff_required
def admin_report_action(request, report_id):
    """
    Processes moderation actions on reported reviews:
    Dismiss report or Hide review.
    """
    report = get_object_or_404(ReviewReport, id=report_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        notes = request.POST.get('moderator_notes', '').strip()

        if action == 'dismiss':
            report.status = 'dismissed'
            report.moderator_notes = notes
            report.action_taken_by = request.user
            report.save()
            messages.success(request, f"Report #{report.id} dismissed.")

        elif action == 'hide_review':
            report.status = 'action_taken'
            report.moderator_notes = notes
            report.action_taken_by = request.user
            report.save()

            review = report.review
            review.is_approved = False
            review.save()
            review.movie.update_rating_stats()
            messages.success(request, f"Review hidden from public view and report marked as action taken.")

    return redirect('movie_admin_reports')


# ----------------------------------------------------------------------
# Theaters & Multiplexes Management (Cineva Ops)
# ----------------------------------------------------------------------

@staff_required
def admin_theaters_list(request):
    """
    Cineva Ops control panel for theaters / venues.
    """
    search = request.GET.get('search', '').strip()
    theaters = Theater.objects.all().prefetch_related('screens').select_related('movie')
    if search:
        theaters = theaters.filter(Q(name__icontains=search) | Q(city__icontains=search) | Q(address__icontains=search))
    theaters = theaters.order_by('city', 'name')
    paginator = Paginator(theaters, 15)
    page = paginator.get_page(request.GET.get('page'))

    for th in page:
        th.shows_count = ShowSchedule.objects.filter(theater=th).count()

    return render(request, 'movies/admin/theaters_list.html', {
        'theaters': page,
        'search': search,
        'total_theaters': Theater.objects.count(),
        'total_screens': Screen.objects.count(),
        'active_theaters': Theater.objects.filter(is_active=True).count(),
        'total_shows': ShowSchedule.objects.count(),
    })


@staff_required
def admin_theater_create(request):
    """
    Creates a new theater with auditoriums and full seating layout.
    """
    if request.method == 'POST':
        form = TheaterForm(request.POST)
        if form.is_valid():
            theater = form.save()
            num_screens = form.cleaned_data.get('num_screens') or 2
            screen_types = ['IMAX', '4DX', 'Dolby Atmos', '2D Standard', '3D Digital']
            for i in range(1, num_screens + 1):
                stype = screen_types[(i - 1) % len(screen_types)]
                Screen.objects.create(
                    theater=theater,
                    name=f"Audi {i} ({stype.split()[0]})",
                    screen_type=stype.split()[0],
                    seating_capacity=100
                )
            TheaterSeatingService.ensure_full_theater_layout(theater)
            messages.success(request, f"Theater '{theater.name}' created with {num_screens} screens and seating layout!")
            return redirect('admin_theaters_list')
    else:
        form = TheaterForm()

    return render(request, 'movies/admin/theater_form.html', {
        'form': form,
        'action_title': 'Add New Multiplex / Venue',
    })


@staff_required
def admin_theater_edit(request, theater_id):
    """
    Edits an existing theater.
    """
    theater = get_object_or_404(Theater, id=theater_id)
    if request.method == 'POST':
        form = TheaterForm(request.POST, instance=theater)
        if form.is_valid():
            theater = form.save()
            TheaterSeatingService.ensure_full_theater_layout(theater)
            messages.success(request, f"Theater '{theater.name}' updated successfully!")
            return redirect('admin_theaters_list')
    else:
        form = TheaterForm(instance=theater)

    return render(request, 'movies/admin/theater_form.html', {
        'form': form,
        'theater': theater,
        'action_title': f"Edit Theater: {theater.name}",
    })


@staff_required
def admin_theater_delete(request, theater_id):
    """
    Removes or deactivates a theater.
    """
    theater = get_object_or_404(Theater, id=theater_id)
    bookings_count = Booking.objects.filter(theater=theater).count()
    shows_count = ShowSchedule.objects.filter(theater=theater).count()

    if request.method == 'POST':
        action = request.POST.get('action', 'soft')
        if action == 'hard':
            name = theater.name
            theater.delete()
            messages.success(request, f"Theater '{name}' permanently deleted.")
        else:
            theater.is_active = False
            theater.save(update_fields=['is_active'])
            messages.success(request, f"Theater '{theater.name}' deactivated.")
        return redirect('admin_theaters_list')

    return render(request, 'movies/admin/theater_confirm_delete.html', {
        'theater': theater,
        'bookings_count': bookings_count,
        'shows_count': shows_count,
    })


@staff_required
def admin_theater_toggle_status(request, theater_id):
    """
    Quickly toggles theater active/inactive status.
    """
    if request.method == 'POST':
        theater = get_object_or_404(Theater, id=theater_id)
        theater.is_active = not theater.is_active
        theater.save(update_fields=['is_active'])
        status_str = "activated" if theater.is_active else "deactivated"
        messages.success(request, f"Theater '{theater.name}' has been {status_str}.")
    return redirect('admin_theaters_list')


# ----------------------------------------------------------------------
# Show Schedules Management (Cineva Ops)
# ----------------------------------------------------------------------

@staff_required
def admin_shows_list(request):
    """
    Cineva Ops control panel for Show Schedules with filtering.
    """
    movie_id = request.GET.get('movie')
    theater_id = request.GET.get('theater')
    status_filter = request.GET.get('status')

    shows = ShowSchedule.objects.all().select_related('movie', 'theater', 'screen').order_by('-start_time')
    if movie_id:
        shows = shows.filter(movie_id=movie_id)
    if theater_id:
        shows = shows.filter(theater_id=theater_id)
    if status_filter:
        shows = shows.filter(status=status_filter)

    paginator = Paginator(shows, 20)
    page = paginator.get_page(request.GET.get('page'))

    movies = Movie.objects.all().order_by('title')
    theaters = Theater.objects.all().order_by('name')

    return render(request, 'movies/admin/shows_list.html', {
        'shows': page,
        'movies': movies,
        'theaters': theaters,
        'selected_movie': movie_id,
        'selected_theater': theater_id,
        'selected_status': status_filter,
        'total_shows': ShowSchedule.objects.count(),
    })


@staff_required
def admin_show_create(request):
    """
    Creates a new show schedule with collision detection.
    """
    if request.method == 'POST':
        form = ShowScheduleForm(request.POST)
        if form.is_valid():
            show = form.save()
            messages.success(request, f"Show scheduled for '{show.movie.title}' at '{show.theater.name}' ({show.screen.name})!")
            return redirect('admin_shows_list')
    else:
        initial = {}
        if request.GET.get('movie'):
            initial['movie'] = request.GET.get('movie')
        if request.GET.get('theater'):
            initial['theater'] = request.GET.get('theater')
        form = ShowScheduleForm(initial=initial)

    return render(request, 'movies/admin/show_form.html', {
        'form': form,
        'action_title': 'Schedule New Show',
    })


@staff_required
def admin_show_edit(request, show_id):
    """
    Edits an existing show schedule.
    """
    show = get_object_or_404(ShowSchedule, id=show_id)
    if request.method == 'POST':
        form = ShowScheduleForm(request.POST, instance=show)
        if form.is_valid():
            show = form.save()
            messages.success(request, "Show schedule updated successfully!")
            return redirect('admin_shows_list')
    else:
        form = ShowScheduleForm(instance=show)

    return render(request, 'movies/admin/show_form.html', {
        'form': form,
        'show': show,
        'action_title': f"Edit Show: {show.movie.title} at {show.theater.name}",
    })


@staff_required
def admin_show_delete(request, show_id):
    """
    Deletes a show schedule.
    """
    show = get_object_or_404(ShowSchedule, id=show_id)
    if request.method == 'POST':
        show_str = f"{show.movie.title} at {show.theater.name} ({show.start_time.strftime('%b %d, %I:%M %p')})"
        show.delete()
        messages.success(request, f"Show schedule '{show_str}' has been deleted.")
        return redirect('admin_shows_list')

    return render(request, 'movies/admin/show_confirm_delete.html', {
        'show': show,
    })

