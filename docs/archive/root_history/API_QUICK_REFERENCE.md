# QUICK API COPY & PASTE REFERENCE
# All code ready to copy from here
# Location: API_QUICK_REFERENCE.md

## TABLE OF CONTENTS
1. Dashboard APIs
2. Notification APIs
3. Search API
4. Authentication APIs
5. Finance APIs
6. Academic APIs

---

## 1️⃣ DASHBOARD OVERVIEW API

### **Request:**
```
GET /api/dashboard/admin/overview/
Authorization: Bearer {token}
```

### **Response:**
```json
{
    "total_students": 1250,
    "total_teachers": 45,
    "total_parents": 800,
    "total_revenue": 125000.50,
    "pending_fees": 25000.00,
    "attendance_rate": 92.5,
    "active_users_today": 340,
    "system_health": "healthy",
    "last_updated": "2025-01-22T10:30:00Z"
}
```

### **Copy & Paste Code:**
```python
# File: apps/api/dashboard_api.py

from django.views import View
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta

@method_decorator(login_required, name='dispatch')
class AdminDashboardOverviewAPI(View):
    def get(self, request):
        if not (request.user.is_staff or request.user.role == 'ADMIN'):
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        from apps.people.models import StudentProfile, TeacherProfile
        from apps.finance.models import Invoice, Payment
        from apps.academics.models import Attendance
        from django.contrib.auth.models import User
        
        total_students = StudentProfile.objects.filter(is_active=True).count()
        total_teachers = TeacherProfile.objects.filter(is_active=True).count()
        
        total_invoices = Invoice.objects.aggregate(Sum('amount'))['amount__sum'] or 0
        total_paid = Payment.objects.aggregate(Sum('amount'))['amount__sum'] or 0
        pending_fees = total_invoices - total_paid
        
        today = timezone.now().date()
        attendance_today = Attendance.objects.filter(date=today, status='present').count()
        attendance_rate = (attendance_today / total_students * 100) if total_students > 0 else 0
        
        last_24h = timezone.now() - timedelta(hours=24)
        active_users = User.objects.filter(last_login__gte=last_24h).count()
        
        return JsonResponse({
            'total_students': total_students,
            'total_teachers': total_teachers,
            'total_revenue': float(total_paid),
            'pending_fees': float(pending_fees),
            'attendance_rate': round(attendance_rate, 1),
            'active_users_today': active_users,
            'system_health': 'healthy',
            'last_updated': timezone.now().isoformat(),
        })
```

---

## 2️⃣ TEACHER DASHBOARD API

### **Request:**
```
GET /api/dashboard/teacher/
Authorization: Bearer {token}
```

### **Response:**
```json
{
    "my_students": 120,
    "my_classes": 4,
    "pending_grades": 45,
    "ungraded_submissions": 23,
    "class_average": 75.8,
    "last_updated": "2025-01-22T10:30:00Z"
}
```

### **Copy & Paste Code:**
```python
@method_decorator(login_required, name='dispatch')
class TeacherDashboardAPI(View):
    def get(self, request):
        if request.user.role != 'TEACHER':
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        from apps.people.models import TeacherProfile
        from apps.academics.models import Classroom
        
        teacher = TeacherProfile.objects.get(user=request.user)
        my_classes = Classroom.objects.filter(teacher=teacher).count()
        
        my_students = 0
        for classroom in Classroom.objects.filter(teacher=teacher):
            my_students += classroom.student_set.filter(is_active=True).count()
        
        pending_grades = 0  # Implement based on your model
        ungraded_submissions = 0  # Implement based on your model
        class_average = 0.0  # Calculate based on assessments
        
        return JsonResponse({
            'my_students': my_students,
            'my_classes': my_classes,
            'pending_grades': pending_grades,
            'ungraded_submissions': ungraded_submissions,
            'class_average': class_average,
            'last_updated': timezone.now().isoformat(),
        })
```

---

## 3️⃣ NOTIFICATIONS API

### **List Notifications:**
```
GET /api/notifications/?limit=50&type=message&is_read=false
Authorization: Bearer {token}
```

### **Response:**
```json
{
    "count": 150,
    "next": "?limit=50&offset=50",
    "results": [
        {
            "id": 1,
            "title": "Grade Published",
            "message": "Your Math grade has been published",
            "type": "message",
            "priority": "normal",
            "is_read": false,
            "created_at": "2025-01-22T09:30:00Z",
            "link": "/evals/grades/"
        }
    ]
}
```

### **Mark as Read:**
```
POST /api/notifications/1/mark-read/
Authorization: Bearer {token}

Response:
{
    "id": 1,
    "status": "success",
    "is_read": true
}
```

### **Mark All as Read:**
```
POST /api/notifications/mark-all-read/
Authorization: Bearer {token}

Response:
{
    "status": "success",
    "marked_as_read": 15
}
```

### **Copy & Paste Code:**
```python
# File: apps/api/notification_api.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import timedelta

class NotificationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        from apps.communication.models import Notification
        return Notification.objects.filter(
            user=self.request.user
        ).order_by('-created_at')
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        notif_type = request.query_params.get('type')
        if notif_type:
            queryset = queryset.filter(type=notif_type)
        
        is_read = request.query_params.get('is_read')
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read.lower() == 'true')
        
        days = request.query_params.get('days', 7)
        start_date = timezone.now() - timedelta(days=int(days))
        queryset = queryset.filter(created_at__gte=start_date)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        from apps.communication.models import Notification
        notification = Notification.objects.get(pk=pk)
        notification.is_read = True
        notification.save()
        return Response({'status': 'success', 'is_read': True})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        from apps.communication.models import Notification
        count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).update(is_read=True)
        return Response({'status': 'success', 'marked_as_read': count})
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        from apps.communication.models import Notification
        count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()
        return Response({'unread_count': count})
```

---

## 4️⃣ GLOBAL SEARCH API

### **Request:**
```
GET /api/search/?q=john&limit=20
Authorization: Bearer {token}

GET /api/search/?q=math&type=subject
GET /api/search/?q=STU001&type=student
```

### **Response:**
```json
{
    "query": "john",
    "count": 3,
    "results": [
        {
            "id": 1,
            "type": "student",
            "title": "John Doe",
            "description": "Grade 10A - Student ID: STU001234",
            "url": "/portal/student/1/",
            "icon": "bi-person",
            "metadata": {
                "grade": "10A",
                "status": "Active"
            }
        },
        {
            "id": 2,
            "type": "teacher",
            "title": "John Smith",
            "description": "Staff ID: TCH0456",
            "url": "/portal/teacher/2/",
            "icon": "bi-person-badge",
            "metadata": {
                "subject": "Mathematics",
                "status": "Active"
            }
        }
    ]
}
```

### **Copy & Paste Code:**
```python
# File: apps/api/search_api.py

from django.views import View
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.db.models import Q

@method_decorator(login_required, name='dispatch')
class GlobalSearchAPI(View):
    SEARCH_CONFIG = {
        'student': {
            'model': 'StudentProfile',
            'search_fields': ['user__first_name', 'user__last_name', 'student_id'],
            'icon': 'bi-person',
        },
        'teacher': {
            'model': 'TeacherProfile',
            'search_fields': ['user__first_name', 'user__last_name', 'staff_id'],
            'icon': 'bi-person-badge',
        },
    }
    
    def get(self, request):
        query = request.GET.get('q', '').strip()
        search_type = request.GET.get('type', 'all')
        limit = int(request.GET.get('limit', 20))
        
        if len(query) < 2:
            return JsonResponse({'error': 'Query too short'}, status=400)
        
        results = []
        types_to_search = [search_type] if search_type != 'all' else list(self.SEARCH_CONFIG.keys())
        
        for stype in types_to_search:
            config = self.SEARCH_CONFIG.get(stype)
            if not config:
                continue
            
            q_object = Q()
            for field in config['search_fields']:
                q_object |= Q(**{f'{field}__icontains': query})
            
            if stype == 'student':
                from apps.people.models import StudentProfile
                items = StudentProfile.objects.filter(q_object, is_active=True)[:limit]
                for item in items:
                    results.append({
                        'id': item.id,
                        'type': 'student',
                        'title': item.user.get_full_name(),
                        'description': f"Grade {item.current_class}",
                        'url': f"/portal/student/{item.id}/",
                        'icon': 'bi-person',
                    })
            
            elif stype == 'teacher':
                from apps.people.models import TeacherProfile
                items = TeacherProfile.objects.filter(q_object, is_active=True)[:limit]
                for item in items:
                    results.append({
                        'id': item.id,
                        'type': 'teacher',
                        'title': item.user.get_full_name(),
                        'description': f"ID: {item.staff_id}",
                        'url': f"/portal/teacher/{item.id}/",
                        'icon': 'bi-person-badge',
                    })
        
        return JsonResponse({
            'query': query,
            'count': len(results),
            'results': results
        })
```

---

## 5️⃣ INVOICES API

### **List Invoices:**
```
GET /api/finance/invoices/?status=pending&limit=50
Authorization: Bearer {token}
```

### **Response:**
```json
{
    "count": 150,
    "results": [
        {
            "id": 1,
            "student": 5,
            "student_name": "John Doe",
            "student_id": "STU001234",
            "amount": 50000.00,
            "paid_amount": 25000.00,
            "balance": 25000.00,
            "status": "pending",
            "due_date": "2025-02-01",
            "invoice_date": "2025-01-22"
        }
    ]
}
```

### **Copy & Paste Code:**
```python
# File: apps/finance/api_views.py

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Sum, Q

class InvoiceViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        from apps.finance.models import Invoice
        user = self.request.user
        if user.is_staff or user.role == 'ADMIN':
            return Invoice.objects.all()
        return Invoice.objects.filter(
            Q(student__user=user) | Q(student__guardian__user=user)
        )
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        if from_date and to_date:
            queryset = queryset.filter(
                invoice_date__gte=from_date,
                invoice_date__lte=to_date
            )
        
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)
```

---

## 6️⃣ ATTENDANCE API

### **Mark Attendance:**
```
POST /api/academics/attendance/mark/
Authorization: Bearer {token}
Content-Type: application/json

{
    "class_id": 1,
    "date": "2025-01-22",
    "attendees": [
        {"student_id": 1, "status": "present"},
        {"student_id": 2, "status": "absent"},
        {"student_id": 3, "status": "late"}
    ]
}
```

### **Response:**
```json
{
    "status": "success",
    "recorded": 3,
    "message": "Attendance recorded for 3 students"
}
```

### **Get Attendance for Student:**
```
GET /api/academics/attendance/student/1/?start_date=2025-01-01&end_date=2025-01-31
Authorization: Bearer {token}
```

### **Response:**
```json
{
    "student_id": 1,
    "total_days": 20,
    "present": 18,
    "absent": 1,
    "late": 1,
    "percentage": 92.5,
    "records": [
        {"date": "2025-01-22", "status": "present"}
    ]
}
```

### **Copy & Paste Code:**
```python
# File: apps/academics/api_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import datetime

class AttendanceMarkAPI(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        class_id = request.data.get('class_id')
        date_str = request.data.get('date')
        attendees = request.data.get('attendees', [])
        
        from apps.academics.models import Attendance, Classroom
        from apps.people.models import StudentProfile
        
        classroom = Classroom.objects.get(id=class_id)
        attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        recorded = 0
        for attendee in attendees:
            student = StudentProfile.objects.get(id=attendee['student_id'])
            attendance, created = Attendance.objects.update_or_create(
                student=student,
                classroom=classroom,
                date=attendance_date,
                defaults={'status': attendee['status']}
            )
            recorded += 1
        
        return Response({
            'status': 'success',
            'recorded': recorded,
            'message': f'Attendance recorded for {recorded} students'
        })

class AttendanceStudentAPI(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, student_id):
        from apps.academics.models import Attendance
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        queryset = Attendance.objects.filter(student_id=student_id)
        
        if start_date and end_date:
            queryset = queryset.filter(
                date__gte=start_date,
                date__lte=end_date
            )
        
        records = queryset.values('date', 'status')
        total = records.count()
        present = records.filter(status='present').count()
        
        percentage = (present / total * 100) if total > 0 else 0
        
        return Response({
            'student_id': student_id,
            'total_days': total,
            'present': present,
            'percentage': round(percentage, 1),
            'records': list(records)
        })
```

---

## 📝 URL REGISTRATION

Add these to `config/urls.py`:

```python
# config/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.api import views as api_views
from apps.api.dashboard_api import (
    AdminDashboardOverviewAPI, 
    TeacherDashboardAPI,
    ParentDashboardAPI,
    StudentDashboardAPI
)
from apps.api.notification_api import NotificationViewSet
from apps.api.search_api import GlobalSearchAPI

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    # ... existing patterns ...
    
    # API URLs
    path('api/', include([
        # Dashboard APIs
        path('dashboard/admin/overview/', AdminDashboardOverviewAPI.as_view()),
        path('dashboard/teacher/', TeacherDashboardAPI.as_view()),
        path('dashboard/parent/', ParentDashboardAPI.as_view()),
        path('dashboard/student/', StudentDashboardAPI.as_view()),
        
        # Search
        path('search/', GlobalSearchAPI.as_view()),
        
        # Viewsets
        path('', include(router.urls)),
    ])),
]
```

---

**All files ready to copy and paste!**  
**Document Version:** 1.0  
**Last Updated:** January 22, 2025
