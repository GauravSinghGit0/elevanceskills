import json
import razorpay
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from .models import Booking, Movie, PaymentTransaction, Seat, Theater


def movie_list(request):
    query = request.GET.get('search')
    movies = Movie.objects.filter(name__icontains=query) if query else Movie.objects.all()
    return render(request, 'movies/movie_list.html', {'movies': movies})


def theater_list(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    return render(request, 'movies/theater_list.html', {'movie': movie, 'theaters': Theater.objects.filter(movie=movie)})


def client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise RuntimeError('Razorpay environment variables are not configured.')
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def default_price():
    try:
        return Decimal(settings.DEFAULT_SEAT_PRICE_INR)
    except (InvalidOperation, TypeError):
        return Decimal('100.00')


@login_required(login_url='/login/')
def book_seats(request, theater_id):
    theater = get_object_or_404(Theater, id=theater_id)
    seats = Seat.objects.filter(theater=theater)
    return render(request, 'movies/seat_selection.html', {
        'theater': theater, 'seats': seats, 'razorpay_key_id': settings.RAZORPAY_KEY_ID,
    })


@login_required(login_url='/login/')
def create_payment_order(request, theater_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)
    theater = get_object_or_404(Theater, id=theater_id)
    try:
        selected_ids = list(dict.fromkeys(int(value) for value in request.POST.getlist('seats')))
        if not selected_ids:
            return JsonResponse({'error': 'Select at least one seat.'}, status=400)
        with transaction.atomic():
            seats = list(Seat.objects.select_for_update().filter(id__in=selected_ids, theater=theater, is_booked=False))
            if len(seats) != len(selected_ids):
                return JsonResponse({'error': 'One or more selected seats are unavailable.'}, status=409)
            amount_paise = sum(int(seat.price * 100) for seat in seats)
            order = client().order.create({
                'amount': amount_paise, 'currency': 'INR',
                'receipt': f'booking-{request.user.id}-{timezone.now().strftime("%Y%m%d%H%M%S%f")}',
                'notes': {'theater_id': str(theater.id), 'user_id': str(request.user.id)},
            })
            PaymentTransaction.objects.create(user=request.user, theater=theater,
                seat_ids=[seat.id for seat in seats], amount_paise=amount_paise, razorpay_order_id=order['id'])
        return JsonResponse({'key_id': settings.RAZORPAY_KEY_ID, 'order_id': order['id'],
            'amount': amount_paise, 'currency': 'INR', 'movie': theater.movie.name, 'theater': theater.name})
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid seat selection.'}, status=400)
    except RuntimeError as exc:
        return JsonResponse({'error': str(exc)}, status=503)
    except Exception:
        return JsonResponse({'error': 'Could not create payment order.'}, status=502)


@login_required(login_url='/login/')
def verify_payment(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8'))
        client().utility.verify_payment_signature({
            'razorpay_order_id': data['razorpay_order_id'],
            'razorpay_payment_id': data['razorpay_payment_id'],
            'razorpay_signature': data['razorpay_signature'],
        })
        with transaction.atomic():
            payment = PaymentTransaction.objects.select_for_update().get(
                razorpay_order_id=data['razorpay_order_id'], user=request.user)
            if payment.status == 'paid':
                return JsonResponse({'success': True, 'redirect_url': '/profile/'})
            seats = list(Seat.objects.select_for_update().filter(id__in=payment.seat_ids, theater=payment.theater))
            if len(seats) != len(payment.seat_ids) or any(seat.is_booked for seat in seats):
                payment.status = 'failed'; payment.save(update_fields=['status'])
                return JsonResponse({'error': 'A selected seat is no longer available.'}, status=409)
            for seat in seats:
                Booking.objects.create(user=request.user, seat=seat, movie=payment.theater.movie, theater=payment.theater)
                seat.is_booked = True; seat.save(update_fields=['is_booked'])
            payment.status = 'paid'; payment.razorpay_payment_id = data['razorpay_payment_id']; payment.paid_at = timezone.now()
            payment.save(update_fields=['status', 'razorpay_payment_id', 'paid_at'])
        return JsonResponse({'success': True, 'redirect_url': '/profile/'})
    except (KeyError, ValueError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid payment response.'}, status=400)
    except PaymentTransaction.DoesNotExist:
        return JsonResponse({'error': 'Payment order not found.'}, status=404)
    except Exception:
        return JsonResponse({'error': 'Payment verification failed.'}, status=400)
