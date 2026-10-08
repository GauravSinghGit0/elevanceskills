import os
from datetime import datetime, time, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from movies.models import Movie, Theater, Screen, ShowSchedule


class Command(BaseCommand):
    help = 'Populates realistic show schedules for active movies and theaters for today and the next 7 days'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=8,
            help='Number of days from today to populate schedules for (default: 8)'
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear upcoming and current schedules before generating'
        )

    def handle(self, *args, **options):
        days_count = options['days']
        clear_existing = options['clear_existing']

        today = timezone.localdate()
        now = timezone.localtime()

        movies = list(Movie.objects.filter(is_active=True))
        theaters = list(Theater.objects.filter(is_active=True).prefetch_related('screens'))

        if not movies:
            self.stdout.write(self.style.ERROR("No active movies found in database."))
            return

        if not theaters:
            self.stdout.write(self.style.ERROR("No active theaters found in database."))
            return

        start_range = today
        end_range = today + timedelta(days=days_count)

        if clear_existing:
            deleted_count, _ = ShowSchedule.objects.filter(
                start_time__date__gte=start_range,
                start_time__date__lte=end_range
            ).delete()
            self.stdout.write(self.style.WARNING(f"Cleared {deleted_count} existing shows in target range."))

        created_count = 0
        existing_count = 0

        # Typical showtime slot templates per screen
        screen_1_slots = [
            (time(9, 30), time(12, 15), Decimal('250.00')),
            (time(13, 0), time(15, 45), Decimal('280.00')),
            (time(16, 30), time(19, 15), Decimal('320.00')),
            (time(20, 0), time(22, 45), Decimal('350.00')),
            (time(23, 15), time(2, 0), Decimal('220.00')),
        ]

        screen_2_slots = [
            (time(10, 45), time(13, 30), Decimal('180.00')),
            (time(14, 15), time(17, 0), Decimal('200.00')),
            (time(17, 45), time(20, 30), Decimal('240.00')),
            (time(21, 15), time(23, 55), Decimal('220.00')),
        ]

        existing_keys = set(
            ShowSchedule.objects.filter(
                start_time__date__gte=start_range,
                start_time__date__lte=end_range
            ).values_list('screen_id', 'start_time')
        )
        to_create = []

        for th_idx, theater in enumerate(theaters):
            screens = list(theater.screens.filter(is_active=True))
            if not screens:
                sc1 = Screen.objects.create(theater=theater, name='Audi 1 (IMAX 4K)', screen_type='IMAX', seating_capacity=100)
                sc2 = Screen.objects.create(theater=theater, name='Audi 2 (Dolby Atmos)', screen_type='Dolby Atmos', seating_capacity=80)
                screens = [sc1, sc2]

            movie_for_th = movies[th_idx % len(movies)]
            secondary_movie = movies[(th_idx + 1) % len(movies)]

            for day_offset in range(days_count):
                target_date = today + timedelta(days=day_offset)

                for sc_idx, screen in enumerate(screens):
                    assigned_movie = movie_for_th if (sc_idx % 2 == 0) else secondary_movie
                    slots = screen_1_slots if (sc_idx % 2 == 0) else screen_2_slots

                    for start_t, end_t, price in slots:
                        start_dt = timezone.make_aware(datetime.combine(target_date, start_t))
                        if end_t < start_t:
                            end_dt = timezone.make_aware(datetime.combine(target_date + timedelta(days=1), end_t))
                        else:
                            end_dt = timezone.make_aware(datetime.combine(target_date, end_t))

                        if (screen.id, start_dt) in existing_keys:
                            existing_count += 1
                            continue

                        to_create.append(ShowSchedule(
                            movie=assigned_movie,
                            theater=theater,
                            screen=screen,
                            start_time=start_dt,
                            end_time=end_dt,
                            price=price,
                            status='open'
                        ))
                        existing_keys.add((screen.id, start_dt))

        if to_create:
            ShowSchedule.objects.bulk_create(to_create)
            created_count = len(to_create)

        self.stdout.write(self.style.SUCCESS(
            f"Successfully generated {created_count} shows across {len(theaters)} theaters for {days_count} days "
            f"({today.strftime('%Y-%m-%d')} to {end_range.strftime('%Y-%m-%d')}). "
            f"Existing unchanged: {existing_count}."
        ))
