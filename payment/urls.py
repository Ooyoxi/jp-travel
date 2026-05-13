from django.urls import path
from . import views

urlpatterns = [
    path("checkout/<int:order_id>/", views.create_checkout_session, name="create_checkout_session"),
    path("simulate/<int:order_id>/", views.payment_simulate, name="payment_simulate"),
    path("success/", views.payment_success, name="payment_success"),
    path("cancel/", views.payment_cancel, name="payment_cancel"),
    path("webhook/", views.stripe_webhook, name="stripe_webhook"),
]
