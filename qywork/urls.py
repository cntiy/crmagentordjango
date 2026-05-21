from django.urls import path

from . import views

urlpatterns = [
    path("", views.index),
    path("WW_verify_lKNYL5JBAI1lduZs.txt", views.verify_domain),
    path("api/leads", views.api_leads),
    path("api/leads", views.api_leads),
    path("api/users", views.api_users),
    path("api/contact", views.api_contact),
    path("api/groupchat", views.api_groupchat),
]
