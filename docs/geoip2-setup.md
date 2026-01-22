# GeoIP2 Setup Guide

This guide helps you configure MaxMind's GeoIP2 database for IP-to-country mapping in the compliance access control system.

## Overview

The Country Access Control feature uses GeoIP2 to block or allow traffic based on geographic location. Without GeoIP2 configured, country-based rules will be skipped (IP-based rules still work).

## Prerequisites

- Django application with `django.contrib.gis` available
- Write access to server filesystem for database files
- Internet connection for initial download

## Step 1: Create MaxMind Account

1. Go to https://www.maxmind.com/en/geolite2/signup
2. Create a free account (GeoLite2 is free for production use)
3. Verify your email address
4. Log in to your account

## Step 2: Generate License Key

1. Navigate to "Account" → "Manage License Keys"
2. Click "Generate New License Key"
3. Give it a descriptive name (e.g., "School Management System")
4. Select "No" for "Will this key be used for GeoIP Update?" (unless using geoipupdate tool)
5. Confirm and save the license key securely

## Step 3: Download GeoLite2-Country Database

### Option A: Manual Download (Recommended for Development)

1. Go to https://www.maxmind.com/en/accounts/current/geoip/downloads
2. Find "GeoLite2 Country" in the list
3. Click "Download GZIP" for the database format (`.mmdb`)
4. Extract the `.tar.gz` file to get `GeoLite2-Country.mmdb`
5. Place the file in a secure directory on your server:
   ```
   mkdir -p /var/geoip/
   cp GeoLite2-Country.mmdb /var/geoip/
   ```

### Option B: Automated Updates with geoipupdate (Recommended for Production)

1. Install geoipupdate tool:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install geoipupdate
   
   # CentOS/RHEL
   sudo yum install geoipupdate
   
   # macOS
   brew install geoipupdate
   ```

2. Configure `/etc/GeoIP.conf`:
   ```
   AccountID YOUR_ACCOUNT_ID
   LicenseKey YOUR_LICENSE_KEY
   EditionIDs GeoLite2-Country
   DatabaseDirectory /var/geoip
   ```

3. Run initial update:
   ```bash
   sudo geoipupdate
   ```

4. Set up weekly cron job for updates:
   ```bash
   sudo crontab -e
   # Add line:
   0 2 * * 3 /usr/bin/geoipupdate
   ```

## Step 4: Configure Django Settings

Add to `config/settings.py` or set environment variables:

```python
# GeoIP2 Configuration
GEOIP_PATH = os.getenv('GEOIP_PATH', '/var/geoip/')

# Install django.contrib.gis if not already in INSTALLED_APPS
INSTALLED_APPS = [
    # ... other apps
    'django.contrib.gis',  # Required for GeoIP2
]
```

Or set environment variable:
```bash
export GEOIP_PATH=/var/geoip/
```

## Step 5: Test GeoIP2 Integration

Run Django shell to test:

```python
python manage.py shell

from django.contrib.gis.geoip2 import GeoIP2

g = GeoIP2()

# Test with known IPs
print(g.country('8.8.8.8'))  # Should return: {'country_code': 'US', 'country_name': 'United States'}
print(g.country('41.204.224.1'))  # Cameroon IP
print(g.country('105.112.0.1'))  # Nigeria IP

# Test the access control function
from apps.compliance.access_control import get_country_from_ip
print(get_country_from_ip('8.8.8.8'))  # Should return 'US'
```

Expected output:
```
{'country_code': 'US', 'country_name': 'United States'}
CM
US
```

## Step 6: Verify Country Access Rules Work

1. Go to Django admin: `/admin/compliance/countryaccessrule/`
2. Create a test rule:
   - Rule Type: DENY
   - Country Code: US
   - Description: "Test rule - deny US traffic"
   - Is Active: ✓
3. Try accessing the site from a US IP or using a VPN
4. You should see a 403 Forbidden error
5. Delete the test rule after verification

## Troubleshooting

### Error: "No module named 'geoip2'"

**Solution:** Install the GeoIP2 Python library:
```bash
pip install geoip2
```

### Error: "GeoIP2 path does not exist"

**Solution:** Ensure `GEOIP_PATH` points to a valid directory containing `GeoLite2-Country.mmdb`:
```bash
ls -la /var/geoip/
# Should show: GeoLite2-Country.mmdb
```

### Country lookup returns None

**Possible causes:**
1. Database file is outdated or corrupted → Re-download
2. IP address is private (192.168.x.x, 10.x.x.x) → GeoIP2 only works with public IPs
3. Database file permissions → Ensure Django process can read the file:
   ```bash
   sudo chmod 644 /var/geoip/GeoLite2-Country.mmdb
   ```

### Performance Issues

**Solution:** GeoIP2 lookups are cached for 5 minutes in the access control system. For high-traffic sites:

1. Consider using Redis for cache backend:
   ```python
   CACHES = {
       'default': {
           'BACKEND': 'django_redis.cache.RedisCache',
           'LOCATION': 'redis://127.0.0.1:6379/1',
       }
   }
   ```

2. Monitor cache hit rates via Django cache stats

## Production Checklist

- [ ] MaxMind account created and verified
- [ ] License key generated and stored securely
- [ ] GeoLite2-Country.mmdb downloaded and placed in `/var/geoip/`
- [ ] geoipupdate configured for weekly updates
- [ ] GEOIP_PATH set in Django settings or environment
- [ ] django.contrib.gis installed
- [ ] geoip2 Python package installed
- [ ] Test country lookup successful
- [ ] Country access rules tested
- [ ] File permissions verified (644 for .mmdb)
- [ ] Cache backend configured (Redis recommended)
- [ ] Monitoring set up for GeoIP2 errors

## Alternative: GeoIP2 Web Service (Optional)

For very high-traffic sites, MaxMind offers a paid web service API that doesn't require local database files:

1. Subscribe at https://www.maxmind.com/en/geoip2-precision-services
2. Update `access_control.py` to use web service instead of local database
3. Benefits: Always up-to-date, no disk I/O, no update management
4. Drawback: Requires internet connection, adds latency

## License Information

**GeoLite2 Databases:**
- Free for production use
- Updated weekly by MaxMind
- Less accurate than paid GeoIP2 databases (~99.8% country accuracy for GeoLite2 vs 99.99% for paid)
- Sufficient for access control use cases

**Attribution Required:**
Include this notice in your application's legal/about page:
> "This product includes GeoLite2 data created by MaxMind, available from https://www.maxmind.com"

## Additional Resources

- MaxMind Documentation: https://dev.maxmind.com/geoip/docs
- Django GeoIP2 Docs: https://docs.djangoproject.com/en/stable/ref/contrib/gis/geoip2/
- GeoIP Update Tool: https://github.com/maxmind/geoipupdate
- Country Code Reference (ISO 3166-1 alpha-2): https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2

## Support

If you encounter issues not covered in this guide:
1. Check Django logs for GeoIP2-related errors
2. Verify database file integrity: `file GeoLite2-Country.mmdb` should show "MaxMind DB database"
3. Test with known public IPs (not localhost or private ranges)
4. Review MaxMind documentation for changes to download process
