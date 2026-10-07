from django.urls import path
from . import views

urlpatterns = [
    path('', views.movie_list, name='movie_list'),

    # Staff Admin Management (Must precede slug catch-all)
    path('manage/', views.admin_dashboard, name='movie_admin_dashboard'),
    path('manage/analytics/', views.admin_analytics_dashboard, name='admin_analytics_dashboard'),
    path('manage/analytics/export/', views.admin_analytics_export_csv, name='admin_analytics_export_csv'),
    path('manage/movies/create/', views.admin_movie_create, name='movie_admin_create'),
    path('manage/movies/<int:movie_id>/edit/', views.admin_movie_edit, name='movie_admin_edit'),
    path('manage/movies/<int:movie_id>/delete/', views.admin_movie_delete, name='movie_admin_delete'),
    path('manage/movies/<int:movie_id>/toggle-status/', views.admin_movie_toggle_status, name='movie_admin_toggle_status'),
    path('manage/movies/<int:movie_id>/theaters/', views.admin_movie_assign_theaters, name='movie_admin_assign_theaters'),
    path('manage/movies/<int:movie_id>/gallery/', views.admin_movie_gallery, name='movie_admin_gallery'),
    path('manage/reports/', views.admin_reports_list, name='movie_admin_reports'),
    path('manage/reports/<int:report_id>/action/', views.admin_report_action, name='movie_admin_report_action'),

    # Theaters & Multiplexes Management
    path('manage/theaters/', views.admin_theaters_list, name='admin_theaters_list'),
    path('manage/theaters/create/', views.admin_theater_create, name='admin_theater_create'),
    path('manage/theaters/<int:theater_id>/edit/', views.admin_theater_edit, name='admin_theater_edit'),
    path('manage/theaters/<int:theater_id>/delete/', views.admin_theater_delete, name='admin_theater_delete'),
    path('manage/theaters/<int:theater_id>/toggle-status/', views.admin_theater_toggle_status, name='admin_theater_toggle_status'),

    # Show Schedules Management
    path('manage/shows/', views.admin_shows_list, name='admin_shows_list'),
    path('manage/shows/create/', views.admin_show_create, name='admin_show_create'),
    path('manage/shows/<int:show_id>/edit/', views.admin_show_edit, name='admin_show_edit'),
    path('manage/shows/<int:show_id>/delete/', views.admin_show_delete, name='admin_show_delete'),

    # Reviews and Ratings
    path('review/add/<slug:slug>/', views.add_review, name='add_review'),
    path('review/edit/<int:review_id>/', views.edit_review, name='edit_review'),
    path('review/report/<int:review_id>/', views.report_review, name='report_review'),

    # Legacy theater & seat booking routes (Preserved)
    path('<int:movie_id>/theaters/', views.theater_list, name='theater_list'),
    path('theater/<int:theater_id>/seats/book/', views.book_seats, name='book_seats'),
    path('theater/<int:theater_id>/seats/toggle-lock/', views.toggle_seat_lock, name='toggle_seat_lock'),
    path('theater/<int:theater_id>/seats/live-status/', views.seat_live_status, name='seat_live_status'),

    # Payment Gateway & Online Booking Workflow Routes
    path('theater/<int:theater_id>/payment/create-order/', views.create_payment_order_view, name='create_payment_order'),
    path('payment/verify/', views.verify_payment_view, name='verify_payment'),
    path('payment/failure/', views.payment_failure_view, name='payment_failure'),
    path('payment/cancel/', views.payment_cancel_view, name='payment_cancel'),
    path('payment/retry/', views.payment_retry_view, name='payment_retry'),
    path('payment/webhook/', views.razorpay_webhook_view, name='razorpay_webhook'),

    # Live Search, Dynamic Filtering, and Recommendation API
    path('api/discovery/', views.movie_discovery_api, name='movie_discovery_api'),

    # PDF Ticket Generation, Download, and Admission Gate Verification
    path('tickets/<int:booking_id>/download/', views.download_ticket_view, name='download_ticket'),
    path('tickets/payment/<int:payment_id>/download/', views.download_payment_tickets_view, name='download_payment_tickets'),
    path('tickets/verify/<int:booking_id>/', views.verify_ticket_view, name='verify_ticket'),

    # Movie details by ID (Redirects to slug)
    path('id/<int:movie_id>/', views.movie_detail_by_id, name='movie_detail_by_id'),

    # Movie details by slug
    path('<slug:slug>/', views.movie_detail, name='movie_detail'),
]