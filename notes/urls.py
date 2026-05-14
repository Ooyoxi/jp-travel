from django.urls import path
from . import views

app_name = "notes"

urlpatterns = [
    path("", views.home, name="home"),
    path("notes/", views.note_list, name="note_list"),
    path("notes/<slug:slug>/", views.note_detail, name="note_detail"),
]
