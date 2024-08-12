from django.urls import path
from .views import LongView, ShortView, GetPositionState

urlpatterns = [
    path('long/', LongView.as_view()),
    path('short/', ShortView.as_view()),
    path('ask_active_position/', GetPositionState.as_view())
]
