import os
import urllib.request
from datetime import datetime, time, timedelta
from decimal import Decimal
from PIL import Image, ImageDraw, ImageFont

from django.core.management.base import BaseCommand
from django.core.files import File
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify

from movies.models import Movie, Genre, Language, Theater, Screen, ShowSchedule, Seat
from movies.services import TheaterSeatingService


class Command(BaseCommand):
    help = 'Populates a rich cinema catalog: Hollywood, Anime, Bollywood, Upcoming movies, and Big, Small & Unique Theaters.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-shows',
            action='store_true',
            help='Clear existing show schedules before populating'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting expanded catalog population..."))
        today = timezone.localdate()

        # -------------------------------------------------------------
        # 1. Languages
        # -------------------------------------------------------------
        languages_data = [
            ('English', 'en'),
            ('Hindi', 'hi'),
            ('Japanese', 'ja'),
            ('Telugu', 'te'),
            ('Tamil', 'ta'),
            ('Korean', 'ko'),
        ]
        lang_map = {}
        for name, code in languages_data:
            lang, _ = Language.objects.get_or_create(code=code, defaults={'name': name, 'is_active': True})
            if lang.name != name:
                lang.name = name
                lang.save()
            lang_map[code] = lang
        self.stdout.write(self.style.SUCCESS(f"Languages verified: {len(lang_map)}"))

        # -------------------------------------------------------------
        # 2. Genres
        # -------------------------------------------------------------
        genres_data = [
            ('Action', 'High-adrenaline combat, chases, and heroic feats'),
            ('Adventure', 'Epic journeys into the uncharted and unknown'),
            ('Animation', 'Hand-drawn, CGI, and stop-motion visual artistry'),
            ('Anime', 'Iconic Japanese animated cinematic storytelling'),
            ('Sci-Fi', 'Futuristic science, space travel, and speculative technology'),
            ('Drama', 'Emotionally gripping stories of life and human relationships'),
            ('Comedy', 'Witty humor, satire, and laugh-out-loud amusement'),
            ('Horror', 'Spine-chilling terror, supernatural suspense, and thrills'),
            ('Fantasy', 'Magical realms, mythical legends, and enchanting lore'),
            ('Thriller', 'Tense mystery, suspense, and psychological twists'),
            ('Biography', 'True-life accounts of extraordinary individuals'),
            ('Romance', 'Heartfelt love stories, passion, and emotional bonds'),
        ]
        genre_map = {}
        for name, desc in genres_data:
            g_slug = slugify(name)
            genre, _ = Genre.objects.get_or_create(name=name, defaults={'slug': g_slug, 'description': desc, 'is_active': True})
            genre_map[name.lower()] = genre
        self.stdout.write(self.style.SUCCESS(f"Genres verified: {len(genre_map)}"))

        # -------------------------------------------------------------
        # 3. Poster Helper Function
        # -------------------------------------------------------------
        posters_dir = os.path.join(settings.MEDIA_ROOT, 'movies', 'posters')
        os.makedirs(posters_dir, exist_ok=True)

        def ensure_movie_poster(filename, title, category_color, remote_url=None):
            file_path = os.path.join(posters_dir, filename)
            rel_path = f"movies/posters/{filename}"

            if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:
                return rel_path

            # Attempt remote download first
            downloaded = False
            if remote_url:
                try:
                    req = urllib.request.Request(
                        remote_url,
                        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                    )
                    with urllib.request.urlopen(req, timeout=5) as response:
                        if response.status == 200:
                            data = response.read()
                            with open(file_path, 'wb') as f:
                                f.write(data)
                            downloaded = True
                except Exception:
                    downloaded = False

            if not downloaded:
                # Generate high quality styled poster with PIL
                img = Image.new('RGB', (600, 900), color=(15, 23, 42))
                draw = ImageDraw.Draw(img)

                # Gradient accent boxes
                draw.rectangle([(0, 0), (600, 24)], fill=category_color)
                draw.rectangle([(0, 876), (600, 900)], fill=category_color)
                draw.rectangle([(24, 40), (576, 860)], outline=category_color, width=3)

                # Watermark badge
                draw.rectangle([(50, 60), (550, 110)], fill=(30, 41, 59))
                draw.text((70, 75), "CINEVA PREMIERE SELECTION", fill=category_color)

                # Center text banner
                draw.rectangle([(50, 360), (550, 540)], fill=(30, 41, 59))
                draw.text((70, 390), title[:28].upper(), fill=(255, 255, 255))
                if len(title) > 28:
                    draw.text((70, 430), title[28:56].upper(), fill=(203, 213, 225))
                draw.text((70, 480), "PREMIUM THEATRICAL RELEASE", fill=category_color)

                # Bottom Specs
                draw.text((70, 800), "IMAX LASER • DOLBY ATMOS • 4DX", fill=(148, 163, 184))

                img.save(file_path, format='JPEG', quality=90)

            return rel_path

        # -------------------------------------------------------------
        # 4. Movies Definition (Anime, Bollywood, Hollywood, Upcoming)
        # -------------------------------------------------------------
        movies_definitions = [
            # === ANIME MOVIES ===
            {
                'title': "Demon Slayer: Kimetsu no Yaiba - Infinity Castle",
                'slug': 'demon-slayer-infinity-castle',
                'primary_lang': 'ja',
                'langs': ['ja', 'hi', 'en'],
                'genres': ['Anime', 'Animation', 'Action', 'Fantasy'],
                'release_date': today - timedelta(days=20),
                'duration': 118,
                'age_cert': 'UA',
                'rating': Decimal('4.9'),
                'total_reviews': 3820,
                'short_desc': "Tanjiro, the Hashira, and the Demon Slayer Corps plunge into the labyrinthine Infinity Castle for the climactic battle against Muzan Kibutsuji.",
                'trailer_url': "https://www.youtube.com/watch?v=VQGCKyvzIM4",
                'poster_file': "demon_slayer_infinity_castle.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/8b8R8l88Qje9dn9OE8PY05Nxl1X.jpg",
                'color': (225, 29, 72),
                'is_active': True,
            },
            {
                'title': "Suzume",
                'slug': 'suzume-no-tojimari',
                'primary_lang': 'ja',
                'langs': ['ja', 'hi', 'en'],
                'genres': ['Anime', 'Animation', 'Adventure', 'Fantasy'],
                'release_date': today - timedelta(days=60),
                'duration': 121,
                'age_cert': 'U',
                'rating': Decimal('4.8'),
                'total_reviews': 2450,
                'short_desc': "A high school girl and a mysterious young traveler embark on a spellbinding journey across Japan to close magical doors that are unleashing natural disasters.",
                'trailer_url': "https://www.youtube.com/watch?v=F7nQ0VUAOXg",
                'poster_file': "suzume.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/vIew5mEACjC79VwMsyUq5efjT2n.jpg",
                'color': (56, 189, 248),
                'is_active': True,
            },
            {
                'title': "Your Name (Kimi no Na wa)",
                'slug': 'your-name-kimi-no-na-wa',
                'primary_lang': 'ja',
                'langs': ['ja', 'en', 'hi'],
                'genres': ['Anime', 'Animation', 'Drama', 'Romance', 'Fantasy'],
                'release_date': today - timedelta(days=120),
                'duration': 107,
                'age_cert': 'U',
                'rating': Decimal('4.9'),
                'total_reviews': 5120,
                'short_desc': "Two strangers discover a magical cosmic connection as they wake up intermittently in each other's bodies. Makoto Shinkai's globally acclaimed masterpiece.",
                'trailer_url': "https://www.youtube.com/watch?v=xU47nhruN-Q",
                'poster_file': "your_name.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/q719jXXEzOoYaps6qFsRWa2f48k.jpg",
                'color': (168, 85, 247),
                'is_active': True,
            },
            {
                'title': "Jujutsu Kaisen 0",
                'slug': 'jujutsu-kaisen-0',
                'primary_lang': 'ja',
                'langs': ['ja', 'hi', 'en'],
                'genres': ['Anime', 'Animation', 'Action', 'Fantasy'],
                'release_date': today - timedelta(days=90),
                'duration': 105,
                'age_cert': 'UA',
                'rating': Decimal('4.7'),
                'total_reviews': 3110,
                'short_desc': "Yuta Okkotsu enrolls at the mysterious Tokyo Jujutsu High School to master cursed energy and free the monstrous spirit of his tragic childhood love.",
                'trailer_url': "https://www.youtube.com/watch?v=2docezZl574",
                'poster_file': "jujutsu_kaisen_0.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/3pTwXd0Ema429v6f9iG6CkNfIov.jpg",
                'color': (239, 68, 68),
                'is_active': True,
            },
            {
                'title': "Spirited Away",
                'slug': 'spirited-away-ghibli',
                'primary_lang': 'ja',
                'langs': ['ja', 'en'],
                'genres': ['Anime', 'Animation', 'Adventure', 'Fantasy'],
                'release_date': today - timedelta(days=180),
                'duration': 125,
                'age_cert': 'U',
                'rating': Decimal('4.9'),
                'total_reviews': 4890,
                'short_desc': "Hayao Miyazaki's Academy Award-winning classic: Young Chihiro wanders into a secret mystical bathhouse realm of ancient kami spirits and sorcery.",
                'trailer_url': "https://www.youtube.com/watch?v=ByXuk9QqQkk",
                'poster_file': "spirited_away.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/393mhKnlwoRydJ9Mmn2UrRkmZJ5.jpg",
                'color': (34, 197, 94),
                'is_active': True,
            },

            # === BOLLYWOOD MOVIES ===
            {
                'title': "Jawan",
                'slug': 'jawan-srk',
                'primary_lang': 'hi',
                'langs': ['hi', 'ta', 'te'],
                'genres': ['Action', 'Thriller', 'Drama'],
                'release_date': today - timedelta(days=40),
                'duration': 169,
                'age_cert': 'UA',
                'rating': Decimal('4.7'),
                'total_reviews': 6400,
                'short_desc': "A high-octane emotional action thriller driven by a wounded jailer and his vigilante team fighting systemic corruption. Starring Shah Rukh Khan.",
                'trailer_url': "https://www.youtube.com/watch?v=MWOlnZSnXJo",
                'poster_file': "jawan.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/jYW6iYFqgq1mZ7G8o5p8Vb4i9Xn.jpg",
                'color': (234, 88, 12),
                'is_active': True,
            },
            {
                'title': "Stree 2: Sarkate Ka Aatank",
                'slug': 'stree-2-sarkate-ka-aatank',
                'primary_lang': 'hi',
                'langs': ['hi'],
                'genres': ['Comedy', 'Horror'],
                'release_date': today - timedelta(days=14),
                'duration': 147,
                'age_cert': 'UA',
                'rating': Decimal('4.6'),
                'total_reviews': 5200,
                'short_desc': "The hilarious and terrified residents of Chanderi unite with the enigmatic Stree to confront the monstrous headless demon Sarkata in this record-breaking horror comedy.",
                'trailer_url': "https://www.youtube.com/watch?v=KVnheXwqFAw",
                'poster_file': "stree2.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/yL3pCqT8bA8lC4sNqG0n4fT9i2r.jpg",
                'color': (217, 119, 6),
                'is_active': True,
            },
            {
                'title': "Kalki 2898 AD",
                'slug': 'kalki-2898-ad',
                'primary_lang': 'hi',
                'langs': ['hi', 'te', 'ta'],
                'genres': ['Action', 'Sci-Fi', 'Fantasy'],
                'release_date': today - timedelta(days=30),
                'duration': 181,
                'age_cert': 'UA',
                'rating': Decimal('4.5'),
                'total_reviews': 4750,
                'short_desc': "In a post-apocalyptic dystopian Kasi, the immortal Ashwatthama awakens to protect the unborn savior of the cosmos from the tyrannical Supreme Yaskin.",
                'trailer_url': "https://www.youtube.com/watch?v=y1-w1TrF45A",
                'poster_file': "kalki2898.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/3b4lP5gY0yV9u5H9nI1Z8lG8rL.jpg",
                'color': (245, 158, 11),
                'is_active': True,
            },
            {
                'title': "12th Fail",
                'slug': '12th-fail-movie',
                'primary_lang': 'hi',
                'langs': ['hi'],
                'genres': ['Biography', 'Drama'],
                'release_date': today - timedelta(days=70),
                'duration': 147,
                'age_cert': 'U',
                'rating': Decimal('4.9'),
                'total_reviews': 5800,
                'short_desc': "The inspiring true story of Manoj Kumar Sharma, who rose from poverty in Chambal to restart his education and clear the civil services examination.",
                'trailer_url': "https://www.youtube.com/watch?v=weU61Zz72_I",
                'poster_file': "12th_fail.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/x56kS5Y2w9kM3M6YV1P9J9p5Q1.jpg",
                'color': (14, 165, 233),
                'is_active': True,
            },
            {
                'title': "Fighter",
                'slug': 'fighter-iaf',
                'primary_lang': 'hi',
                'langs': ['hi'],
                'genres': ['Action', 'Thriller'],
                'release_date': today - timedelta(days=50),
                'duration': 166,
                'age_cert': 'UA',
                'rating': Decimal('4.4'),
                'total_reviews': 3600,
                'short_desc': "Elite Indian Air Force aviators come together to form the Air Dragons quick-response team, taking to the skies to protect the homeland in intense aerial dogfights.",
                'trailer_url': "https://www.youtube.com/watch?v=6amIq_mP4xM",
                'poster_file': "fighter.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/zTo5b2wP5B1Y0T2s1Y3t1Y2b9a.jpg",
                'color': (14, 116, 144),
                'is_active': True,
            },

            # === HOLLYWOOD MOVIES ===
            {
                'title': "Gladiator II",
                'slug': 'gladiator-2-scott',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Action', 'Adventure', 'Drama'],
                'release_date': today - timedelta(days=10),
                'duration': 148,
                'age_cert': 'A',
                'rating': Decimal('4.6'),
                'total_reviews': 4100,
                'short_desc': "Decades after Maximus's heroic sacrifice, his son Lucius enters the Colosseum arena to challenge the tyrannical co-emperors and reclaim the lost glory of Rome.",
                'trailer_url': "https://www.youtube.com/watch?v=4rgYUipGJNo",
                'poster_file': "gladiator2.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/2cxhvwyEwRlysAmRH4iodkvo0z5.jpg",
                'color': (180, 83, 9),
                'is_active': True,
            },
            {
                'title': "Deadpool & Wolverine",
                'slug': 'deadpool-and-wolverine',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Action', 'Comedy', 'Sci-Fi'],
                'release_date': today - timedelta(days=25),
                'duration': 128,
                'age_cert': 'A',
                'rating': Decimal('4.8'),
                'total_reviews': 7200,
                'short_desc': "The Merc with a Mouth teams up with an elusive, world-weary Wolverine in an adrenaline-fueled multiverse adventure packed with irreverent chaos and brutal action.",
                'trailer_url': "https://www.youtube.com/watch?v=73_1biulkYk",
                'poster_file': "deadpool_wolverine.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/8cdWjvZQUExUUTzyp4t6EDMubfO.jpg",
                'color': (220, 38, 38),
                'is_active': True,
            },
            {
                'title': "Dune: Part Two",
                'slug': 'dune-part-two',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Action', 'Adventure', 'Sci-Fi'],
                'release_date': today - timedelta(days=45),
                'duration': 166,
                'age_cert': 'UA',
                'rating': Decimal('4.9'),
                'total_reviews': 8300,
                'short_desc': "Paul Atreides unites with Chani and the Fremen while seeking vengeance against the conspirators who destroyed his family, facing a fateful choice between love and the universe.",
                'trailer_url': "https://www.youtube.com/watch?v=Way9Dexny3w",
                'poster_file': "dune2.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/czembW0Rk1Ke7lCJGhkAi0ymUTW.jpg",
                'color': (202, 138, 4),
                'is_active': True,
            },

            # === UPCOMING MOVIES (WITH PRECISE RELEASE DATES & PREVIEW ADVANCE BOOKING) ===
            {
                'title': "Avatar: Fire and Ash",
                'slug': 'avatar-fire-and-ash',
                'primary_lang': 'en',
                'langs': ['en', 'hi', 'te', 'ta'],
                'genres': ['Sci-Fi', 'Action', 'Adventure', 'Fantasy'],
                'release_date': today + timedelta(days=71),  # Dec 18, 2026
                'duration': 192,
                'age_cert': 'UA',
                'rating': Decimal('4.9'),
                'total_reviews': 890,
                'short_desc': "James Cameron returns to Pandora to unveil the fierce volcanic Ash People tribe, pushing the Sully family into moral ambiguity and stunning uncharted territories.",
                'trailer_url': "https://www.youtube.com/watch?v=d9MyW72ELq0",
                'poster_file': "avatar_fire_and_ash.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/t6HIqrRAclMCA60NsSmeqe9RmNV.jpg",
                'color': (239, 68, 68),
                'is_active': True,
            },
            {
                'title': "War 2",
                'slug': 'war-2-yrf',
                'primary_lang': 'hi',
                'langs': ['hi', 'te', 'ta'],
                'genres': ['Action', 'Thriller'],
                'release_date': today + timedelta(days=37),  # Nov 14, 2026 (Diwali)
                'duration': 165,
                'age_cert': 'UA',
                'rating': Decimal('4.8'),
                'total_reviews': 620,
                'short_desc': "Major Kabir Dhaliwal returns for an explosive clash of titans across Tokyo, Madrid, and the Himalayas. Starring Hrithik Roshan, Jr. NTR, and Kiara Advani.",
                'trailer_url': "https://www.youtube.com/watch?v=tQ0mz_U3V4c",
                'poster_file': "war2.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/7I9n1B1r2C4Y5s8M1N4L8V9bT1K.jpg",
                'color': (249, 115, 22),
                'is_active': True,
            },
            {
                'title': "Chainsaw Man – The Movie: Reze Arc",
                'slug': 'chainsaw-man-reze-arc-movie',
                'primary_lang': 'ja',
                'langs': ['ja', 'hi', 'en'],
                'genres': ['Anime', 'Animation', 'Action', 'Fantasy', 'Horror'],
                'release_date': today + timedelta(days=43),  # Nov 20, 2026
                'duration': 102,
                'age_cert': 'A',
                'rating': Decimal('4.9'),
                'total_reviews': 740,
                'short_desc': "Denji meets the captivating cafe barista Reze, completely unaware of her deadly alter ego as the Soviet Bomb Devil in this explosive cinematic adaptation.",
                'trailer_url': "https://www.youtube.com/watch?v=0kFh_0k-q8A",
                'poster_file': "chainsaw_man_reze.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/npdB6eFz4qt952z9UmMcIMAZ0PP.jpg",
                'color': (244, 63, 94),
                'is_active': True,
            },
            {
                'title': "Spider-Man: Beyond the Spider-Verse",
                'slug': 'spider-man-beyond-the-spider-verse',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Animation', 'Action', 'Sci-Fi', 'Adventure'],
                'release_date': today + timedelta(days=22),  # Oct 30, 2026
                'duration': 140,
                'age_cert': 'U',
                'rating': Decimal('4.9'),
                'total_reviews': 1200,
                'short_desc': "Miles Morales faces an alternate reality version of himself as the Prowler on Earth-42 while Gwen Stacy gathers a rebel spider-force to save all dimensions.",
                'trailer_url': "https://www.youtube.com/watch?v=cqGjhVJWtEg",
                'poster_file': "beyond_spider_verse.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/8Vt6mWEReuy4Of61Lnj5Xj704m8.jpg",
                'color': (99, 102, 241),
                'is_active': True,
            },
            {
                'title': "Avengers: Secret Wars",
                'slug': 'avengers-secret-wars',
                'primary_lang': 'en',
                'langs': ['en', 'hi', 'te'],
                'genres': ['Action', 'Sci-Fi', 'Adventure', 'Fantasy'],
                'release_date': today + timedelta(days=211),  # May 7, 2027
                'duration': 185,
                'age_cert': 'UA',
                'rating': Decimal('5.0'),
                'total_reviews': 450,
                'short_desc': "The Marvel Multiverse fractures into Battleworld. Earth's mightiest heroes from all eras and alternate dimensions unite for the greatest battle in history.",
                'trailer_url': "https://www.youtube.com/watch?v=hA6hldpSTF8",
                'poster_file': "secret_wars.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/mBaXZ95R2v6L3v9rY6aV3pZ2r9M.jpg",
                'color': (147, 51, 234),
                'is_active': True,
            },
        ]

        movies_obj_map = {}
        for m_data in movies_definitions:
            poster_rel = ensure_movie_poster(
                filename=m_data['poster_file'],
                title=m_data['title'],
                category_color=m_data['color'],
                remote_url=m_data.get('remote_url')
            )

            movie, created = Movie.objects.get_or_create(
                slug=m_data['slug'],
                defaults={
                    'title': m_data['title'],
                    'name': m_data['title'],
                    'short_description': m_data['short_desc'],
                    'description': m_data['short_desc'],
                    'release_date': m_data['release_date'],
                    'duration': m_data['duration'],
                    'age_certification': m_data['age_cert'],
                    'rating': m_data['rating'],
                    'total_reviews': m_data['total_reviews'],
                    'trailer_url': m_data['trailer_url'],
                    'is_active': m_data['is_active'],
                    'poster': poster_rel,
                    'image': poster_rel,
                    'language': lang_map.get(m_data['primary_lang']),
                }
            )

            # Update existing if needed
            movie.title = m_data['title']
            movie.name = m_data['title']
            movie.short_description = m_data['short_desc']
            movie.description = m_data['short_desc']
            movie.release_date = m_data['release_date']
            movie.duration = m_data['duration']
            movie.age_certification = m_data['age_cert']
            movie.rating = m_data['rating']
            movie.total_reviews = m_data['total_reviews']
            movie.trailer_url = m_data['trailer_url']
            movie.is_active = m_data['is_active']
            movie.poster = poster_rel
            movie.image = poster_rel
            movie.language = lang_map.get(m_data['primary_lang'])
            movie.save()

            # Set languages
            movie.languages.set([lang_map[c] for c in m_data['langs'] if c in lang_map])

            # Set genres
            genre_objs = [genre_map[g.lower()] for g in m_data['genres'] if g.lower() in genre_map]
            movie.genres.set(genre_objs)

            movies_obj_map[m_data['slug']] = movie

        self.stdout.write(self.style.SUCCESS(f"Saved {len(movies_obj_map)} curated movies in database."))

        # -------------------------------------------------------------
        # 5. Diverse Theaters (Big, Small, Boutique, Drive-In, Rooftop)
        # -------------------------------------------------------------
        theaters_data = [
            # --- BIG THEATERS: Mega Multiplexes / Superplexes ---
            {
                'name': "PVR Superplex IMAX Laser & 4DX",
                'city': "Mumbai",
                'address': "High Street Phoenix Mall, Senapati Bapat Marg, Lower Parel, Mumbai",
                'screens': [
                    {'name': "Audi 1 (IMAX 4K Laser Giant)", 'screen_type': "IMAX", 'capacity': 280},
                    {'name': "Audi 2 (4DX Motion Theater)", 'screen_type': "4DX", 'capacity': 140},
                    {'name': "Audi 3 (Dolby Atmos Grand Audi)", 'screen_type': "Dolby Atmos", 'capacity': 220},
                    {'name': "Audi 4 (Laser RealD 3D)", 'screen_type': "3D", 'capacity': 180},
                ]
            },
            {
                'name': "INOX Megaplex & Luxe Club",
                'city': "Delhi NCR",
                'address': "DLF Mall of India, Sector 18, Noida, Delhi NCR",
                'screens': [
                    {'name': "Audi 1 (Dolby Cinema Laser)", 'screen_type': "Dolby Atmos", 'capacity': 260},
                    {'name': "Audi 2 (Insignia VIP Lounge)", 'screen_type': "2D", 'capacity': 64},
                    {'name': "Audi 3 (IMAX Experience Hall)", 'screen_type': "IMAX", 'capacity': 240},
                    {'name': "Audi 4 (BigPix Digital 2D)", 'screen_type': "2D", 'capacity': 190},
                ]
            },
            {
                'name': "Cinepolis Grand Megaplex",
                'city': "Bengaluru",
                'address': "Forum Shantiniketan, ITPL Main Road, Whitefield, Bengaluru",
                'screens': [
                    {'name': "Audi 1 (Macro XE Giant Screen Atmos)", 'screen_type': "Dolby Atmos", 'capacity': 250},
                    {'name': "Audi 2 (4DX Motion Hall)", 'screen_type': "4DX", 'capacity': 120},
                    {'name': "Audi 3 (VIP Royal Class Lounge)", 'screen_type': "2D", 'capacity': 70},
                ]
            },

            # --- SMALL THEATERS: Boutique, Indie, Single-Screen & Cozy ---
            {
                'name': "The Velvet Screen Boutique & Indie Lounge",
                'city': "Bengaluru",
                'address': "100 Feet Road, HAL 2nd Stage, Indiranagar, Bengaluru",
                'screens': [
                    {'name': "The Velvet Salon (Intimate 36-Seat Lounge)", 'screen_type': "Dolby Atmos", 'capacity': 36},
                ]
            },
            {
                'name': "Regal Heritage Single-Screen Cinema",
                'city': "Mumbai",
                'address': "Colaba Causeway, Opposite Prince of Wales Museum, Colaba, Mumbai",
                'screens': [
                    {'name': "Grand Balcony & Stalls (Historic Hall)", 'screen_type': "2D", 'capacity': 140},
                ]
            },
            {
                'name': "Little Star Kids & Family Playhouse",
                'city': "Delhi NCR",
                'address': "Select Citywalk Mall, District Centre, Saket, New Delhi",
                'screens': [
                    {'name': "Playhouse Audi (Beanbags & Family Soft Loungers)", 'screen_type': "2D", 'capacity': 48},
                ]
            },
            {
                'name': "Criterion Arthouse & Vault Cinema",
                'city': "Kolkata",
                'address': "17 Park Street, Heritage Cultural Corridor, Kolkata",
                'screens': [
                    {'name': "Vault Audi (Curated 4K Indie Cinema)", 'screen_type': "Dolby Atmos", 'capacity': 52},
                ]
            },

            # --- EVERY TYPE: Drive-In, VIP Luxury, 4DX, Rooftop ---
            {
                'name': "Sunset Open-Air & Drive-In Cinema",
                'city': "Goa",
                'address': "Vagator Cliffside, Near Ozran Beach, North Goa",
                'screens': [
                    {'name': "Giant Cliffside Drive-In Screen (Car FM 98.4 & Loungers)", 'screen_type': "2D", 'capacity': 60},
                ]
            },
            {
                'name': "Gold Class VIP Luxury Cinema",
                'city': "Mumbai",
                'address': "Linking Road, Bandra West, Mumbai",
                'screens': [
                    {'name': "The Royal Screen (Electric Heated Recliners)", 'screen_type': "Dolby Atmos", 'capacity': 32},
                ]
            },
            {
                'name': "CineMotion 4DX & Dynamic Sensations",
                'city': "Pune",
                'address': "Phoenix Marketcity, Nagar Road, Viman Nagar, Pune",
                'screens': [
                    {'name': "4DX Sensation Audi (Synchronized Motion)", 'screen_type': "4DX", 'capacity': 96},
                ]
            },
            {
                'name': "Skyline Rooftop Starlight Cinema",
                'city': "Bengaluru",
                'address': "Barton Centre Rooftop (13th Floor), MG Road, Bengaluru",
                'screens': [
                    {'name': "Skyline Starlight Deck (Silent Wireless Hi-Fi)", 'screen_type': "2D", 'capacity': 56},
                ]
            },
        ]

        theater_objs = []
        for t_info in theaters_data:
            th, _ = Theater.objects.get_or_create(
                name=t_info['name'],
                defaults={
                    'city': t_info['city'],
                    'address': t_info['address'],
                    'is_active': True,
                }
            )
            th.city = t_info['city']
            th.address = t_info['address']
            th.is_active = True
            th.save()

            # Ensure screens
            for sc_info in t_info['screens']:
                sc, sc_created = Screen.objects.get_or_create(
                    theater=th,
                    name=sc_info['name'],
                    defaults={
                        'screen_type': sc_info['screen_type'],
                        'seating_capacity': sc_info['capacity'],
                        'is_active': True,
                    }
                )
                if not sc_created:
                    sc.screen_type = sc_info['screen_type']
                    sc.seating_capacity = sc_info['capacity']
                    sc.is_active = True
                    sc.save()

            # Generate seat layout
            TheaterSeatingService.ensure_full_theater_layout(th, min_seats=30)
            theater_objs.append(th)

        self.stdout.write(self.style.SUCCESS(f"Saved {len(theater_objs)} diverse theaters (Big, Small, Boutique, Drive-In, Rooftop)."))

        # -------------------------------------------------------------
        # 6. Generate Realistic Show Schedules
        # -------------------------------------------------------------
        if options['clear_shows']:
            ShowSchedule.objects.all().delete()
            self.stdout.write(self.style.WARNING("Cleared existing show schedules."))

        now = timezone.localtime()
        all_active_movies = list(Movie.objects.filter(is_active=True))
        now_showing_movies = [m for m in all_active_movies if m.release_date and m.release_date <= today]
        upcoming_movies = [m for m in all_active_movies if m.release_date and m.release_date > today]

        slot_templates = [
            (time(10, 0), time(12, 45), Decimal('220.00')),
            (time(13, 30), time(16, 15), Decimal('260.00')),
            (time(17, 0), time(19, 45), Decimal('320.00')),
            (time(20, 30), time(23, 15), Decimal('350.00')),
        ]

        existing_keys = set(ShowSchedule.objects.values_list('screen_id', 'start_time'))
        new_shows = []

        screens_by_theater = {
            th.id: list(th.screens.filter(is_active=True))
            for th in theater_objs
        }

        # A) Now Showing Movies: Today + next 7 days
        for day_offset in range(8):
            target_date = today + timedelta(days=day_offset)

            for th_idx, theater in enumerate(theater_objs):
                screens = screens_by_theater.get(theater.id, [])
                if not screens:
                    continue

                for sc_idx, screen in enumerate(screens):
                    assigned_movie = now_showing_movies[(th_idx + sc_idx + day_offset) % len(now_showing_movies)]

                    for slot_idx, (st_t, end_t, base_pr) in enumerate(slot_templates):
                        # Adjust price based on screen type and time
                        price = base_pr
                        if screen.screen_type == 'IMAX':
                            price += Decimal('120.00')
                        elif screen.screen_type == '4DX':
                            price += Decimal('100.00')
                        elif screen.screen_type == 'Dolby Atmos':
                            price += Decimal('60.00')

                        start_dt = timezone.make_aware(datetime.combine(target_date, st_t))
                        end_dt = timezone.make_aware(datetime.combine(target_date, end_t))

                        if (screen.id, start_dt) in existing_keys:
                            continue

                        new_shows.append(ShowSchedule(
                            movie=assigned_movie,
                            theater=theater,
                            screen=screen,
                            start_time=start_dt,
                            end_time=end_dt,
                            price=price,
                            status='open',
                        ))
                        existing_keys.add((screen.id, start_dt))

        # B) Upcoming Movies: Show in theaters with dates (on release date and opening week!)
        for up_movie in upcoming_movies:
            # Stagger premiere week shows across top theaters (IMAX Superplex, Luxe, Velvet Screen, Drive-In)
            rel_date = up_movie.release_date
            for day_offset in range(7):
                target_date = rel_date + timedelta(days=day_offset)

                for th_idx, theater in enumerate(theater_objs[:6]):  # Premiere auditoriums
                    screens = screens_by_theater.get(theater.id, [])
                    if not screens:
                        continue
                    screen = screens[th_idx % len(screens)]

                    # Pick 2-3 premiere slots
                    for st_t, end_t, base_pr in slot_templates[1:]:
                        price = base_pr + Decimal('80.00')  # Advance booking premiere price
                        start_dt = timezone.make_aware(datetime.combine(target_date, st_t))
                        end_dt = timezone.make_aware(datetime.combine(target_date, end_t))

                        if (screen.id, start_dt) in existing_keys:
                            continue

                        new_shows.append(ShowSchedule(
                            movie=up_movie,
                            theater=theater,
                            screen=screen,
                            start_time=start_dt,
                            end_time=end_dt,
                            price=price,
                            status='open',
                        ))
                        existing_keys.add((screen.id, start_dt))

        if new_shows:
            ShowSchedule.objects.bulk_create(new_shows)
            self.stdout.write(self.style.SUCCESS(f"Created {len(new_shows)} scheduled shows across theaters!"))

        self.stdout.write(self.style.SUCCESS("All tasks finished successfully! Cinema repertoire is live and ready."))
