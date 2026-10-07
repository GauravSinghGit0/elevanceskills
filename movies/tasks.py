import logging
import threading
from celery import shared_task

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from .models import Booking, Payment
from .ticket_service import TicketGeneratorService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    name='movies.tasks.send_booking_ticket_email_task'
)
def send_booking_ticket_email_task(self, payment_id=None, booking_ids=None, recipient_email=None):
    """
    Asynchronous Celery task that generates and emails professional PDF tickets.
    Automatically retries up to 3 times on failure with exponential backoff.
    """
    logger.info(
        "Starting ticket email task (Attempt %s/%s) for payment_id=%s, booking_ids=%s",
        self.request.retries + 1, self.max_retries, payment_id, booking_ids
    )

    payment = None
    bookings = []

    if payment_id:
        payment = Payment.objects.filter(id=payment_id).first()
        if payment:
            bookings = list(payment.bookings.select_related('movie', 'theater', 'seat', 'show', 'user').all())

    if not bookings and booking_ids:
        bookings = list(Booking.objects.filter(id__in=booking_ids).select_related('movie', 'theater', 'seat', 'show', 'user').all())
        if bookings and not payment:
            payment = bookings[0].payment

    if not bookings:
        logger.warning("No booking records found for ticket email dispatch. Skipping.")
        return {'success': False, 'message': 'No bookings found'}

    primary_booking = bookings[0]
    user = primary_booking.user
    if not recipient_email:
        recipient_email = user.email or f"{user.username}@example.com"

    movie_title = primary_booking.movie.title or getattr(primary_booking.movie, 'name', '') or 'Movie'
    booking_ref = primary_booking.id

    # 1. Generate PDF Ticket
    pdf_bytes = TicketGeneratorService.generate_ticket_pdf(
        payment=payment,
        bookings=bookings
    )

    # 2. Generate HTML Email Body
    html_content = TicketGeneratorService.generate_ticket_email_html(
        payment=payment,
        bookings=bookings
    )

    # 3. Plaintext body fallback
    theater_name = primary_booking.theater.name
    show_time_str = primary_booking.show.start_time.strftime("%a %b %d, %Y at %I:%M %p") if primary_booking.show else "Scheduled Screening"
    seats_list = ", ".join([f"{getattr(b.seat, 'tier', 'SEAT')}-{b.seat.seat_number}" for b in bookings])

    text_content = (
        f"Thank you for booking with Cineva Cinemas!\n\n"
        f"Movie: {movie_title}\n"
        f"Cinema: {theater_name}\n"
        f"Showtime: {show_time_str}\n"
        f"Seats: {seats_list}\n"
        f"Booking ID: {booking_ref}\n\n"
        f"Your official PDF admission ticket is attached. "
        f"Please present the QR code at the cinema gate for verification.\n"
    )

    subject = f"🎟️ Ticket Confirmation: {movie_title} [Booking #{booking_ref}]"
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'Cineva Cinema <ownai63@gmail.com>')

    email_msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=from_email,
        to=[recipient_email]
    )
    email_msg.attach_alternative(html_content, "text/html")

    filename = f"ticket_cineva_{booking_ref}.pdf"
    email_msg.attach(filename, pdf_bytes, 'application/pdf')

    # Send email (exceptions trigger Celery autoretry)
    try:
        sent_count = email_msg.send(fail_silently=False)
        logger.info("Successfully sent ticket email for booking #%s to %s", booking_ref, recipient_email)
        return {
            'success': True,
            'booking_id': booking_ref,
            'recipient': recipient_email,
            'sent_count': sent_count
        }
    except Exception as exc:
        logger.error(
            "Failed to send ticket email for booking #%s to %s (Attempt %s/%s): %s",
            booking_ref, recipient_email, self.request.retries + 1, self.max_retries, exc
        )
        raise self.retry(exc=exc)


def dispatch_booking_ticket_email(payment=None, bookings=None, recipient_email=None):
    """
    Non-blocking helper that enqueues the ticket generation and email delivery task.
    Ensures the user's booking confirmation is NEVER delayed or interrupted by email delivery.
    """
    payment_id = payment.id if payment else None
    booking_ids = [b.id for b in bookings] if bookings else None

    try:
        # Enqueue via Celery worker
        send_booking_ticket_email_task.delay(
            payment_id=payment_id,
            booking_ids=booking_ids,
            recipient_email=recipient_email
        )
        logger.info("Enqueued Celery ticket email task for payment_id=%s, booking_ids=%s", payment_id, booking_ids)
    except Exception as e:
        logger.warning(
            "Celery broker dispatch exception: %s. Falling back to background daemon thread to avoid blocking booking flow.", e
        )
        # Background thread fallback so booking flow returns instantaneously
        def fallback_worker():
            try:
                # Call task directly in isolated background thread
                send_booking_ticket_email_task(
                    payment_id=payment_id,
                    booking_ids=booking_ids,
                    recipient_email=recipient_email
                )
            except Exception as thread_exc:
                logger.error("Fallback ticket email thread failed: %s", thread_exc)

        t = threading.Thread(target=fallback_worker, daemon=True)
        t.start()
