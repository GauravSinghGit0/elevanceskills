# elevanceskills

Django movie seat-booking application with Razorpay test-mode checkout.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in your environment. `BOOKING_PRICE_INR` controls the price per seat and defaults to 100.

The test Checkout flow creates a Razorpay order, verifies the returned signature on the Django server, and creates bookings only after successful verification. Use Razorpay test cards from the Razorpay Dashboard documentation; no real money is charged in test mode.

Never commit `.env`, API secrets, database credentials, or a production secret key.
