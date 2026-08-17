from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView

from service.sitemaps import PublicSitemap

handler403 = "service.views.error_403"
handler404 = "service.views.error_404"
handler500 = "service.views.error_500"
urlpatterns = [
    path("admin/", admin.site.urls),
    path("sitemap.xml", sitemap, {"sitemaps": {"public": PublicSitemap}}, name="sitemap"),
    path("robots.txt", TemplateView.as_view(template_name="robots.txt", content_type="text/plain")),
    path("", include("service.urls")),
]
