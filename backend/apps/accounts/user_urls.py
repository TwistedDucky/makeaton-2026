from django.urls import path

from . import views

urlpatterns = [
    path("",        views.user_list_create, name="user-list-create"),
    path("<int:pk>/", views.user_detail,    name="user-detail"),
]
