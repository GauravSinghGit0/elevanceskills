from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from .forms import UserRegisterForm, UserUpdateForm
from django.shortcuts import render,redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from movies.models import Movie, Booking, Payment

def home(request):
    movies = (
        Movie.objects.filter(is_active=True)
        .select_related('language')
        .prefetch_related('genres')
    )
    return render(request, 'home.html', {'movies': movies})
def register(request):
    if request.method == 'POST':
        form=UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            username=form.cleaned_data.get('username')
            password=form.cleaned_data.get('password1')
            user=authenticate(username=username,password=password)
            login(request,user)
            return redirect('profile')
    else:
        form=UserRegisterForm()
    return render(request,'users/register.html',{'form':form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                return redirect(next_url)
            if user.is_staff or user.is_superuser:
                return redirect('movie_admin_dashboard')
            return redirect('/')
    else:
        form = AuthenticationForm()
    return render(request, 'users/login.html', {'form': form})

@login_required
def profile(request):
    bookings = (
        Booking.objects.filter(user=request.user)
        .select_related('movie', 'theater', 'seat', 'payment')
        .order_by('-booked_at')
    )
    payments = (
        Payment.objects.filter(user=request.user)
        .select_related('movie', 'theater')
        .order_by('-created_at')
    )

    total_spent = sum(p.amount for p in payments if p.status == 'SUCCESS')
    successful_payments_count = sum(1 for p in payments if p.status == 'SUCCESS')
    pending_payments_count = sum(1 for p in payments if p.status == 'PENDING')
    refunded_count = sum(1 for p in payments if p.status == 'REFUNDED')
    refunded_amount = sum(p.amount for p in payments if p.status == 'REFUNDED')

    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        if u_form.is_valid():
            u_form.save()
            return redirect('profile')
    else:
        u_form = UserUpdateForm(instance=request.user)

    context = {
        'u_form': u_form,
        'bookings': bookings,
        'payments': payments,
        'total_spent': total_spent,
        'successful_payments_count': successful_payments_count,
        'pending_payments_count': pending_payments_count,
        'refunded_count': refunded_count,
        'refunded_amount': refunded_amount,
    }
    return render(request, 'users/profile.html', context)


@login_required
def reset_password(request):
    if request.method == 'POST':
        form=PasswordChangeForm(user=request.user,data=request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form=PasswordChangeForm(user=request.user)
    return render(request,'users/reset_password.html',{'form':form})

def logout_view(request):
    logout(request)
    return render(request, 'users/logout.html')