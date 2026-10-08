import os
import urllib.request
from datetime import datetime, time, timedelta
from decimal import Decimal
from PIL import Image, ImageDraw

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify

from movies.models import Movie, Genre, Language, Theater, Screen, ShowSchedule
from movies.services import TheaterSeatingService


class Command(BaseCommand):
    help = 'Populates authentic real-world movies (Now Showing & Upcoming across Hollywood, Bollywood, and Anime) and diverse theaters.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-shows',
            action='store_true',
            help='Clear existing show schedules before populating'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Populating authentic cinema catalog based on real theatrical releases..."))
        today = timezone.localdate()

        # -------------------------------------------------------------
        # 0. Deactivate legacy dummy movies
        # -------------------------------------------------------------
        dummy_movies = Movie.objects.filter(title__iregex=r'^(movie|test|ergeg|thread)')
        deactivated = dummy_movies.update(is_active=False)
        if deactivated:
            self.stdout.write(self.style.WARNING(f"Deactivated {deactivated} legacy dummy movies."))

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
                img = Image.new('RGB', (600, 900), color=(15, 23, 42))
                draw = ImageDraw.Draw(img)

                draw.rectangle([(0, 0), (600, 24)], fill=category_color)
                draw.rectangle([(0, 876), (600, 900)], fill=category_color)
                draw.rectangle([(24, 40), (576, 860)], outline=category_color, width=3)

                draw.rectangle([(50, 60), (550, 110)], fill=(30, 41, 59))
                draw.text((70, 75), "CINEVA PREMIERE SELECTION", fill=category_color)

                draw.rectangle([(50, 360), (550, 540)], fill=(30, 41, 59))
                draw.text((70, 390), title[:28].upper(), fill=(255, 255, 255))
                if len(title) > 28:
                    draw.text((70, 430), title[28:56].upper(), fill=(203, 213, 225))
                draw.text((70, 480), "PREMIUM THEATRICAL RELEASE", fill=category_color)

                draw.text((70, 800), "IMAX LASER • DOLBY ATMOS • 4DX", fill=(148, 163, 184))
                img.save(file_path, format='JPEG', quality=90)

            return rel_path

        # -------------------------------------------------------------
        # 4. Authentic Movies Definition: Now Showing & Upcoming
        # -------------------------------------------------------------
        movies_definitions = [
            # =========================================================
            # SECTION A: NOW SHOWING IN THEATERS (RELEASE DATE <= TODAY)
            # =========================================================

            # --- Hollywood Now Showing ---
            {
                'title': "Joker: Folie à Deux",
                'slug': 'joker-folie-a-deux',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Drama', 'Thriller', 'Crime'],
                'release_date': today - timedelta(days=4),  # Oct 4, 2026
                'duration': 138,
                'age_cert': 'A',
                'rating': Decimal('4.1'),
                'total_reviews': 3200,
                'short_desc': "Arthur Fleck meets the love of his life, Harleen Quinzel, while incarcerated at Arkham State Hospital, embarking on a musical madness through Gotham City.",
                'trailer_url': "https://www.youtube.com/watch?v=_OKAwz2NiOI",
                'poster_file': "joker_folie_a_deux.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/aciP8Km0waTLACC1KhAg37q59Sr.jpg",
                'color': (220, 38, 38),
                'is_active': True,
            },
            {
                'title': "The Wild Robot",
                'slug': 'the-wild-robot',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Animation', 'Adventure', 'Sci-Fi', 'Family'],
                'release_date': today - timedelta(days=11),  # Sep 27, 2026
                'duration': 102,
                'age_cert': 'U',
                'rating': Decimal('4.9'),
                'total_reviews': 4500,
                'short_desc': "After a shipwreck, an intelligent robot named Roz is stranded on an uninhabited island, bonding with the native animals and adopting an orphaned gosling.",
                'trailer_url': "https://www.youtube.com/watch?v=67vbA5ZJdKQ",
                'poster_file': "the_wild_robot.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/wTnV3PCVW5O92JMrFvvrRil3Gl8.jpg",
                'color': (34, 197, 94),
                'is_active': True,
            },
            {
                'title': "Deadpool & Wolverine",
                'slug': 'deadpool-and-wolverine',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Action', 'Comedy', 'Sci-Fi'],
                'release_date': today - timedelta(days=74),  # July 26, 2026
                'duration': 128,
                'age_cert': 'A',
                'rating': Decimal('4.8'),
                'total_reviews': 7800,
                'short_desc': "The Merc with a Mouth teams up with an elusive, world-weary Wolverine in an adrenaline-fueled multiverse adventure packed with irreverent chaos and brutal action.",
                'trailer_url': "https://www.youtube.com/watch?v=73_1biulkYk",
                'poster_file': "deadpool_wolverine.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/8cdWjvZQUExUUTzyp4t6EDMubfO.jpg",
                'color': (239, 68, 68),
                'is_active': True,
            },
            {
                'title': "Beetlejuice Beetlejuice",
                'slug': 'beetlejuice-beetlejuice',
                'primary_lang': 'en',
                'langs': ['en'],
                'genres': ['Comedy', 'Fantasy', 'Horror'],
                'release_date': today - timedelta(days=32),  # Sep 6, 2026
                'duration': 105,
                'age_cert': 'UA',
                'rating': Decimal('4.4'),
                'total_reviews': 2900,
                'short_desc': "Three generations of the Deetz family return home to Winter River following an unexpected family tragedy. Lydia's rebellious teenage daughter accidentally opens the portal to the Afterlife.",
                'trailer_url': "https://www.youtube.com/watch?v=As-vKW4ZboU",
                'poster_file': "beetlejuice2.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/kKgQzkUCUmgnqzAzqqwMukAKu0U.jpg",
                'color': (168, 85, 247),
                'is_active': True,
            },
            {
                'title': "Alien: Romulus",
                'slug': 'alien-romulus',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Horror', 'Sci-Fi', 'Thriller'],
                'release_date': today - timedelta(days=53),  # Aug 16, 2026
                'duration': 119,
                'age_cert': 'A',
                'rating': Decimal('4.6'),
                'total_reviews': 3400,
                'short_desc': "While scavenging the deep ends of a derelict space station, a group of young space colonizers come face-to-face with the most terrifying life form in the universe.",
                'trailer_url': "https://www.youtube.com/watch?v=x0XDEhP4MQs",
                'poster_file': "alien_romulus.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/b33nnKl1vvg6k7MLUmWFiDYtYIF.jpg",
                'color': (14, 165, 233),
                'is_active': True,
            },
            {
                'title': "Transformers One",
                'slug': 'transformers-one',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Animation', 'Action', 'Sci-Fi', 'Adventure'],
                'release_date': today - timedelta(days=18),  # Sep 20, 2026
                'duration': 104,
                'age_cert': 'U',
                'rating': Decimal('4.7'),
                'total_reviews': 2700,
                'short_desc': "The untold origin story of Optimus Prime and Megatron, exploring their bond as brothers-in-arms on Cybertron before they became sworn enemies.",
                'trailer_url': "https://www.youtube.com/watch?v=u2NuUWuwPCM",
                'poster_file': "transformers_one.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/qbkAqmmEIZfrG8vjpHpqaCkhp5M.jpg",
                'color': (234, 88, 12),
                'is_active': True,
            },
            {
                'title': "Dune: Part Two",
                'slug': 'dune-part-two',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Action', 'Adventure', 'Sci-Fi'],
                'release_date': today - timedelta(days=150),
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
            {
                'title': "Interstellar (10th Anniversary IMAX Re-Release)",
                'slug': 'interstellar-imax-10th',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Sci-Fi', 'Adventure', 'Drama'],
                'release_date': today - timedelta(days=23),
                'duration': 169,
                'age_cert': 'UA',
                'rating': Decimal('5.0'),
                'total_reviews': 9400,
                'short_desc': "Christopher Nolan's interstellar masterpiece returns to 70mm IMAX Laser screens to celebrate 10 years of cosmic awe and emotion.",
                'trailer_url': "https://www.youtube.com/watch?v=zSWdZVtXT7E",
                'poster_file': "interstellar.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg",
                'color': (30, 41, 59),
                'is_active': True,
            },

            # --- Bollywood Now Showing ---
            {
                'title': "Jigra",
                'slug': 'jigra-movie',
                'primary_lang': 'hi',
                'langs': ['hi', 'te'],
                'genres': ['Action', 'Thriller', 'Drama'],
                'release_date': today - timedelta(days=6),  # Oct 2, 2026
                'duration': 155,
                'age_cert': 'UA',
                'rating': Decimal('4.6'),
                'total_reviews': 3800,
                'short_desc': "An exceptionally courageous sister undergoes extreme trials to break her unjustly incarcerated younger brother out of a high-security foreign prison. Starring Alia Bhatt and Vedang Raina.",
                'trailer_url': "https://www.youtube.com/watch?v=2tX2bA_uR_A",
                'poster_file': "jigra.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/d7FpW8XWjFfB5V5Xk5k4Z4zY3g1.jpg",
                'color': (225, 29, 72),
                'is_active': True,
            },
            {
                'title': "Devara: Part 1",
                'slug': 'devara-part-1',
                'primary_lang': 'hi',
                'langs': ['hi', 'te', 'ta'],
                'genres': ['Action', 'Thriller', 'Drama'],
                'release_date': today - timedelta(days=11),  # Sep 27, 2026
                'duration': 178,
                'age_cert': 'UA',
                'rating': Decimal('4.5'),
                'total_reviews': 4900,
                'short_desc': "A fearless coastal chieftain fights ruthlessly against smuggling cartels to defend his homeland. Starring Jr. NTR, Saif Ali Khan, and Janhvi Kapoor in an epic coastal saga.",
                'trailer_url': "https://www.youtube.com/watch?v=Fj2FkG1yU54",
                'poster_file': "devara_part_1.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/AIPVs9A7t77hW2v44Z127zG8gP0.jpg",
                'color': (180, 83, 9),
                'is_active': True,
            },
            {
                'title': "Stree 2: Sarkate Ka Aatank",
                'slug': 'stree-2-sarkate-ka-aatank',
                'primary_lang': 'hi',
                'langs': ['hi'],
                'genres': ['Comedy', 'Horror'],
                'release_date': today - timedelta(days=54),  # Aug 15, 2026
                'duration': 147,
                'age_cert': 'UA',
                'rating': Decimal('4.7'),
                'total_reviews': 8200,
                'short_desc': "The town of Chanderi unites with Stree to confront the monstrous headless demon Sarkata in this blockbuster horror-comedy starring Rajkummar Rao and Shraddha Kapoor.",
                'trailer_url': "https://www.youtube.com/watch?v=KVnheXwqFAw",
                'poster_file': "stree2.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/yL3pCqT8bA8lC4sNqG0n4fT9i2r.jpg",
                'color': (217, 119, 6),
                'is_active': True,
            },
            {
                'title': "Tumbbad (4K Re-Release)",
                'slug': 'tumbbad-4k-remaster',
                'primary_lang': 'hi',
                'langs': ['hi'],
                'genres': ['Horror', 'Fantasy', 'Drama'],
                'release_date': today - timedelta(days=25),  # Sep 13, 2026
                'duration': 104,
                'age_cert': 'A',
                'rating': Decimal('4.9'),
                'total_reviews': 6100,
                'short_desc': "The legendary mythological horror masterpiece returns to cinemas in pristine 4K Dolby Atmos, exploring insatiable greed and the sinister curse of Hastar.",
                'trailer_url': "https://www.youtube.com/watch?v=sN75MPxgvX8",
                'poster_file': "tumbbad.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/3oQ2uWlT1o5E8t2Z2G2mY5v5e7X.jpg",
                'color': (146, 64, 14),
                'is_active': True,
            },
            {
                'title': "Kalki 2898 AD",
                'slug': 'kalki-2898-ad',
                'primary_lang': 'hi',
                'langs': ['hi', 'te', 'ta'],
                'genres': ['Action', 'Sci-Fi', 'Fantasy'],
                'release_date': today - timedelta(days=103),
                'duration': 181,
                'age_cert': 'UA',
                'rating': Decimal('4.5'),
                'total_reviews': 6750,
                'short_desc': "In a dystopian futuristic Kasi, the immortal Ashwatthama awakens to protect the unborn savior of humanity. Starring Prabhas, Amitabh Bachchan, and Deepika Padukone.",
                'trailer_url': "https://www.youtube.com/watch?v=y1-w1TrF45A",
                'poster_file': "kalki2898.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/3b4lP5gY0yV9u5H9nI1Z8lG8rL.jpg",
                'color': (245, 158, 11),
                'is_active': True,
            },

            # --- Anime Now Showing ---
            {
                'title': "Look Back",
                'slug': 'look-back-anime',
                'primary_lang': 'ja',
                'langs': ['ja', 'en'],
                'genres': ['Anime', 'Animation', 'Drama'],
                'release_date': today - timedelta(days=4),  # Oct 4, 2026
                'duration': 58,
                'age_cert': 'UA',
                'rating': Decimal('4.9'),
                'total_reviews': 3100,
                'short_desc': "Tatsuki Fujimoto's critically acclaimed emotional masterpiece. Two young girls with opposite personalities are united by their deep passion for drawing manga.",
                'trailer_url': "https://www.youtube.com/watch?v=i9YQ_q_1_Hw",
                'poster_file': "look_back.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/y6wM2k9pY7t7kY5y8n8o1Z1b2a3.jpg",
                'color': (56, 189, 248),
                'is_active': True,
            },
            {
                'title': "My Hero Academia: You're Next",
                'slug': 'my-hero-academia-youre-next',
                'primary_lang': 'ja',
                'langs': ['ja', 'hi', 'en'],
                'genres': ['Anime', 'Animation', 'Action', 'Sci-Fi'],
                'release_date': today - timedelta(days=18),  # Sep 20, 2026
                'duration': 110,
                'age_cert': 'UA',
                'rating': Decimal('4.6'),
                'total_reviews': 3500,
                'short_desc': "Deku and Class 1-A face off against Dark Might, a sinister new villain claiming to be the true successor of All Might, in this explosive feature film.",
                'trailer_url': "https://www.youtube.com/watch?v=0hK2fA2K7sY",
                'poster_file': "mha_youre_next.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/3U9wZ0v2k9Y7t8kY5y8n8o1Z1b2.jpg",
                'color': (16, 185, 129),
                'is_active': True,
            },
            {
                'title': "Haikyu!! The Dumpster Battle",
                'slug': 'haikyu-the-dumpster-battle',
                'primary_lang': 'ja',
                'langs': ['ja', 'hi', 'en'],
                'genres': ['Anime', 'Animation', 'Comedy'],
                'release_date': today - timedelta(days=130),
                'duration': 85,
                'age_cert': 'U',
                'rating': Decimal('4.8'),
                'total_reviews': 4200,
                'short_desc': "Karasuno High and Nekoma High clash in the legendary Trash Heap Showdown at the Spring National Tournament.",
                'trailer_url': "https://www.youtube.com/watch?v=hN_7Y23lA_0",
                'poster_file': "haikyu_dumpster.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/x7f7kY5y8n8o1Z1b2a3b4c5d6e.jpg",
                'color': (249, 115, 22),
                'is_active': True,
            },
            {
                'title': "Spy x Family Code: White",
                'slug': 'spy-x-family-code-white',
                'primary_lang': 'ja',
                'langs': ['ja', 'hi', 'en'],
                'genres': ['Anime', 'Animation', 'Comedy', 'Action'],
                'release_date': today - timedelta(days=170),
                'duration': 110,
                'age_cert': 'U',
                'rating': Decimal('4.7'),
                'total_reviews': 3900,
                'short_desc': "The Forger family takes a winter weekend getaway, but Anya accidentally triggers a chain of events that threatens world peace.",
                'trailer_url': "https://www.youtube.com/watch?v=r_b1a3c5d7e",
                'poster_file': "spy_x_family.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/w7f7kY5y8n8o1Z1b2a3b4c5d6e.jpg",
                'color': (236, 72, 153),
                'is_active': True,
            },
            {
                'title': "Suzume",
                'slug': 'suzume-no-tojimari',
                'primary_lang': 'ja',
                'langs': ['ja', 'hi', 'en'],
                'genres': ['Anime', 'Animation', 'Adventure', 'Fantasy'],
                'release_date': today - timedelta(days=200),
                'duration': 121,
                'age_cert': 'U',
                'rating': Decimal('4.8'),
                'total_reviews': 5400,
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
                'release_date': today - timedelta(days=240),
                'duration': 107,
                'age_cert': 'U',
                'rating': Decimal('4.9'),
                'total_reviews': 6120,
                'short_desc': "Two strangers discover a magical cosmic connection as they wake up intermittently in each other's bodies. Makoto Shinkai's globally acclaimed masterpiece.",
                'trailer_url': "https://www.youtube.com/watch?v=xU47nhruN-Q",
                'poster_file': "your_name.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/q719jXXEzOoYaps6qFsRWa2f48k.jpg",
                'color': (168, 85, 247),
                'is_active': True,
            },


            # =========================================================
            # SECTION B: UPCOMING IN THEATERS (RELEASE DATE > TODAY)
            # =========================================================

            # --- Hollywood Upcoming (Real confirmed releases) ---
            {
                'title': "Smile 2",
                'slug': 'smile-2-movie',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Horror', 'Mystery', 'Thriller'],
                'release_date': today + timedelta(days=10),  # Oct 18, 2026
                'duration': 127,
                'age_cert': 'A',
                'rating': Decimal('4.6'),
                'total_reviews': 420,
                'short_desc': "About to embark on a world tour, global pop sensation Skye Riley begins experiencing increasingly terrifying and unexplainable supernatural events.",
                'trailer_url': "https://www.youtube.com/watch?v=0HY6QFlBzUY",
                'poster_file': "smile_2.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/ht8Uv9Ag9wsBu1Bi8X19uaTFQHN.jpg",
                'color': (220, 38, 38),
                'is_active': True,
            },
            {
                'title': "Venom: The Last Dance",
                'slug': 'venom-the-last-dance',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Action', 'Sci-Fi', 'Adventure'],
                'release_date': today + timedelta(days=17),  # Oct 25, 2026
                'duration': 110,
                'age_cert': 'UA',
                'rating': Decimal('4.7'),
                'total_reviews': 580,
                'short_desc': "Eddie Brock and Venom are on the run. Hunted by both of their worlds, the duo is forced into a devastating decision that will bring the curtains down on their last dance.",
                'trailer_url': "https://www.youtube.com/watch?v=__2bjWbetsA",
                'poster_file': "venom_last_dance.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/k42OwCUx9MgrtkYjG1vSD0m9aek.jpg",
                'color': (15, 23, 42),
                'is_active': True,
            },
            {
                'title': "Gladiator II",
                'slug': 'gladiator-2-scott',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Action', 'Adventure', 'Drama'],
                'release_date': today + timedelta(days=45),  # Nov 22, 2026
                'duration': 148,
                'age_cert': 'A',
                'rating': Decimal('4.8'),
                'total_reviews': 890,
                'short_desc': "Decades after Maximus's heroic sacrifice, his son Lucius enters the Colosseum arena to challenge the tyrannical co-emperors and restore Rome's lost glory. Directed by Ridley Scott.",
                'trailer_url': "https://www.youtube.com/watch?v=4rgYUipGJNo",
                'poster_file': "gladiator2.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/2cxhvwyEwRlysAmRH4iodkvo0z5.jpg",
                'color': (180, 83, 9),
                'is_active': True,
            },
            {
                'title': "Wicked",
                'slug': 'wicked-part-one',
                'primary_lang': 'en',
                'langs': ['en'],
                'genres': ['Fantasy', 'Musical', 'Drama'],
                'release_date': today + timedelta(days=45),  # Nov 22, 2026
                'duration': 160,
                'age_cert': 'U',
                'rating': Decimal('4.8'),
                'total_reviews': 670,
                'short_desc': "The untold story of the witches of Oz: Elphaba, a green-skinned misunderstood young woman, and Glinda, a popular blonde, form an extraordinary bond that alters their destinies.",
                'trailer_url': "https://www.youtube.com/watch?v=6COmYeLsz4c",
                'poster_file': "wicked.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/2vFuG6bWGyQUzYS9d69E5l85nIz.jpg",
                'color': (34, 197, 94),
                'is_active': True,
            },
            {
                'title': "Moana 2",
                'slug': 'moana-2-disney',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Animation', 'Adventure', 'Family', 'Musical'],
                'release_date': today + timedelta(days=50),  # Nov 27, 2026
                'duration': 100,
                'age_cert': 'U',
                'rating': Decimal('4.9'),
                'total_reviews': 950,
                'short_desc': "Moana journeys to the far seas of Oceania after receiving an unexpected call from her wayfinding ancestors, reuniting with the legendary demigod Maui.",
                'trailer_url': "https://www.youtube.com/watch?v=hDZ7y8RP5HE",
                'poster_file': "moana_2.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/4YZpsylshsvQwE2vegEZ7alIV5.jpg",
                'color': (6, 182, 212),
                'is_active': True,
            },
            {
                'title': "Mufasa: The Lion King",
                'slug': 'mufasa-the-lion-king',
                'primary_lang': 'en',
                'langs': ['en', 'hi'],
                'genres': ['Adventure', 'Drama', 'Family', 'Animation'],
                'release_date': today + timedelta(days=73),  # Dec 20, 2026
                'duration': 118,
                'age_cert': 'U',
                'rating': Decimal('4.7'),
                'total_reviews': 540,
                'short_desc': "Rafiki relays the legend of Mufasa to young lion cub Kiara, revealing the unlikely rise of the beloved king of the Pride Lands alongside his royal brother Taka.",
                'trailer_url': "https://www.youtube.com/watch?v=o17MF9vnabg",
                'poster_file': "mufasa.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/9nhjGaFLKtddDPtPaX5EmK2vYeS.jpg",
                'color': (202, 138, 4),
                'is_active': True,
            },
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
                'title': "Captain America: Brave New World",
                'slug': 'captain-america-brave-new-world',
                'primary_lang': 'en',
                'langs': ['en', 'hi', 'te'],
                'genres': ['Action', 'Sci-Fi', 'Thriller'],
                'release_date': today + timedelta(days=129),  # Feb 14, 2027
                'duration': 135,
                'age_cert': 'UA',
                'rating': Decimal('4.8'),
                'total_reviews': 430,
                'short_desc': "Sam Wilson finds himself in the middle of an international incident after meeting with newly elected U.S. President Thaddeus Ross, uncovering a nefarious global plot.",
                'trailer_url': "https://www.youtube.com/watch?v=1pHDWnXmKMY",
                'poster_file': "captain_america_brave_new_world.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/8b8R8l88Qje9dn9OE8PY05Nxl1X.jpg",
                'color': (59, 130, 246),
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

            # --- Bollywood Upcoming (Real confirmed releases) ---
            {
                'title': "Singham Again",
                'slug': 'singham-again-diwali',
                'primary_lang': 'hi',
                'langs': ['hi', 'te', 'ta'],
                'genres': ['Action', 'Crime', 'Thriller'],
                'release_date': today + timedelta(days=24),  # Nov 1, 2026 (Diwali Mega Release)
                'duration': 170,
                'age_cert': 'UA',
                'rating': Decimal('4.8'),
                'total_reviews': 920,
                'short_desc': "Bajirao Singham leads the unified Cop Universe alongside Sooryavanshi, Simmba, and Shakti Shetty on an epic cross-border rescue mission. Directed by Rohit Shetty.",
                'trailer_url': "https://www.youtube.com/watch?v=uC0_5z3h3Xo",
                'poster_file': "singham_again.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/a7z7mZ1Z9v8k7y8n8o1Z1b2a3b4.jpg",
                'color': (234, 88, 12),
                'is_active': True,
            },
            {
                'title': "Bhool Bhulaiyaa 3",
                'slug': 'bhool-bhulaiyaa-3-diwali',
                'primary_lang': 'hi',
                'langs': ['hi'],
                'genres': ['Comedy', 'Horror'],
                'release_date': today + timedelta(days=24),  # Nov 1, 2026 (Diwali Mega Clash)
                'duration': 158,
                'age_cert': 'UA',
                'rating': Decimal('4.7'),
                'total_reviews': 880,
                'short_desc': "Rooh Baba returns to the haunted kingdom of Raktaghat, confronting two rival incarnations of Manjulika. Starring Kartik Aaryan, Vidya Balan, and Madhuri Dixit.",
                'trailer_url': "https://www.youtube.com/watch?v=7pC_5b3h2Yp",
                'poster_file': "bhool_bhulaiyaa_3.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/b8z8mZ2Z9v8k7y8n8o1Z1b2a3b5.jpg",
                'color': (217, 119, 6),
                'is_active': True,
            },
            {
                'title': "Pushpa 2: The Rule",
                'slug': 'pushpa-2-the-rule',
                'primary_lang': 'hi',
                'langs': ['hi', 'te', 'ta'],
                'genres': ['Action', 'Crime', 'Drama'],
                'release_date': today + timedelta(days=58),  # Dec 5, 2026
                'duration': 185,
                'age_cert': 'UA',
                'rating': Decimal('5.0'),
                'total_reviews': 1200,
                'short_desc': "The clash between Pushpa Raj and SP Bhanwar Singh Shekhawat escalates into all-out war as Pushpa expands his red sandalwood syndicate worldwide. Starring Allu Arjun.",
                'trailer_url': "https://www.youtube.com/watch?v=1kC_5b2h1Yq",
                'poster_file': "pushpa_2.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/k7z7mZ1Z9v8k7y8n8o1Z1b2a3b6.jpg",
                'color': (220, 38, 38),
                'is_active': True,
            },
            {
                'title': "War 2",
                'slug': 'war-2-yrf',
                'primary_lang': 'hi',
                'langs': ['hi', 'te', 'ta'],
                'genres': ['Action', 'Thriller'],
                'release_date': today + timedelta(days=310),  # Aug 14, 2027
                'duration': 165,
                'age_cert': 'UA',
                'rating': Decimal('4.9'),
                'total_reviews': 620,
                'short_desc': "Major Kabir Dhaliwal returns for an explosive clash of titans across Tokyo, Madrid, and the Himalayas. Starring Hrithik Roshan, Jr. NTR, and Kiara Advani.",
                'trailer_url': "https://www.youtube.com/watch?v=tQ0mz_U3V4c",
                'poster_file': "war2.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/7I9n1B1r2C4Y5s8M1N4L8V9bT1K.jpg",
                'color': (249, 115, 22),
                'is_active': True,
            },

            # --- Anime Upcoming (Real confirmed releases) ---
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
                'title': "Demon Slayer: Kimetsu no Yaiba - Infinity Castle Arc (Movie 1)",
                'slug': 'demon-slayer-infinity-castle-part-1',
                'primary_lang': 'ja',
                'langs': ['ja', 'hi', 'en'],
                'genres': ['Anime', 'Animation', 'Action', 'Fantasy'],
                'release_date': today + timedelta(days=65),  # Dec 12, 2026
                'duration': 120,
                'age_cert': 'UA',
                'rating': Decimal('5.0'),
                'total_reviews': 1800,
                'short_desc': "Tanjiro, the Hashira, and the Demon Slayer Corps plunge into the labyrinthine Infinity Castle for the beginning of the three-part cinematic trilogy against Muzan.",
                'trailer_url': "https://www.youtube.com/watch?v=VQGCKyvzIM4",
                'poster_file': "demon_slayer_infinity_castle.jpg",
                'remote_url': "https://image.tmdb.org/t/p/w500/8b8R8l88Qje9dn9OE8PY05Nxl1X.jpg",
                'color': (225, 29, 72),
                'is_active': True,
            },
        ]

        saved_movies = {}
        for m_data in movies_definitions:
            poster_rel = ensure_movie_poster(
                filename=m_data['poster_file'],
                title=m_data['title'],
                category_color=m_data['color'],
                remote_url=m_data.get('remote_url')
            )

            movie, _ = Movie.objects.get_or_create(
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

            movie.languages.set([lang_map[c] for c in m_data['langs'] if c in lang_map])
            genre_objs = [genre_map[g.lower()] for g in m_data['genres'] if g.lower() in genre_map]
            movie.genres.set(genre_objs)

            saved_movies[m_data['slug']] = movie

        # Deactivate any legacy or obsolete movie records that are not in the curated authentic catalog
        # to ensure there are no duplicate titles (e.g. Demon Slayer in both Now Showing and Upcoming,
        # or multiple Interstellar entries) and only authentic releases are displayed.
        curated_slugs = set(saved_movies.keys())
        obsolete_movies = Movie.objects.exclude(slug__in=curated_slugs).filter(is_active=True)
        obs_count = obsolete_movies.count()
        if obs_count:
            obsolete_movies.update(is_active=False)
            self.stdout.write(self.style.WARNING(f"Deactivated {obs_count} legacy/duplicate movies outside curated catalog."))

        self.stdout.write(self.style.SUCCESS(f"Saved {len(saved_movies)} authentic real-world movies."))

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

            TheaterSeatingService.ensure_full_theater_layout(th, min_seats=30)
            theater_objs.append(th)

        self.stdout.write(self.style.SUCCESS(f"Verified {len(theater_objs)} diverse theaters."))

        # -------------------------------------------------------------
        # 6. Generate Show Schedules
        # -------------------------------------------------------------
        if options['clear_shows']:
            ShowSchedule.objects.all().delete()
            self.stdout.write(self.style.WARNING("Cleared existing show schedules."))

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
            rel_date = up_movie.release_date
            for day_offset in range(7):
                target_date = rel_date + timedelta(days=day_offset)

                for th_idx, theater in enumerate(theater_objs[:6]):
                    screens = screens_by_theater.get(theater.id, [])
                    if not screens:
                        continue
                    screen = screens[th_idx % len(screens)]

                    for st_t, end_t, base_pr in slot_templates[1:]:
                        price = base_pr + Decimal('80.00')
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

        self.stdout.write(self.style.SUCCESS("All tasks finished successfully! Authentic catalog is live."))
