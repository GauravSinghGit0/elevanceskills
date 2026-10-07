from django.db import migrations
from django.utils.text import slugify


def populate_movies(apps, schema_editor):
    Movie = apps.get_model('movies', 'Movie')
    for movie in Movie.objects.all():
        if not movie.title:
            movie.title = movie.name or f"Movie {movie.id}"
        if not movie.name:
            movie.name = movie.title

        if not movie.slug:
            base_slug = slugify(movie.title) or f"movie-{movie.id}"
            candidate = base_slug
            counter = 1
            while Movie.objects.filter(slug=candidate).exclude(pk=movie.pk).exists():
                candidate = f"{base_slug}-{counter}"
                counter += 1
            movie.slug = candidate

        if not movie.short_description and movie.description:
            movie.short_description = movie.description[:500]
        if not movie.description and movie.short_description:
            movie.description = movie.short_description

        if movie.image and not movie.poster:
            movie.poster = movie.image

        movie.save()


def reverse_populate(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0002_auto_20260915_0545'),
    ]

    operations = [
        migrations.RunPython(populate_movies, reverse_populate),
    ]
