from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import (
    Movie, MovieImage, Genre, Language, CastMember,
    Theater, Screen, ShowSchedule, Review, ReviewReport,
    validate_image_file, validate_youtube_url, extract_youtube_video_id
)


class MovieForm(forms.ModelForm):
    """
    Industrial form for adding and editing movies with clean section organization.
    """
    assigned_theaters = forms.ModelMultipleChoiceField(
        queryset=Theater.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Assign to Multiplexes / Theaters"
    )

    class Meta:
        model = Movie
        fields = [
            'title', 'slug', 'short_description', 'detailed_description',
            'release_date', 'age_certification', 'duration',
            'language', 'languages', 'genres',
            'director_name', 'director', 'cast_members',
            'poster', 'trailer_url', 'is_active'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Inception'}),
            'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Auto-generated from title if blank'}),
            'short_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Short summary for cards and previews (max 500 chars)'}),
            'detailed_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 6, 'placeholder': 'Full synopsis and storyline'}),
            'release_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'age_certification': forms.Select(attrs={'class': 'form-control'}),
            'duration': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 600}),
            'language': forms.Select(attrs={'class': 'form-control'}),
            'languages': forms.SelectMultiple(attrs={'class': 'form-control', 'size': 4}),
            'genres': forms.SelectMultiple(attrs={'class': 'form-control', 'size': 5}),
            'director_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Christopher Nolan'}),
            'director': forms.Select(attrs={'class': 'form-control'}),
            'cast_members': forms.SelectMultiple(attrs={'class': 'form-control', 'size': 6}),
            'poster': forms.ClearableFileInput(attrs={'class': 'form-control-file', 'accept': 'image/jpeg,image/png,image/webp'}),
            'trailer_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://www.youtube.com/watch?v=...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_theaters'].queryset = Theater.objects.all().order_by('city', 'name')
        if self.instance and self.instance.pk:
            current_ids = Theater.objects.filter(
                Q(movie=self.instance) | Q(shows__movie=self.instance)
            ).values_list('id', flat=True)
            self.fields['assigned_theaters'].initial = list(current_ids)

    def clean_trailer_url(self):
        url = self.cleaned_data.get('trailer_url')
        if url:
            video_id = extract_youtube_video_id(url)
            if not video_id:
                raise ValidationError(
                    "Invalid YouTube URL. Please provide a standard YouTube video URL "
                    "(e.g., https://www.youtube.com/watch?v=... or https://youtu.be/...)."
                )
        return url

    def clean_poster(self):
        poster = self.cleaned_data.get('poster')
        if poster and hasattr(poster, 'file'):
            validate_image_file(poster)
        return poster

    def save(self, commit=True):
        movie = super().save(commit=commit)
        if commit:
            selected_theaters = self.cleaned_data.get('assigned_theaters', [])
            for th in selected_theaters:
                if not th.movie:
                    th.movie = movie
                    th.save(update_fields=['movie'])
        return movie


class MovieImageForm(forms.ModelForm):
    """
    Form for uploading and editing movie gallery/poster images.
    """
    class Meta:
        model = MovieImage
        fields = ['image', 'caption', 'is_primary', 'display_order']
        widgets = {
            'image': forms.ClearableFileInput(attrs={'class': 'form-control-file', 'accept': 'image/jpeg,image/png,image/webp'}),
            'caption': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional image caption'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'style': 'max-width: 100px;'}),
        }

    def clean_image(self):
        img = self.cleaned_data.get('image')
        if img and hasattr(img, 'file'):
            validate_image_file(img)
        return img


class ReviewForm(forms.ModelForm):
    """
    Form for verified viewers to submit or update a rating and review.
    """
    RATING_CHOICES = [
        (5, '★★★★★ (5 - Outstanding)'),
        (4, '★★★★☆ (4 - Very Good)'),
        (3, '★★★☆☆ (3 - Average)'),
        (2, '★★☆☆☆ (2 - Below Average)'),
        (1, '★☆☆☆☆ (1 - Poor)'),
    ]

    rating = forms.ChoiceField(
        choices=RATING_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control form-control-lg font-weight-bold text-warning'})
    )

    class Meta:
        model = Review
        fields = ['rating', 'title', 'comment']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Summarize your thoughts (e.g. Masterpiece visuals!)'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'What did you think of the story, acting, direction, and experience?'}),
        }

    def clean_rating(self):
        rating_val = self.cleaned_data.get('rating')
        try:
            val = int(rating_val)
            if val < 1 or val > 5:
                raise ValidationError("Rating must be between 1 and 5 stars.")
            return val
        except (ValueError, TypeError):
            raise ValidationError("Please provide a valid rating number.")

    def clean_comment(self):
        comment = self.cleaned_data.get('comment', '').strip()
        if len(comment) < 5:
            raise ValidationError("Review comment must be at least 5 characters long.")
        return comment


class ReviewReportForm(forms.ModelForm):
    """
    Form for reporting inappropriate reviews.
    """
    class Meta:
        model = ReviewReport
        fields = ['reason', 'details']
        widgets = {
            'reason': forms.Select(attrs={'class': 'form-control'}),
            'details': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Please provide details on why this review violates guidelines (optional)'}),
        }


class ShowScheduleForm(forms.ModelForm):
    """
    Form for scheduling shows with conflict validation.
    """
    class Meta:
        model = ShowSchedule
        fields = ['movie', 'theater', 'screen', 'start_time', 'end_time', 'price', 'status']
        widgets = {
            'movie': forms.Select(attrs={'class': 'form-control'}),
            'theater': forms.Select(attrs={'class': 'form-control'}),
            'screen': forms.Select(attrs={'class': 'form-control'}),
            'start_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.50'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['movie'].queryset = Movie.objects.all().order_by('title')
        self.fields['theater'].queryset = Theater.objects.all().order_by('city', 'name')
        if 'theater' in self.data:
            try:
                theater_id = int(self.data.get('theater'))
                self.fields['screen'].queryset = Screen.objects.filter(theater_id=theater_id)
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.theater:
            self.fields['screen'].queryset = self.instance.theater.screens.all()


class TheaterForm(forms.ModelForm):
    """
    Form for creating and editing cinema theaters / multiplexes.
    """
    num_screens = forms.IntegerField(
        required=False,
        initial=2,
        min_value=1,
        max_value=10,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 10}),
        help_text="Auditoriums to auto-create (Audi 1, Audi 2...) if this is a new theater"
    )

    class Meta:
        model = Theater
        fields = ['name', 'city', 'address', 'movie', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., PVR Director\'s Cut'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Mumbai, Delhi NCR, Bengaluru'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Street address, mall name, and landmark'}),
            'movie': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['movie'].queryset = Movie.objects.all().order_by('title')
        self.fields['movie'].required = False
        if not self.instance.pk:
            self.fields['is_active'].initial = True


class AssignTheatersForm(forms.Form):
    """
    Form for assigning multiple theaters to a movie with optional show generation.
    """
    theaters = forms.ModelMultipleChoiceField(
        queryset=Theater.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input theater-box'}),
        required=False,
        label="Select Multiplexes / Theaters"
    )
    auto_create_shows = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Auto-generate standard daily show schedules for selected theaters"
    )
    days_ahead = forms.IntegerField(
        required=False,
        initial=3,
        min_value=1,
        max_value=7,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 7}),
        label="Days to schedule ahead (1-7 days)"
    )
    ticket_price = forms.DecimalField(
        required=False,
        initial=180.00,
        min_value=50.00,
        max_value=2000.00,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '10.00'}),
        label="Standard ticket price (₹)"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['theaters'].queryset = Theater.objects.all().order_by('city', 'name')
