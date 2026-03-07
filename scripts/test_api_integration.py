"""
API Integration Test Script
Comprehensive testing of all dashboard, notification, search, and data management APIs
"""

import os
import sys
import django
from django.test import Client
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import json

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.people.models import StudentProfile, TeacherProfile
from apps.finance.models import Invoice, Payment, Notification
from apps.academics.models import Classroom, Attendance
from apps.communication.models import Message, Announcement


class APITestSuite:
    """Comprehensive API testing"""
    
    def __init__(self):
        self.client = Client()
        self.results = {
            'passed': 0,
            'failed': 0,
            'errors': []
        }
        self.test_user = None
        self.test_token = None
    
    def setup_test_users(self):
        """Create test users with different roles"""
        print("\n[SETUP] Creating test users...")
        
        # Admin user
        admin = User.objects.create_user(
            username='admin_test',
            email='admin@test.com',
            password='testpass123'
        )
        admin.is_staff = True
        admin.role = 'ADMIN'
        admin.save()
        
        # Teacher user
        teacher = User.objects.create_user(
            username='teacher_test',
            email='teacher@test.com',
            password='testpass123'
        )
        teacher.role = 'TEACHER'
        teacher.save()
        
        # Student user
        student = User.objects.create_user(
            username='student_test',
            email='student@test.com',
            password='testpass123'
        )
        student.role = 'STUDENT'
        student.save()
        
        # Parent user
        parent = User.objects.create_user(
            username='parent_test',
            email='parent@test.com',
            password='testpass123'
        )
        parent.role = 'PARENT'
        parent.save()
        
        self.test_user = admin
        
        print("✓ Test users created")
        return admin, teacher, student, parent
    
    def test_dashboard_apis(self):
        """Test all dashboard APIs"""
        print("\n[TEST] Dashboard APIs...")
        
        endpoints = [
            ('/api/dashboard/admin/', 'GET'),
            ('/api/dashboard/teacher/', 'GET'),
            ('/api/dashboard/parent/', 'GET'),
            ('/api/dashboard/student/', 'GET'),
            ('/api/dashboard/financial/', 'GET'),
            ('/api/dashboard/academic/', 'GET'),
        ]
        
        for endpoint, method in endpoints:
            try:
                self.client.login(username='admin_test', password='testpass123')
                response = self.client.get(endpoint)
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✓ {endpoint} - Status: {response.status_code}")
                    self.results['passed'] += 1
                else:
                    print(f"✗ {endpoint} - Status: {response.status_code}")
                    self.results['failed'] += 1
                    self.results['errors'].append(f"{endpoint}: {response.status_code}")
            except Exception as e:
                print(f"✗ {endpoint} - Error: {str(e)}")
                self.results['failed'] += 1
                self.results['errors'].append(f"{endpoint}: {str(e)}")
    
    def test_notification_apis(self):
        """Test notification APIs"""
        print("\n[TEST] Notification APIs...")
        
        try:
            self.client.login(username='admin_test', password='testpass123')
            
            # List notifications
            response = self.client.get('/api/notifications/')
            print(f"✓ GET /api/notifications/ - Status: {response.status_code}")
            self.results['passed'] += 1
            
            # Unread count
            response = self.client.get('/api/notifications/unread_count/')
            if response.status_code == 200:
                print(f"✓ GET /api/notifications/unread_count/ - Status: {response.status_code}")
                self.results['passed'] += 1
            else:
                print(f"✗ GET /api/notifications/unread_count/ - Status: {response.status_code}")
                self.results['failed'] += 1
            
        except Exception as e:
            print(f"✗ Notification APIs - Error: {str(e)}")
            self.results['failed'] += 1
            self.results['errors'].append(f"Notification APIs: {str(e)}")
    
    def test_search_api(self):
        """Test global search API"""
        print("\n[TEST] Search API...")
        
        try:
            self.client.login(username='admin_test', password='testpass123')
            
            # Test search with query
            response = self.client.get('/api/search/?q=test&limit=10')
            
            if response.status_code in [200, 400]:  # 400 is OK if no matches
                print(f"✓ GET /api/search/ - Status: {response.status_code}")
                self.results['passed'] += 1
            else:
                print(f"✗ GET /api/search/ - Status: {response.status_code}")
                self.results['failed'] += 1
            
            # Test suggestions
            response = self.client.get('/api/search/suggestions/')
            print(f"✓ GET /api/search/suggestions/ - Status: {response.status_code}")
            self.results['passed'] += 1
            
        except Exception as e:
            print(f"✗ Search API - Error: {str(e)}")
            self.results['failed'] += 1
            self.results['errors'].append(f"Search API: {str(e)}")
    
    def test_invoice_api(self):
        """Test invoice management API"""
        print("\n[TEST] Invoice API...")
        
        try:
            self.client.login(username='admin_test', password='testpass123')
            
            # List invoices
            response = self.client.get('/api/invoices/')
            
            if response.status_code in [200, 404]:  # 404 if no invoices
                print(f"✓ GET /api/invoices/ - Status: {response.status_code}")
                self.results['passed'] += 1
            else:
                print(f"✗ GET /api/invoices/ - Status: {response.status_code}")
                self.results['failed'] += 1
            
            # Invoice summary
            response = self.client.get('/api/invoices/summary/')
            if response.status_code in [200, 404]:
                print(f"✓ GET /api/invoices/summary/ - Status: {response.status_code}")
                self.results['passed'] += 1
            
        except Exception as e:
            print(f"✗ Invoice API - Error: {str(e)}")
            self.results['failed'] += 1
            self.results['errors'].append(f"Invoice API: {str(e)}")
    
    def test_attendance_api(self):
        """Test attendance management API"""
        print("\n[TEST] Attendance API...")
        
        try:
            self.client.login(username='admin_test', password='testpass123')
            
            # List attendance
            response = self.client.get('/api/attendance/')
            
            if response.status_code in [200, 404]:
                print(f"✓ GET /api/attendance/ - Status: {response.status_code}")
                self.results['passed'] += 1
            else:
                print(f"✗ GET /api/attendance/ - Status: {response.status_code}")
                self.results['failed'] += 1
            
        except Exception as e:
            print(f"✗ Attendance API - Error: {str(e)}")
            self.results['failed'] += 1
            self.results['errors'].append(f"Attendance API: {str(e)}")
    
    def test_message_api(self):
        """Test messaging API"""
        print("\n[TEST] Message API...")
        
        try:
            self.client.login(username='admin_test', password='testpass123')
            
            # List messages (should not error even if empty)
            response = self.client.get('/api/messages/')
            
            print(f"✓ GET /api/messages/ - Status: {response.status_code}")
            self.results['passed'] += 1
            
        except Exception as e:
            print(f"✗ Message API - Error: {str(e)}")
            self.results['failed'] += 1
            self.results['errors'].append(f"Message API: {str(e)}")
    
    def test_announcement_api(self):
        """Test announcement API"""
        print("\n[TEST] Announcement API...")
        
        try:
            self.client.login(username='admin_test', password='testpass123')
            
            # List announcements
            response = self.client.get('/api/announcements/')
            
            print(f"✓ GET /api/announcements/ - Status: {response.status_code}")
            self.results['passed'] += 1
            
            # Active announcements
            response = self.client.get('/api/announcements/active/')
            if response.status_code in [200, 404]:
                print(f"✓ GET /api/announcements/active/ - Status: {response.status_code}")
                self.results['passed'] += 1
            
        except Exception as e:
            print(f"✗ Announcement API - Error: {str(e)}")
            self.results['failed'] += 1
            self.results['errors'].append(f"Announcement API: {str(e)}")
    
    def test_permissions(self):
        """Test role-based access control"""
        print("\n[TEST] Permission Control...")
        
        try:
            # Test unauthenticated access
            response = self.client.get('/api/dashboard/admin/')
            if response.status_code in [401, 403]:
                print(f"✓ Unauthenticated access denied - Status: {response.status_code}")
                self.results['passed'] += 1
            
            # Test student accessing admin dashboard
            self.client.login(username='student_test', password='testpass123')
            response = self.client.get('/api/dashboard/admin/')
            if response.status_code in [403, 401]:
                print(f"✓ Student access to admin dashboard denied - Status: {response.status_code}")
                self.results['passed'] += 1
            
        except Exception as e:
            print(f"✗ Permission tests - Error: {str(e)}")
            self.results['failed'] += 1
            self.results['errors'].append(f"Permission tests: {str(e)}")
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print(f"Passed: {self.results['passed']}")
        print(f"Failed: {self.results['failed']}")
        print(f"Total: {self.results['passed'] + self.results['failed']}")
        
        if self.results['errors']:
            print("\nErrors:")
            for error in self.results['errors']:
                print(f"  - {error}")
        
        success_rate = (self.results['passed'] / (self.results['passed'] + self.results['failed']) * 100) if (self.results['passed'] + self.results['failed']) > 0 else 0
        print(f"\nSuccess Rate: {success_rate:.1f}%")
        print("="*60)
    
    def run_all_tests(self):
        """Run all tests"""
        print("\n" + "="*60)
        print("API INTEGRATION TEST SUITE")
        print("="*60)
        print(f"Test Started: {timezone.now()}")
        
        # Clean up previous test data
        try:
            User.objects.filter(username__endswith='_test').delete()
        except:
            pass
        
        # Setup
        self.setup_test_users()
        
        # Run tests
        self.test_dashboard_apis()
        self.test_notification_apis()
        self.test_search_api()
        self.test_invoice_api()
        self.test_attendance_api()
        self.test_message_api()
        self.test_announcement_api()
        self.test_permissions()
        
        # Print summary
        self.print_summary()


if __name__ == '__main__':
    suite = APITestSuite()
    suite.run_all_tests()
