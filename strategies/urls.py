from django.urls import path
from . import views

app_name = "strategies"

urlpatterns = [
    path("", views.strategy_list, name="strategy_list"),
    path("box-strategy/", views.box_strategy_view, name="box_strategy"),
    path("<slug:slug>/", views.strategy_detail, name="strategy_detail"),
    path("<slug:slug>/code/", views.strategy_code, name="strategy_code"),
    path("<slug:slug>/run/", views.run_strategy_view, name="run_strategy"),
]
