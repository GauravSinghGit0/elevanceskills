import io
import hmac
import hashlib
import base64
from decimal import Decimal
from datetime import datetime

import qrcode
from PIL import Image

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.template.loader import render_to_string


class TicketGeneratorService:
    """
    Automated high-fidelity cinema ticket and admission pass generator.
    Produces:
    - Verifiable QR codes
    - Professional, printable PDF tickets matching the cinema ticket standard
    - Rich, responsive HTML confirmation emails with inline ticket presentation
    - Cryptographic HMAC verification for cinema gate check-in scanners
    """

    @classmethod
    def get_verification_token(cls, booking_id: int, user_id: int, movie_id: int) -> str:
        """
        Generates a 16-character HMAC token to prevent tampering with QR code verification URLs.
        """
        secret = getattr(settings, 'SECRET_KEY', 'bookmyseat-secret-key').encode('utf-8')
        msg = f"ticket:{booking_id}:{user_id}:{movie_id}".encode('utf-8')
        return hmac.new(secret, msg, hashlib.sha256).hexdigest()[:16]

    @classmethod
    def verify_ticket_token(cls, booking, token: str) -> bool:
        """
        Validates token against booking record.
        """
        if not booking or not token:
            return False
        expected = cls.get_verification_token(booking.id, booking.user_id, booking.movie_id)
        return hmac.compare_digest(token.strip(), expected)

    @classmethod
    def get_verification_url(cls, booking, request=None) -> str:
        """
        Constructs the verification URL embedded into the QR code.
        """
        token = cls.get_verification_token(booking.id, booking.user_id, booking.movie_id)
        path = reverse('verify_ticket', args=[booking.id])
        full_path = f"{path}?token={token}"

        if request:
            return request.build_absolute_uri(full_path)
        return f"http://127.0.0.1:8000{full_path}"

    @classmethod
    def generate_qr_code_image(cls, data: str, box_size: int = 8, border: int = 2) -> io.BytesIO:
        """
        Generates PNG image bytes of QR code.
        """
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    @classmethod
    def generate_qr_code_base64(cls, data: str) -> str:
        """
        Generates base64 data URI for inline HTML rendering.
        """
        buf = cls.generate_qr_code_image(data, box_size=6, border=2)
        b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        return f"data:image/png;base64,{b64}"

    @classmethod
    def _extract_ticket_data(cls, booking=None, payment=None, bookings=None, request=None):
        """
        Normalizes single booking or multi-seat payment booking into structured dictionary.
        """
        if booking:
            bookings_list = [booking]
            payment_obj = booking.payment
            user = booking.user
            movie = booking.movie
            theater = booking.theater
            show = booking.show
        elif payment:
            bookings_list = list(payment.bookings.select_related('movie', 'theater', 'seat', 'show', 'user').all())
            payment_obj = payment
            user = payment.user
            movie = payment.movie
            theater = payment.theater
            show = payment.show
        elif bookings:
            bookings_list = list(bookings)
            first_b = bookings_list[0]
            payment_obj = first_b.payment
            user = first_b.user
            movie = first_b.movie
            theater = first_b.theater
            show = first_b.show
        else:
            raise ValueError("Must provide booking, payment, or bookings list.")

        primary_b = bookings_list[0]

        # Seat strings
        seat_labels = []
        for b in bookings_list:
            tier_label = getattr(b.seat, 'tier', 'SEAT')
            seat_labels.append(f"{tier_label}-{b.seat.seat_number}")
        seats_str = ", ".join(seat_labels)

        # Timings
        booking_time = primary_b.booked_at if primary_b.booked_at else timezone.now()
        if show and show.start_time:
            show_dt_str = show.start_time.strftime("%a %b %d, %Y %I:%M %p")
        elif theater and theater.time:
            show_dt_str = theater.time.strftime("%a %b %d, %Y %I:%M %p")
        else:
            show_dt_str = booking_time.strftime("%a %b %d, %Y %I:%M %p")

        txn_dt_str = booking_time.strftime("%a %d %b %Y @ %I:%M %p")

        # Screen & Audio
        screen_name = "Screen 1"
        screen_type = "2D Standard"
        if show and show.screen:
            screen_name = show.screen.name
            screen_type = show.screen.get_screen_type_display() if hasattr(show.screen, 'get_screen_type_display') else show.screen.screen_type

        # Pricing
        if payment_obj:
            gross_amount = payment_obj.amount
            payment_mode = f"{payment_obj.gateway} ({payment_obj.payment_method.upper()})"
            payment_ref = payment_obj.transaction_id or payment_obj.order_id
            order_id = payment_obj.order_id
        else:
            gross_amount = sum(b.seat.price for b in bookings_list if b.seat)
            payment_mode = "Razorpay Test"
            payment_ref = f"REF-{primary_b.id}"
            order_id = f"ORD-{primary_b.id}"

        # Tax calculation
        conv_fee = (gross_amount * Decimal('0.10')).quantize(Decimal('0.01'))
        nett_amount = (gross_amount - conv_fee).quantize(Decimal('0.01'))

        # Movie details
        movie_title = movie.title or getattr(movie, 'name', '') or 'Cinema Premiere'
        age_cert = getattr(movie, 'age_certification', 'UA')
        full_movie_name = f"{movie_title} ({age_cert})"
        cinema_name = f"Cineva: {theater.name}" + (f", {theater.city}" if theater.city else "")

        # Verification URL
        verify_url = cls.get_verification_url(primary_b, request=request)

        # Booking IDs
        b_ids = [str(b.id) for b in bookings_list]
        booking_id_str = b_ids[0] if len(b_ids) == 1 else f"{b_ids[0]} (+{len(b_ids)-1})"
        ticket_number_str = f"TCK-{primary_b.id:06d}"

        customer_name = user.get_full_name() or user.username
        customer_email = user.email or f"{user.username}@example.com"

        return {
            'primary_booking': primary_b,
            'bookings_count': len(bookings_list),
            'movie_title': movie_title,
            'full_movie_name': full_movie_name,
            'cinema_name': cinema_name,
            'screen_name': screen_name,
            'screen_type': screen_type,
            'show_dt_str': show_dt_str,
            'txn_dt_str': txn_dt_str,
            'seats_str': seats_str,
            'booking_id_str': booking_id_str,
            'ticket_number_str': ticket_number_str,
            'gross_amount': f"Rs. {gross_amount:.2f}",
            'nett_amount': f"Rs. {nett_amount:.2f}",
            'conv_fee': f"Rs. {conv_fee:.2f}",
            'payment_mode': payment_mode,
            'payment_ref': payment_ref,
            'order_id': order_id,
            'customer_name': customer_name,
            'customer_email': customer_email,
            'verify_url': verify_url,
        }

    @classmethod
    def generate_ticket_pdf(cls, booking=None, payment=None, bookings=None, request=None) -> bytes:
        """
        Renders an authentic, vector PDF cinema admission ticket modeled
        on the BookMyShow / Wave Cinemas standard ticket format.
        """
        data = cls._extract_ticket_data(booking=booking, payment=payment, bookings=bookings, request=request)

        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        page_width, page_height = letter

        # Draw a single or dual-pass ticket slip on the letter page
        cls._draw_ticket_slip(p, data, y_offset=page_height - 350)

        p.showPage()
        p.save()

        buffer.seek(0)
        return buffer.getvalue()

    @classmethod
    def _draw_ticket_slip(cls, p, data, y_offset):
        """
        Draws the ticket slip box with precise dimensions and layout.
        """
        margin_x = 36
        slip_width = letter[0] - (2 * margin_x)  # 540 pt
        slip_height = 320  # 320 pt

        box_x = margin_x
        box_y = y_offset

        # 1. Outer Ticket Border
        p.setStrokeColor(colors.HexColor('#222222'))
        p.setLineWidth(1.2)
        p.rect(box_x, box_y, slip_width, slip_height)

        # 2. Header Band
        # Left: Screen / Auditorium Identifier
        p.setFont("Helvetica-Bold", 14)
        p.setFillColor(colors.HexColor('#111827'))
        p.drawString(box_x + 16, box_y + slip_height - 28, f"{data['screen_name'].upper()}")

        # Right: Cinema Brand
        p.setFont("Helvetica-Bold", 13)
        p.setFillColor(colors.HexColor('#881337')) # Deep cinema red
        brand_text = "CINEVA"
        p.drawRightString(box_x + slip_width - 16, box_y + slip_height - 24, brand_text)
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawRightString(box_x + slip_width - 16, box_y + slip_height - 36, "PREMIUM CINEMAS")

        # Header dividing line
        p.setLineWidth(0.8)
        p.setStrokeColor(colors.HexColor('#374151'))
        p.line(box_x, box_y + slip_height - 46, box_x + slip_width, box_y + slip_height - 46)

        # 3. Content Grid
        content_top = box_y + slip_height - 68
        line_height = 20

        # Column positions
        col1_label_x = box_x + 16
        col1_val_x = box_x + 115

        col2_label_x = box_x + 280
        col2_val_x = box_x + 365

        # Row 1: Movie Name & Booking ID
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawString(col1_label_x, content_top, "Movie Name")
        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(colors.black)
        # Truncate title if extremely long
        movie_display = data['full_movie_name']
        if len(movie_display) > 28:
            movie_display = movie_display[:26] + "..."
        p.drawString(col1_val_x, content_top, movie_display)

        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawString(col2_label_x, content_top, "Booking ID")
        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(colors.black)
        p.drawString(col2_val_x, content_top, data['booking_id_str'])

        # Row 2: Cinema Name & Gross Tickets Total
        r2_y = content_top - line_height
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawString(col1_label_x, r2_y, "Cinema Name")
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.black)
        cinema_display = data['cinema_name']
        if len(cinema_display) > 28:
            cinema_display = cinema_display[:26] + "..."
        p.drawString(col1_val_x, r2_y, cinema_display)

        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawString(col2_label_x, r2_y, "Gross Total")
        p.setFont("Helvetica-Bold", 9)
        p.setFillColor(colors.black)
        p.drawString(col2_val_x, r2_y, data['gross_amount'])

        # Row 3: Show Date & Time & Nett Total
        r3_y = r2_y - line_height
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawString(col1_label_x, r3_y, "Show Date & Time")
        p.setFont("Helvetica-Bold", 9)
        p.setFillColor(colors.black)
        p.drawString(col1_val_x, r3_y, data['show_dt_str'])

        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawString(col2_label_x, r3_y, "Nett Total")
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.black)
        p.drawString(col2_val_x, r3_y, data['nett_amount'])

        # Row 4: Seat Information & Ticket Number
        r4_y = r3_y - line_height
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawString(col1_label_x, r4_y, "Seat Information")
        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(colors.HexColor('#1E3A8A')) # Deep indigo
        p.drawString(col1_val_x, r4_y, data['seats_str'][:28])

        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawString(col2_label_x, r4_y, "Ticket Number")
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.black)
        p.drawString(col2_val_x, r4_y, data['ticket_number_str'])

        # Row 5: Txn. Date & Time & Convenience / Tax
        r5_y = r4_y - line_height
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawString(col1_label_x, r5_y, "Txn. Date & Time")
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.black)
        p.drawString(col1_val_x, r5_y, data['txn_dt_str'])

        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawString(col2_label_x, r5_y, "Conv. Fee & Tax")
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.black)
        p.drawString(col2_val_x, r5_y, data['conv_fee'])

        # Row 6: Customer Name & Payment Mode
        r6_y = r5_y - line_height
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawString(col1_label_x, r6_y, "Customer Name")
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.black)
        p.drawString(col1_val_x, r6_y, data['customer_name'][:25])

        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawString(col2_label_x, r6_y, "Payment Mode")
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.black)
        p.drawString(col2_val_x, r6_y, data['payment_mode'][:18])

        # Row 7: Email & Screen No.
        r7_y = r6_y - line_height
        p.setFont("Helvetica", 9)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawString(col1_label_x, r7_y, "Email Address")
        p.setFont("Helvetica", 8.5)
        p.setFillColor(colors.black)
        p.drawString(col1_val_x, r7_y, data['customer_email'][:32])

        p.setFont("Helvetica-Bold", 9)
        p.setFillColor(colors.black)
        p.drawString(col2_label_x, r7_y, f"{data['screen_name']} ({data['screen_type']})")

        # 4. QR Code Column on the Far Right
        qr_buf = cls.generate_qr_code_image(data['verify_url'], box_size=8, border=1)
        from reportlab.lib.utils import ImageReader
        qr_image = ImageReader(qr_buf)

        qr_size = 85
        qr_x = box_x + slip_width - qr_size - 16
        qr_y = box_y + 75

        p.drawImage(qr_image, qr_x, qr_y, width=qr_size, height=qr_size)

        p.setFont("Helvetica-Bold", 7)
        p.setFillColor(colors.HexColor('#374151'))
        p.drawCentredString(qr_x + (qr_size / 2), qr_y - 10, "SCAN AT ADMISSION")

        # 5. Footer Instructions & Sourcing
        footer_line_y = box_y + 44
        p.setLineWidth(0.8)
        p.setStrokeColor(colors.HexColor('#374151'))
        p.line(box_x, footer_line_y, box_x + slip_width, footer_line_y)

        # Instructions Paragraph
        p.setFont("Helvetica-Bold", 7.5)
        p.setFillColor(colors.black)
        p.drawString(box_x + 12, footer_line_y - 12, "Instructions:")

        p.setFont("Helvetica", 6.5)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawString(box_x + 65, footer_line_y - 12, "Cancellations and 100% refunds are permitted up to 10 minutes prior to showtime from your profile. Carry valid photo ID")
        p.drawString(box_x + 65, footer_line_y - 21, "with this ticket. The QR code must be presented at the cinema entrance for contactless verification. All rights reserved.")

        # Sourced By Brand on right
        p.setFont("Helvetica", 7)
        p.setFillColor(colors.HexColor('#4B5563'))
        p.drawRightString(box_x + slip_width - 80, footer_line_y - 16, "Sourced By")
        p.setFont("Helvetica-Bold", 8)
        p.setFillColor(colors.HexColor('#BE123C'))
        p.drawRightString(box_x + slip_width - 14, footer_line_y - 16, "bookmyshow")

    @classmethod
    def generate_ticket_email_html(cls, booking=None, payment=None, bookings=None, request=None) -> str:
        """
        Generates the HTML email body with visual cinema ticket pass.
        """
        data = cls._extract_ticket_data(booking=booking, payment=payment, bookings=bookings, request=request)
        qr_base64 = cls.generate_qr_code_base64(data['verify_url'])
        data['qr_base64'] = qr_base64

        context = {'t': data}
        return render_to_string('emails/ticket_confirmation.html', context)
