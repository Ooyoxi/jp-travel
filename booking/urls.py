from django.urls import path
from . import views

urlpatterns = [
    path("<int:product_id>/", views.create_booking, name="create_booking"),
]
