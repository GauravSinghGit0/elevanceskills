# 🎬 Cineva — Enterprise Multiplex & Cinema Booking Platform

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg?logo=python)](https://python.org)
[![Django](https://img.shields.io/badge/Django-3.2-success.svg?logo=django)](https://djangoproject.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon_Cloud-336791.svg?logo=postgresql)](https://neon.tech)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-3.x-38B2AC.svg?logo=tailwind-css)](https://tailwindcss.com)
[![Vercel](https://img.shields.io/badge/Deploy-Vercel_Ready-black.svg?logo=vercel)](https://vercel.com)
[![Tests](https://img.shields.io/badge/Tests-141%20Passing-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-MIT-purple.svg)]()

> A full-stack, enterprise-grade cinema booking platform inspired by **BookMyShow** and **AMC Theatres**. Cineva delivers an immersive, dark-mode cinema experience with real-time seat locks, multi-tier auditorium layouts, gourmet food court ordering, authentic scannable UPI QR code simulation, automated PDF ticket passes, and asynchronous email confirmations.

---

## 📑 Table of Contents

- [Key Features](#-key-features)
- [Administrative Credentials](#-administrative-credentials)
- [System Architecture](#-system-architecture)
- [Interactive UI & Animations](#-interactive-ui--animations)
- [Payment Gateway & UPI Simulation](#-payment-gateway--upi-simulation)
- [Database Schema & Models](#-database-schema--models)
- [Local Installation Guide](#-local-installation-guide)
- [Vercel & Neon Deployment](#-vercel--neon-deployment)
- [Automated Testing](#-automated-testing)
- [Project Structure](#-project-structure)

---

## ✨ Key Features

- **🎬 Real Cinema Repertory**: 19 pre-populated box office movies with high-resolution posters, certifications (`UA`, `U`, `A`), ratings, runtimes, and embedded YouTube trailer modals.
- **🏛️ Multi-Theater Network**: 8 flagship theaters and 16 screens across major cities (Mumbai, Delhi, Bengaluru, Hyderabad) with 97 scheduled showtimes.
- **💺 Dynamic Multi-Tier Seating Map**: 1,315 auditorium seats spanning 5 distinct tiers:
  - 🛋️ **Recliner VIP Lounge** (₹350.00)
  - ⭐ **Premium Prime** (₹250.00)
  - 🎟️ **Executive Club** (₹200.00)
  - 💺 **Silver Plus** (₹160.00)
  - 🍿 **Classic D-Cinema** (₹120.00)
- **⏱️ High-Concurrency 2-Minute Lock**: When a patron selects a seat, an atomic database lock (`select_for_update`) holds the seat for 120 seconds. If payment is not finalized within 2 minutes, seats are automatically released for other users.
- **🍿 Gourmet Food Court Concessions**: Interactive menu with categories (Popcorn, Combos, Snacks, Beverages) and live cart calculation with a 10% multiplex convenience fee.
- **📱 100% Real Scannable UPI / QR Code**: Encodes standard UPI specification (`upi://pay?pa=cinevatickets@okaxis&pn=CinevaCinema&am=...`). Instantly recognized by Google Pay, PhonePe, Paytm, BHIM, and phone cameras.
- **⚡ 1-Click Instant Test Sandbox**: One-click simulation button to verify payment, confirm bookings, generate PDF tickets, and dispatch confirmation emails instantly.
- **🎟️ Automated PDF Admission Passes**: Authentic, printable PDF tickets generated with ReportLab, featuring barcode, booking ID, auditorium directions, and HMAC verification QR codes.
- **📧 Dual-Channel Email Delivery**: Instant HTML booking confirmation emails with attached PDF passes delivered via Gmail SMTP using Celery background workers (with daemon thread fallback).
- **🛠️ Dedicated Management Suite**: Full-featured cinema manager portal (`/movies/admin/`) and core Django admin (`/admin/`) to add/remove movies, assign screenings, and audit box office revenue.

---

## 🔐 Administrative Credentials

Cineva comes pre-configured with secure administrative access on both local SQLite and Neon PostgreSQL cloud databases:

| Portal | URL | Username | Password | Email |
| :--- | :--- | :--- | :--- | :--- |
| **Cineva Manager Suite** | `/movies/admin/` | `admin` | `Admin@Cineva#Secure2026!` | `ownai63@gmail.com` |
| **Django Admin** | `/admin/` | `cineva_admin` | `Admin@Cineva#Secure2026!` | `ownai63@gmail.com` |

> **To re-sync or change credentials via CLI**:
> ```bash
> python manage.py setup_admin
> ```

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    Client["User Browser / Mobile Device"] --> Vercel["Vercel Edge / Reverse Proxy"]
    Vercel --> WSGI["Django WSGI Application (Python 3.12)"]
    
    subgraph "Application Core"
        WSGI --> Services["Service Layers"]
        Services --> SeatLock["SeatLockService (2-Min Atomic Hold)"]
        Services --> Gateway["PaymentGatewayService (UPI / Razorpay)"]
        Services --> PDFGen["TicketGeneratorService (ReportLab)"]
    end
    
    subgraph "Data & Persistence"
        Services --> DB[("Neon PostgreSQL Cloud / SQLite")]
        Services --> Static["WhiteNoise (129 Static Assets)"]
    end
    
    subgraph "Asynchronous Delivery"
        Gateway --> CeleryWorker["Celery Worker / Daemon Thread"]
        CeleryWorker --> SMTP["Gmail SMTP (ownai63@gmail.com)"]
        SMTP --> UserInbox["Customer Email Inbox (with PDF Pass)"]
    end
```

---

## 🎨 Interactive UI & Animations

- **Hero Ken Burns Effect**: Slow cinematic motion on featured movie banners.
- **Card 3D Micro-Lift**: Movie cards elevate on hover with glowing ambient primary aura (`card-hover-fx`).
- **Tactile Seat Selection**: Dynamic bounce and pop micro-interaction (`seat-selected-pop`) upon seat clicks.
- **Pulsing Screen Beam**: Animated projector light arc (`screen-glow-animated`) directing all eyes toward the screen.
- **Interactive Button Shimmer**: Metallic sweep across primary checkout buttons.

---

## 💳 Payment Gateway & UPI Simulation

1. **Scan via Mobile**: Point Google Pay, PhonePe, or Paytm camera at the QR code modal. The device automatically reads `CinevaCinema` and the exact booking grand total.
2. **Instant Test Simulation**: Click the green **`✓ Simulate Successful Payment (1-Click Test)`** button in the modal.
3. **Razorpay Modal**: Full support for Razorpay popups with cryptographic HMAC-SHA256 signature verification.
4. **Idempotency Guarantee**: Server-side checks ensure zero duplicate charges or double bookings even under rapid network retries.

---

## ⏱️ 10-Minute Show Cut-off & Past Showtime Enforcement

- **Strict Online Cut-Off**: Ticket booking strictly closes **10 minutes prior to showtime**.
- **Past Shows Protected**: Slots for screenings that have already begun or concluded are rendered locked (`line-through` + lock badge).
- **Multi-Layer Validation**: Cut-off validation is enforced across the Theater List view, AJAX seat locks, Razorpay order generation, and transactional checkout finalization.

---

## 🔄 100% Instant Cancellation & Refund Flow

- **Self-Service Refunds**: Patrons can initiate cancellation and receive a full 100% refund directly from their **User Profile**.
- **Real-Time Seat Restoration**: Reserved seats are instantaneously returned to active inventory in a single atomic database transaction.
- **Auditing & Telemetry**: Updates transaction ledger status to `REFUNDED`, voids generated admission passes, and tracks refund telemetry across executive analytics dashboards.

---

## 🗄️ Database Schema & Models

The system architecture models 13 core entities:

- **`Movie`**: Titles, slugs, duration, rating, certification, posters, YouTube trailer IDs.
- **`Theater`**: Multiplex name, metropolitan city, venue location, audio specifications.
- **`Screen`**: Auditorium screen identifiers and total seating capacity.
- **`ShowSchedule`**: Showtime slots, pricing, and scheduling states.
- **`Seat`**: Row, column, seat codes, tier classifications, pricing, and temporary hold states.
- **`Payment`**: Order IDs, transaction hashes, payment methods, status audit logs.
- **`Booking`**: Unique link between user, seat, showtime, and payment transaction.
- **`Genre`**, **`Language`**, **`CastMember`**, **`MovieImage`**: Enriched movie metadata.
- **`Review`**, **`ReviewReport`**: Verified viewer review and moderation system.

---

## 🚀 Local Installation Guide

### 1. Clone & Setup Virtual Environment
```bash
git clone https://github.com/GauravSinghGit0/elevanceskills.git
cd elevanceskills

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy variables from `vercel_env.txt` into a `.env` file:
```bash
cp vercel_env.txt .env
```

### 3. Run Migrations & Initialize Admin
```bash
python manage.py migrate
python manage.py setup_admin
```

### 4. Start Development Server
```bash
python manage.py runserver 0.0.0.0:8000
```
- Open `http://127.0.0.1:8000/` in your browser.
- Access the Admin Suite at `http://127.0.0.1:8000/movies/admin/`.

---

## ☁️ Vercel & Neon Deployment

The project is pre-configured with `vercel.json`, `build_files.sh`, and pre-compiled static assets in `staticfiles/`.

### 1. Import Repository on Vercel
1. Go to [Vercel Dashboard](https://vercel.com/) $\rightarrow$ **Add New...** $\rightarrow$ **Project**.
2. Select repository **`elevanceskills`**.
3. Framework Preset: **Other** (Vercel will detect `vercel.json` automatically).

### 2. Add Environment Variables
In Vercel **Settings $\rightarrow$ Environment Variables**, click **"or paste the .env contents"** and paste the contents of [`vercel_env.txt`](./vercel_env.txt):

```env
SECRET_KEY=django-insecure-c8aetlj(=vp90n@#yoc^&d(_6ivp(d!bv-4-f!r$lawptjzrwu
DEBUG=False
DATABASE_URL=postgresql://username:password@ep-xyz.neon.tech/neondb?sslmode=require
RAZORPAY_KEY_ID=rzp_test_TkuUcn0OX3jYly
RAZORPAY_KEY_SECRET=your_razorpay_key_secret_here
RAZORPAY_WEBHOOK_SECRET=your_razorpay_webhook_secret_here
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_gmail_app_password_here
DEFAULT_FROM_EMAIL=Cineva Cinema <your_email@gmail.com>
```

### 3. Deploy
Click **Deploy**. Vercel will install dependencies, collect static assets, and deploy to a live `*.vercel.app` domain.

---

## 🧪 Automated Testing

Cineva includes 154 automated unit and integration tests covering the entire booking lifecycle:

```bash
python manage.py test
```

```text
Ran 154 tests in 57.250s

OK
```

All tests execute against an isolated in-memory database to ensure maximum test speed and integrity.

---

## 📁 Project Structure

```text
├── api/
│   └── index.py                 # Vercel serverless entrypoint
├── bookmyseat/
│   ├── settings.py              # Core settings (Neon DB, WhiteNoise, Email, Celery)
│   ├── urls.py                  # Master routing configuration
│   └── wsgi.py                  # WSGI callable for Vercel Python runtime
├── movies/
│   ├── models.py                # 13 relational database models
│   ├── views.py                 # Views for catalog, booking, payment, admin
│   ├── services.py              # Business logic: payments, seat locking, queries
│   ├── ticket_service.py        # ReportLab PDF ticket generator & QR builder
│   ├── tasks.py                 # Celery asynchronous email tasks
│   └── management/commands/     # setup_admin and data utilities
├── staticfiles/                 # 129 pre-collected static assets for Vercel
├── templates/
│   ├── components/              # Reusable movie cards, modals, pagination
│   ├── movies/                  # Seat selection, food court, theater lists
│   └── users/                   # Authentication, user profile, base templates
├── build_files.sh               # Vercel production build script
├── vercel.json                  # Vercel serverless build and routing manifest
├── vercel_env.txt               # Plaintext production environment variables
├── PROJECT_REPORT.txt           # Comprehensive humanized technical project report
└── requirements.txt             # Locked Python production dependencies
```

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.
