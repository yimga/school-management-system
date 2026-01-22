import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from config.admin import admin_site
urlpatterns, app_name, namespace = admin_site.urls
print('app_name', app_name)
print('namespace', namespace)
for url in urlpatterns:
    if getattr(url, 'name', None) == 'home':
        print('found admin:home', url.pattern)
        break
