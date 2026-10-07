import datetime
from decimal import Decimal
from django.db import migrations
from django.utils import timezone


def seed_cities_and_shows(apps, schema_editor):
    Theater = apps.get_model('movies', 'Theater')
    Screen = apps.get_model('movies', 'Screen')
    ShowSchedule = apps.get_model('movies', 'ShowSchedule')
    Movie = apps.get_model('movies', 'Movie')
    Genre = apps.get_model('movies', 'Genre')
    Language = apps.get_model('movies', 'Language')

    # 1. Update theater details with prominent cities and authentic names
    theaters_data = [
        {'id': 1, 'name': 'PVR ICON Palladium', 'city': 'Mumbai', 'address': 'High Street Phoenix, Lower Parel, Mumbai'},
        {'id': 2, 'name': 'INOX Laser Megaplex', 'city': 'Mumbai', 'address': 'R-City Mall, Ghatkopar, Mumbai'},
        {'id': 3, 'name': "PVR Director's Cut", 'city': 'Delhi NCR', 'address': 'Ambience Mall, Vasant Kunj, New Delhi'},
        {'id': 4, 'name': 'CineVault IMAX Flagship', 'city': 'Bengaluru', 'address': 'Forum South, Koramangala, Bengaluru'},
        {'id': 5, 'name': 'PVR Forum Koramangala', 'city': 'Bengaluru', 'address': 'Hosur Road, Bengaluru'},
        {'id': 6, 'name': 'Cinepolis Seasons Mall', 'city': 'Pune', 'address': 'Magarpatta City, Hadapsar, Pune'},
        {'id': 7, 'name': "Prasad's Large Screen IMAX", 'city': 'Hyderabad', 'address': 'NTR Gardens, Necklace Road, Hyderabad'},
        {'id': 8, 'name': 'INOX South Extension', 'city': 'Delhi NCR', 'address': 'South Extension II, New Delhi'},
    ]

    for item in theaters_data:
        th = Theater.objects.filter(id=item['id']).first()
        if th:
            th.name = item['name']
            th.city = item['city']
            th.address = item['address']
            th.is_active = True
            th.save()

    # 2. Ensure every theater has at least 2 screens
    for th in Theater.objects.all():
        if not Screen.objects.filter(theater=th).exists():
            Screen.objects.create(
                theater=th,
                name="Audi 1 (IMAX 4K)",
                screen_type="IMAX",
                seating_capacity=120,
                is_active=True
            )
            Screen.objects.create(
                theater=th,
                name="Audi 2 (Dolby Atmos)",
                screen_type="Dolby Atmos",
                seating_capacity=100,
                is_active=True
            )

    # 3. Ensure genre / language defaults on movies
    action_genre = Genre.objects.filter(slug='action').first()
    sci_fi_genre = Genre.objects.filter(slug='sci-fi').first()
    drama_genre = Genre.objects.filter(slug='drama').first()
    english_lang = Language.objects.filter(code='en').first()

    today = datetime.date.today()
    movies = list(Movie.objects.filter(is_active=True))
    for i, m in enumerate(movies):
        updated = False
        if not m.release_date:
            # Stagger release dates: recent past or upcoming
            offset_days = (i * 15) - 30
            m.release_date = today + datetime.timedelta(days=offset_days)
            updated = True
        if not m.rating or m.rating == Decimal('0.0'):
            ratings_pool = [Decimal('8.8'), Decimal('8.5'), Decimal('7.9'), Decimal('8.2'), Decimal('7.4'), Decimal('9.0')]
            m.rating = ratings_pool[i % len(ratings_pool)]
            updated = True
        if updated:
            m.save()

    # 4. Generate show schedules across morning, afternoon, evening, and night slots
    now = timezone.now()
    base_date = now.date()

    # Time slots:
    # Morning: 09:30 AM
    # Afternoon: 01:15 PM
    # Evening: 06:00 PM
    # Night: 09:45 PM
    slots = [
        (datetime.time(9, 30), datetime.time(12, 0), Decimal('180.00'), 'morning'),
        (datetime.time(13, 15), datetime.time(15, 45), Decimal('240.00'), 'afternoon'),
        (datetime.time(18, 0), datetime.time(20, 30), Decimal('350.00'), 'evening'),
        (datetime.time(21, 45), datetime.time(0, 15), Decimal('420.00'), 'night'),
    ]

    theaters = list(Theater.objects.all())
    for d_offset in range(3):  # Today, Tomorrow, Day after
        current_day = base_date + datetime.timedelta(days=d_offset)
        for t_idx, th in enumerate(theaters):
            screens = list(Screen.objects.filter(theater=th))
            if not screens or not movies:
                continue
            # Assign movies to screens
            assigned_movie = movies[t_idx % len(movies)]
            scr = screens[0]
            for start_t, end_t, price, timing_label in slots:
                start_dt = timezone.make_aware(datetime.datetime.combine(current_day, start_t))
                if end_t < start_t:
                    end_dt = timezone.make_aware(datetime.datetime.combine(current_day + datetime.timedelta(days=1), end_t))
                else:
                    end_dt = timezone.make_aware(datetime.datetime.combine(current_day, end_t))

                if not ShowSchedule.objects.filter(screen=scr, start_time=start_dt).exists():
                    ShowSchedule.objects.create(
                        movie=assigned_movie,
                        theater=th,
                        screen=scr,
                        start_time=start_dt,
                        end_time=end_dt,
                        price=price,
                        status='open'
                    )


def reverse_seed(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0006_auto_20260915_0739'),
    ]

    operations = [
        migrations.RunPython(seed_cities_and_shows, reverse_seed),
    ]
