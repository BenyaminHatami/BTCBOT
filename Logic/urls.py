from django.urls import path
from .views import LongView, ShortView

urlpatterns = [
    path('long/', LongView.as_view()),
    path('short/', ShortView.as_view()),
]
