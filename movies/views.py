import json
import os
from decimal import Decimal, InvalidOperation

import razorpay
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Booking, Movie, PaymentTransaction, Seat, Theater


def movie_list(request):
    search_query = request.GET.get('search')
    movies = Movie.objects.filter(name__icontains=search_query) if search_query else Movie.objects.all()
    return render(request, 'movies/movie_list.html', {'movies': movies})


def theater_list(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    theaters = Theater.objects.filter(movie=movie)
    return render(request, 'movies/theater_list.html', {'movie': movie, 'theaters': theaters})


def razorpay_client():
    key_id = os.environ.get('RAZORPAY_KEY_ID')
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET')
    if not key_id or not key_secret:
        raise RuntimeError('Razorpay environment variables are not configured.')
    return razorpay.Client(auth=(key_id, key_secret))


def booking_price_paise():
    try:
        amount = Decimal(os.environ.get('BOOKING_PRICE_INR', '100'))
    except InvalidOperation:
        amount = Decimal('100')
    return int(amount * 100)


@login_required(login_url='/login/')
def book_seats(request, theater_id):
    theater = get_object_or_404(Theater, id=theater_id)
    seats = Seat.objects.filter(theater=theater).order_by('id')
    return render(request, 'movies/seat_selection.html', {
        'theater': theater,
        'seats': seats,
        'razorpay_key_id': os.environ.get('RAZORPAY_KEY_ID', ''),
        'booking_price_inr': booking_price_paise() / 100,
    })


@login_required(login_url='/login/')
def create_payment_order(request, theater_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)

    theater = get_object_or_404(Theater, id=theater_id)
    try:
        selected_ids = [int(value) for value in request.POST.getlist('seats')]
        if not selected_ids:
            raise ValueError
        with transaction.atomic():
            selected_seats = list(Seat.objects.select_for_update().filter(
                id__in=selected_ids, theater=theater, is_booked=False
            ))
            if len(selected_seats) != len(set(selected_ids)):
                return JsonResponse({'error': 'One or more selected seats are no longer available.'}, status=409)

            amount_paise = len(selected_seats) * booking_price_paise()
            order = razorpay_client().order.create({
                'amount': amount_paise,
                'currency': 'INR',
                'receipt': f'booking-{request.user.id}-{timezone.now().timestamp()}',
                'notes': {'theater_id': str(theater.id), 'user_id': str(request.user.id)},
            })
            PaymentTransaction.objects.create(
                user=request.user,
                theater=theater,
                seat_ids=[seat.id for seat in selected_seats],
                amount_paise=amount_paise,
                razorpay_order_id=order['id'],
            )
        return JsonResponse({
            'key_id': os.environ.get('RAZORPAY_KEY_ID'),
            'order_id': order['id'],
            'amount': amount_paise,
            'currency': 'INR',
            'movie': theater.movie.name,
            'theater': theater.name,
        })
    except RuntimeError as exc:
        return JsonResponse({'error': str(exc)}, status=503)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Please select at least one valid seat.'}, status=400)


@login_required(login_url='/login/')
def verify_payment(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)
    try:
        payload = json.loads(request.body.decode('utf-8'))
        order_id = payload['razorpay_order_id']
        payment_id = payload['razorpay_payment_id']
        signature = payload['razorpay_signature']
        razorpay_client().utility.verify_payment_signature({
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature,
        })

        with transaction.atomic():
            payment = PaymentTransaction.objects.select_for_update().get(
                razorpay_order_id=order_id, user=request.user
            )
            if payment.status == 'paid':
                return JsonResponse({'success': True})
            seats = list(Seat.objects.select_for_update().filter(
                id__in=payment.seat_ids, theater=payment.theater
            ))
            if len(seats) != len(payment.seat_ids) or any(seat.is_booked for seat in seats):
                payment.status = 'failed'
                payment.save(update_fields=['status'])
                return JsonResponse({'error': 'A selected seat is no longer available.'}, status=409)
            for seat in seats:
                Booking.objects.create(user=request.user, seat=seat, movie=payment.theater.movie, theater=payment.theater)
                seat.is_booked = True
                seat.save(update_fields=['is_booked'])
            payment.status = 'paid'
            payment.razorpay_payment_id = payment_id
            payment.paid_at = timezone.now()
            payment.save(update_fields=['status', 'razorpay_payment_id', 'paid_at'])
        return JsonResponse({'success': True, 'redirect_url': '/profile/'})
    except (KeyError, ValueError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid payment response.'}, status=400)
    except PaymentTransaction.DoesNotExist:
        return JsonResponse({'error': 'Payment order not found.'}, status=404)
    except Exception:
        return JsonResponse({'error': 'Payment verification failed.'}, status=400)
