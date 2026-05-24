from django.urls import path

from . import views

app_name = "feedback_operator"

urlpatterns = [
    path("voice-of-customer/", views.voice_of_customer, name="voice_of_customer"),
    path("product-feedback/", views.voice_of_customer, name="product_feedback"),
    path("product-roadmap/", views.product_roadmap, name="product_roadmap"),
    path("feedback/<int:pk>/action/", views.operator_feedback_action, name="operator_feedback_action"),
    path("feature/<int:pk>/roadmap/", views.add_to_roadmap, name="add_to_roadmap"),
]
