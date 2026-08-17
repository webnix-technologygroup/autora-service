from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Service


class PublicSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return ["home", "services", "about", "contacts", "privacy"] + list(
            Service.objects.filter(is_active=True)
        )

    def location(self, item):
        return reverse("service_detail", args=[item.slug]) if isinstance(item, Service) else reverse(item)
