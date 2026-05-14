from django.urls import path
from . import views

app_name = "market"

urlpatterns = [
    path("", views.market_home, name="market_home"),
    path("articles/", views.article_list, name="article_list"),
    path("articles/<int:pk>/", views.article_detail, name="article_detail"),
    path("people/<str:person>/", views.by_person, name="by_person"),
    path("tags/<str:tag>/", views.by_tag, name="by_tag"),
    path("fetch-rss/", views.fetch_rss_view, name="fetch_rss"),
]
