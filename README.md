# elevanceskills

Django movie seat booking with Razorpay test-mode checkout.

## Vercel deployment

1. Push this repository to GitHub and import it into Vercel.
2. In Vercel, open **Project Settings → Environment Variables**.
3. Add the variables listed below for Preview and Production.
4. Redeploy after saving the variables.

```text
RAZORPAY_KEY_ID=rzp_test_Tdqz3jVAHGZmJF
RAZORPAY_KEY_SECRET=<new regenerated Razorpay test secret>
DEFAULT_SEAT_PRICE_INR=100
DJANGO_SECRET_KEY=<long random Django secret>
DEBUG=False
ALLOWED_HOSTS=.vercel.app,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://your-project.vercel.app
```

Add `DATABASE_URL` for a managed PostgreSQL database. Vercel's filesystem is not a durable database; SQLite is suitable only for temporary testing.

## Seat pricing

Each seat has its own `price` field. Existing seats receive ₹100 through the migration. Change individual prices in Django admin, for example ₹100 for standard and ₹200 for premium. The server calculates the Razorpay amount by summing the selected seats, so the browser cannot change the amount.

## First deployment

After deployment, open `/admin/`, create or use an admin account, and set seat prices. Then log in, select seats, and choose **Pay and Book Seats**. Use Razorpay test credentials/cards in Test Mode.

Never commit `.env`, a Razorpay secret, database credentials, or a production Django secret.
