from django.urls import path

from . import staff_views, views
from .auth import RateLimitedLoginView

urlpatterns = [
    path("", views.home, name="home"),
    path("services/", views.services_list, name="services"),
    path("services/<slug:slug>/", views.service_detail, name="service_detail"),
    path("about/", views.static_page, {"page": "about"}, name="about"),
    path("process/", views.static_page, {"page": "process"}, name="process"),
    path("cases/", views.static_page, {"page": "cases"}, name="cases"),
    path("warranty/", views.static_page, {"page": "warranty"}, name="warranty"),
    path("faq/", views.static_page, {"page": "faq"}, name="faq"),
    path("contacts/", views.static_page, {"page": "contacts"}, name="contacts"),
    path("privacy/", views.static_page, {"page": "privacy"}, name="privacy"),
    path("consent/", views.static_page, {"page": "consent"}, name="consent"),
    path("success/<uuid:public_id>/<str:token>/", views.success, name="success"),
    path("access/<uuid:public_id>/<str:token>/", views.exchange_access, name="client_exchange"),
    path("portal/order/", views.client_portal, name="client_portal"),
    path("portal/order/estimate/approve/", views.client_estimate_approve, name="client_estimate_approve"),
    path("private/photo/<int:pk>/", views.private_photo, name="private_photo"),
    path("health/", views.health, name="health"),
    path("readiness/", views.readiness, name="readiness"),
    path("staff/login/", RateLimitedLoginView.as_view(), name="login"),
    path("staff/logout/", views.logout_view, name="logout"),
    path("staff/", staff_views.staff_dashboard, name="dashboard"),
    path("staff/orders/", staff_views.order_list, name="staff_orders"),
    path("staff/orders/<int:pk>/", staff_views.order_detail, name="staff_order_detail"),
    path("staff/orders/<int:pk>/status/", staff_views.change_status, name="change_status"),
    path("staff/orders/<int:pk>/assign/", staff_views.assign_order, name="assign_order"),
    path("staff/orders/<int:pk>/schedule/", staff_views.update_schedule, name="update_schedule"),
    path("staff/orders/<int:pk>/price/", staff_views.update_price, name="update_price"),
    path(
        "staff/orders/<int:pk>/estimate/approve/",
        staff_views.record_manual_approval,
        name="record_manual_approval",
    ),
    path("staff/orders/<int:pk>/estimate/add/", staff_views.add_estimate_item, name="add_estimate_item"),
    path(
        "staff/orders/<int:pk>/estimate/<int:item_id>/delete/",
        staff_views.delete_estimate_item,
        name="delete_estimate_item",
    ),
    path("staff/orders/<int:pk>/comment/", staff_views.add_comment, name="add_comment"),
    path("staff/orders/<int:pk>/link/", staff_views.reissue_link, name="reissue_link"),
    path(
        "staff/orders/<int:pk>/notifications/<int:notification_id>/retry/",
        staff_views.retry_notification,
        name="retry_notification",
    ),
]
