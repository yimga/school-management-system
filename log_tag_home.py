import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['ALLOWED_HOSTS'] = 'testserver,localhost,127.0.0.1'
import django
django.setup()
from django.template import defaulttags
orig_url = defaulttags.url

def logging_url(parser, token):
    bits = token.split_contents()
    view_name = bits[1] if len(bits) > 1 else None
    if view_name and 'home' in view_name:
        template_name = parser.origin.name if parser.origin else '<unknown>'
        print('url tag view_name:', view_name, 'template:', template_name)
    return orig_url(parser, token)

def patch():
    defaulttags.register.tags['url'] = logging_url
patch()

from django.test import Client
from django.contrib.auth import get_user_model
User = get_user_model()
user, _ = User.objects.get_or_create(username='admin')
user.set_password('admin123')
user.is_staff = True
user.is_superuser = True
user.save()
client = Client()
client.login(username='admin', password='admin123')
client.raise_request_exception = False
response = client.get('/admin/')
print('status', response.status_code)
