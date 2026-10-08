# 🎬 Cineva — Enterprise Multiplex & Cinema Booking Platform

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg?logo=python)](https://python.org)
[![Django](https://img.shields.io/badge/Django-3.2-success.svg?logo=django)](https://djangoproject.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon_Cloud-336791.svg?logo=postgresql)](https://neon.tech)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-3.x-38B2AC.svg?logo=tailwind-css)](https://tailwindcss.com)
[![Vercel](https://img.shields.io/badge/Deploy-Vercel_Ready-black.svg?logo=vercel)](https://vercel.com)
[![Tests](https://img.shields.io/badge/Tests-159%20Passing-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-MIT-purple.svg)]()

> A full-stack, enterprise-grade cinema booking platform inspired by **BookMyShow** and **AMC Theatres**. Cineva delivers an immersive, dark-mode cinema experience with real-time seat locks, multi-tier auditorium layouts, diverse theater types (Big Superplexes, Small Boutique Lounges, Drive-Ins, Rooftops), Hollywood, Anime, Bollywood, and Upcoming movie schedules, authentic UPI QR payments, and automated PDF tickets.

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

- **🎬 Expanded Cinema Repertory**: 36 curated movies spanning:
  - 🇺🇸 **Hollywood**: *Gladiator II*, *Deadpool & Wolverine*, *Dune: Part Two*, *Interstellar (10th Anniversary IMAX)*, *The Dark Knight*, *Oppenheimer*.
  - 🇯🇵 **Anime**: *Demon Slayer: Kimetsu no Yaiba - Infinity Castle*, *Suzume*, *Your Name (Kimi no Na wa)*, *Jujutsu Kaisen 0*, *Spirited Away (Ghibli 4K)*.
  - 🇮🇳 **Bollywood**: *Jawan*, *Stree 2: Sarkate Ka Aatank*, *Kalki 2898 AD*, *12th Fail*, *Fighter*.
  - 📅 **Upcoming in Theaters (With Release Dates & Advance Booking)**:
    - *Spider-Man: Beyond the Spider-Verse* (Releasing Oct 30, 2026)
    - *War 2* (Releasing Nov 14, 2026 — Diwali)
    - *Chainsaw Man – The Movie: Reze Arc* (Releasing Nov 20, 2026)
    - *Avatar: Fire and Ash* (Releasing Dec 18, 2026)
    - *Avengers: Secret Wars* (Releasing May 7, 2027)
- **🏛️ Diverse Theater Network (Big, Small & Unique Concepts)**: 19 active theaters and screens:
  - 🏢 **Big Theaters / Mega Multiplexes**: *PVR Superplex IMAX Laser & 4DX* (Mumbai, 4 screens), *INOX Megaplex & Luxe Club* (Delhi NCR, 4 screens), *Cinepolis Grand Megaplex* (Bengaluru).
  - 🛋️ **Small Theaters / Boutique & Indie**: *The Velvet Screen Boutique & Indie Lounge* (Bengaluru, 36 private recliners), *Regal Heritage Single-Screen Cinema* (Mumbai, 140 vintage seats), *Little Star Kids & Family Playhouse* (Delhi NCR, 48 beanbag loungers), *Criterion Arthouse & Vault Cinema* (Kolkata, 52 seats).
  - 🌴 **Every Type / Unique Concepts**: *Sunset Open-Air & Drive-In Cinema* (Goa Coast, Car FM 98.4 & deck loungers), *Gold Class VIP Luxury Cinema* (Mumbai Bandra, heated electric recliners), *CineMotion 4DX Dynamic Sensations* (Pune), *Skyline Rooftop Starlight Cinema* (Bengaluru 13th Floor, silent wireless Hi-Fi).
- **💺 Dynamic Multi-Tier Seating Map**: Over 3,100 auditorium seats spanning 5 distinct tiers (Recliner VIP, Balcony Gold, Gold Club, Silver Plus, Classic Silver) with multi-row selection.
- **⏱️ 10-Minute Booking Cut-Off & Instant 100% Refunds**: Past showtimes and shows starting within 10 minutes are locked automatically against late bookings. Confirmed tickets before cutoff are 100% refundable with 1-click instant cancellation and seat freeing.
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
