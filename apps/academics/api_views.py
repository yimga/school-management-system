"""
Academics API Views
Attendance, Grades, Assessments, and Academic Analytics endpoints
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.db.models import Sum, Count, Q, F, Avg, Case, When, IntegerField
from django.utils import timezone
from datetime import datetime, timedelta

from apps.api.permissions import IsTeacherOrAdmin, IsTeacher, IsAdminUser
from apps.api.serializers import AttendanceSerializer
from apps.accounts.permissions import can_view_student_data, can_edit_student_grades


class AttendanceViewSet(viewsets.ModelViewSet):
    """
    Attendance management API
    
    Mark and retrieve attendance records
    Calculate attendance percentages
    Filter by class, date, student
    """
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['student', 'classroom', 'date', 'status']
    ordering_fields = ['date', 'student']
    ordering = ['-date']
    
    def get_queryset(self):
        from apps.academics.models import Attendance
        
        user = self.request.user
        role = (getattr(user, "role", "") or "").upper()
        admin_roles = {"ADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "CENSOR"}
        
        if user.is_staff or role in admin_roles:
            return Attendance.objects.all().select_related(
                'student__user', 'classroom'
            )

        if role == "TEACHER":
            from apps.evals.models import TeacherAssignment
            teacher = getattr(user, "teacher_profile", None)
            if not teacher:
                return Attendance.objects.none()
            classroom_ids = TeacherAssignment.objects.filter(
                teacher=teacher,
                is_active=True,
            ).values_list(
                'subject_assignment__classroom_id',
                flat=True
            ).distinct()
            return Attendance.objects.filter(
                classroom_id__in=classroom_ids
            ).select_related('student__user', 'classroom')
        
        from apps.people.models import StudentProfile
        
        student_profile = StudentProfile.objects.filter(user=user).first()
        if student_profile:
            return Attendance.objects.filter(
                student=student_profile
            ).select_related('student__user', 'classroom')

        if role == "PARENT":
            from apps.people.models import StudentGuardian
            child_ids = StudentGuardian.objects.filter(
                guardian_user=user,
                can_view_results=True,
            ).values_list('student_id', flat=True)
            return Attendance.objects.filter(
                student_id__in=child_ids
            ).select_related('student__user', 'classroom')
        
        return Attendance.objects.none()
    
    def list(self, request, *args, **kwargs):
        """
        List attendance records with advanced filtering
        
        Query Parameters:
        - classroom_id: specific classroom
        - date: specific date (YYYY-MM-DD)
        - start_date, end_date: date range
        - status: present, absent, late, excused
        - student_id: specific student
        """
        queryset = self.get_queryset()
        
        date_val = request.query_params.get('date')
        if date_val:
            queryset = queryset.filter(date=date_val)
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(
                date__gte=start_date,
                date__lte=end_date
            )
        
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        """
        Record attendance for a class
        
        Request Body:
        {
            "classroom": 1,
            "date": "2025-01-22",
            "records": [
                {"student": 1, "status": "present"},
                {"student": 2, "status": "absent"},
                {"student": 3, "status": "late"}
            ]
        }
        """
        user_role = (getattr(request.user, "role", "") or "").upper()
        if not (user_role == 'TEACHER' or request.user.is_staff):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from apps.academics.models import Attendance, Classroom
        
        classroom_id = request.data.get('classroom')
        date_str = request.data.get('date')
        records = request.data.get('records', [])
        
        try:
            classroom = Classroom.objects.get(id=classroom_id)
            attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Classroom.DoesNotExist:
            return Response(
                {'error': 'Classroom not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if user_role == "TEACHER":
            from apps.evals.models import TeacherAssignment
            teacher = getattr(request.user, "teacher_profile", None)
            if not teacher:
                return Response(
                    {'error': 'Teacher profile required'},
                    status=status.HTTP_403_FORBIDDEN
                )
            classroom_allowed = TeacherAssignment.objects.filter(
                teacher=teacher,
                is_active=True,
                subject_assignment__classroom_id=classroom.id,
            ).exists()
            if not classroom_allowed:
                return Response(
                    {'error': 'You are not assigned to this classroom'},
                    status=status.HTTP_403_FORBIDDEN
                )

        student_ids = [record.get('student') for record in records if record.get('student')]
        if student_ids:
            from apps.people.models import StudentProfile
            valid_ids = set(StudentProfile.objects.filter(
                id__in=student_ids,
                classroom_id=classroom.id,
            ).values_list('id', flat=True))
            if len(valid_ids) != len(set(student_ids)):
                return Response(
                    {'error': 'One or more students are not in this classroom'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        recorded_count = 0
        for record in records:
            attendance, created = Attendance.objects.update_or_create(
                student_id=record['student'],
                classroom=classroom,
                date=attendance_date,
                defaults={'status': record['status']}
            )
            recorded_count += 1
        
        return Response({
            'status': 'success',
            'recorded': recorded_count,
            'classroom_id': classroom_id,
            'date': date_str,
            'message': f'Attendance recorded for {recorded_count} students'
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'])
    def student_summary(self, request):
        """
        Get attendance summary for a student
        
        Query Parameters:
        - student_id: required
        - start_date, end_date: optional date range
        
        Returns:
        {
            "student_id": 1,
            "total_days": 20,
            "present": 18,
            "absent": 1,
            "late": 1,
            "percentage": 92.5
        }
        """
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response(
                {'error': 'student_id parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not can_view_student_data(request.user, int(student_id)):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from apps.academics.models import Attendance
        
        queryset = Attendance.objects.filter(student_id=student_id)
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if start_date and end_date:
            queryset = queryset.filter(
                date__gte=start_date,
                date__lte=end_date
            )
        
        total = queryset.count()
        present = queryset.filter(status='present').count()
        absent = queryset.filter(status='absent').count()
        late = queryset.filter(status='late').count()
        
        percentage = (present / total * 100) if total > 0 else 0
        
        return Response({
            'student_id': int(student_id),
            'total_days': total,
            'present': present,
            'absent': absent,
            'late': late,
            'percentage': round(percentage, 1),
            'period': {
                'start': start_date,
                'end': end_date
            }
        })
    
    @action(detail=False, methods=['get'])
    def class_summary(self, request):
        """Get attendance summary for entire class"""
        classroom_id = request.query_params.get('classroom_id')
        if not classroom_id:
            return Response(
                {'error': 'classroom_id parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user_role = (getattr(request.user, "role", "") or "").upper()
        if not (request.user.is_staff or user_role in {'ADMIN', 'LEADERSHIP', 'PRINCIPAL', 'VICE_PRINCIPAL', 'DEAN', 'CENSOR', 'TEACHER'}):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        if user_role == "TEACHER" and not request.user.is_staff:
            from apps.evals.models import TeacherAssignment
            teacher = getattr(request.user, "teacher_profile", None)
            if not teacher:
                return Response(
                    {'error': 'Teacher profile required'},
                    status=status.HTTP_403_FORBIDDEN
                )
            allowed = TeacherAssignment.objects.filter(
                teacher=teacher,
                is_active=True,
                subject_assignment__classroom_id=classroom_id,
            ).exists()
            if not allowed:
                return Response(
                    {'error': 'You are not assigned to this classroom'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        from apps.academics.models import Attendance
        
        queryset = Attendance.objects.filter(classroom_id=classroom_id)
        
        date_val = request.query_params.get('date')
        if date_val:
            queryset = queryset.filter(date=date_val)
        
        total = queryset.count()
        present = queryset.filter(status='present').count()
        absent = queryset.filter(status='absent').count()
        late = queryset.filter(status='late').count()
        
        percentage = (present / total * 100) if total > 0 else 0
        
        by_student = queryset.values('student__user__first_name', 'student__user__last_name').annotate(
            total_days=Count('id'),
            present_days=Count('id', filter=Q(status='present'))
        ).order_by('student__user__last_name')
        
        return Response({
            'classroom_id': int(classroom_id),
            'total_records': total,
            'present': present,
            'absent': absent,
            'late': late,
            'class_percentage': round(percentage, 1),
            'date': date_val,
            'by_student': list(by_student)
        })


class GradeViewSet(viewsets.ModelViewSet):
    """
    Grade/Assessment recording API
    
    Record and retrieve student grades
    Calculate class averages and statistics
    """
    permission_classes = [IsAuthenticated]
    filterset_fields = ['student', 'subject', 'assessment_type', 'term']
    ordering_fields = ['date_recorded', 'score']
    ordering = ['-date_recorded']
    
    def get_queryset(self):
        from apps.evals.models import Grade
        
        user = self.request.user
        role = (getattr(user, "role", "") or "").upper()
        admin_roles = {"ADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "CENSOR"}
        
        if user.is_staff or role in admin_roles:
            return Grade.objects.all().select_related('student__user', 'subject')

        if role == "TEACHER":
            from apps.evals.models import TeacherAssignment
            teacher = getattr(user, "teacher_profile", None)
            if not teacher:
                return Grade.objects.none()
            assignments = list(TeacherAssignment.objects.filter(
                teacher=teacher,
                is_active=True,
            ).values_list(
                'subject_assignment__classroom_id',
                'subject_assignment__subject_id',
            ).distinct())
            if not assignments:
                return Grade.objects.none()
            scope = Q()
            for classroom_id, subject_id in assignments:
                scope |= Q(student__classroom_id=classroom_id, subject_id=subject_id)
            return Grade.objects.filter(scope).select_related('student__user', 'subject')
        
        from apps.people.models import StudentProfile
        
        student_profile = StudentProfile.objects.filter(user=user).first()
        if student_profile:
            return Grade.objects.filter(
                student=student_profile
            ).select_related('student__user', 'subject')

        if role == "PARENT":
            from apps.people.models import StudentGuardian
            child_ids = StudentGuardian.objects.filter(
                guardian_user=user,
                can_view_results=True,
            ).values_list('student_id', flat=True)
            return Grade.objects.filter(
                student_id__in=child_ids
            ).select_related('student__user', 'subject')
        
        return Grade.objects.none()
    
    def create(self, request, *args, **kwargs):
        """
        Record a grade for a student
        
        Request Body:
        {
            "student": 1,
            "subject": 1,
            "assessment_type": "exam",
            "score": 85.5,
            "max_score": 100,
            "term": 1,
            "date_recorded": "2025-01-22"
        }
        """
        user_role = (getattr(request.user, "role", "") or "").upper()
        if not (user_role == 'TEACHER' or request.user.is_staff):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from apps.evals.models import Grade
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if user_role == "TEACHER" and not request.user.is_staff:
            student_obj = serializer.validated_data.get("student")
            subject_obj = serializer.validated_data.get("subject")
            if not student_obj or not subject_obj:
                return Response(
                    {'error': 'Student and subject are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not can_edit_student_grades(request.user, student_obj.id, subject_obj.id):
                return Response(
                    {'error': 'You are not assigned to this student/subject'},
                    status=status.HTTP_403_FORBIDDEN
                )

        grade = serializer.save(recorded_by=request.user)
        
        from apps.finance.models import Notification
        Notification.objects.create(
            title="Grade Published",
            message=f"Your grade for {grade.subject.name} has been published: {grade.score}",
            recipient=request.user,
            created_by=request.user,
        )
        
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )
    
    @action(detail=False, methods=['get'])
    def student_transcript(self, request):
        """Get complete transcript for a student"""
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response(
                {'error': 'student_id parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not can_view_student_data(request.user, int(student_id)):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from apps.evals.models import Grade
        
        grades = Grade.objects.filter(student_id=student_id).select_related(
            'subject'
        ).values('subject__name').annotate(
            average=Avg('score'),
            count=Count('id')
        )
        
        all_grades = Grade.objects.filter(student_id=student_id)
        overall_average = all_grades.aggregate(Avg('score'))['score__avg'] or 0
        
        return Response({
            'student_id': int(student_id),
            'overall_average': round(float(overall_average), 1),
            'total_assessments': all_grades.count(),
            'by_subject': list(grades)
        })
    
    @action(detail=False, methods=['get'])
    def class_performance(self, request):
        """Get performance statistics for a class"""
        classroom_id = request.query_params.get('classroom_id')
        if not classroom_id:
            return Response(
                {'error': 'classroom_id parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user_role = (getattr(request.user, "role", "") or "").upper()
        if not (request.user.is_staff or user_role in {'ADMIN', 'LEADERSHIP', 'PRINCIPAL', 'VICE_PRINCIPAL', 'DEAN', 'CENSOR', 'TEACHER'}):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        if user_role == "TEACHER" and not request.user.is_staff:
            from apps.evals.models import TeacherAssignment
            teacher = getattr(request.user, "teacher_profile", None)
            if not teacher:
                return Response(
                    {'error': 'Teacher profile required'},
                    status=status.HTTP_403_FORBIDDEN
                )
            allowed = TeacherAssignment.objects.filter(
                teacher=teacher,
                is_active=True,
                subject_assignment__classroom_id=classroom_id,
            ).exists()
            if not allowed:
                return Response(
                    {'error': 'You are not assigned to this classroom'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        from apps.evals.models import Grade
        from apps.academics.models import Classroom
        
        try:
            classroom = Classroom.objects.get(id=classroom_id)
        except Classroom.DoesNotExist:
            return Response(
                {'error': 'Classroom not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        students_in_class = classroom.student_set.all().values_list('id', flat=True)
        
        grades = Grade.objects.filter(student_id__in=students_in_class)
        
        class_average = grades.aggregate(Avg('score'))['score__avg'] or 0
        
        top_performers = grades.values('student__user__first_name', 'student__user__last_name').annotate(
            average=Avg('score')
        ).order_by('-average')[:5]
        
        struggling_students = grades.values('student__user__first_name', 'student__user__last_name').annotate(
            average=Avg('score')
        ).filter(average__lt=50).order_by('average')[:5]
        
        return Response({
            'classroom_id': int(classroom_id),
            'classroom_name': classroom.name,
            'class_average': round(float(class_average), 1),
            'total_students': len(students_in_class),
            'total_assessments': grades.count(),
            'top_performers': list(top_performers),
            'struggling_students': list(struggling_students)
        })


class AssessmentResultsAPI(APIView):
    """
    Assessment results and analytics
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get assessment results summary"""
        from apps.evals.models import Grade
        from apps.evals.models import TeacherAssignment

        user = request.user
        role = (getattr(user, "role", "") or "").upper()
        admin_roles = {"ADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "CENSOR"}
        
        subject_id = request.query_params.get('subject_id')
        term = request.query_params.get('term')

        if user.is_staff or role in admin_roles:
            queryset = Grade.objects.all()
        elif role == "TEACHER":
            teacher = getattr(user, "teacher_profile", None)
            if not teacher:
                return Response({'error': 'Teacher profile required'}, status=status.HTTP_403_FORBIDDEN)
            assignments = list(TeacherAssignment.objects.filter(
                teacher=teacher,
                is_active=True,
            ).values_list(
                'subject_assignment__classroom_id',
                'subject_assignment__subject_id',
            ).distinct())
            if not assignments:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            scope = Q()
            for classroom_id, subject_id_scope in assignments:
                scope |= Q(student__classroom_id=classroom_id, subject_id=subject_id_scope)
            queryset = Grade.objects.filter(scope)
        else:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        
        if term:
            queryset = queryset.filter(term=term)
        
        average_score = queryset.aggregate(Avg('score'))['score__avg'] or 0
        
        # DB-agnostic score buckets (Case/When works on SQLite and PostgreSQL)
        agg = queryset.aggregate(
            r1=Count(Case(When(score__lt=50, then=1), output_field=IntegerField())),
            r2=Count(Case(When(score__gte=50, score__lt=70, then=1), output_field=IntegerField())),
            r3=Count(Case(When(score__gte=70, score__lt=85, then=1), output_field=IntegerField())),
            r4=Count(Case(When(score__gte=85, then=1), output_field=IntegerField())),
        )
        score_distribution = [
            {"range": "0-50", "count": agg["r1"] or 0},
            {"range": "50-70", "count": agg["r2"] or 0},
            {"range": "70-85", "count": agg["r3"] or 0},
            {"range": "85-100", "count": agg["r4"] or 0},
        ]
        
        by_subject = queryset.values('subject__name').annotate(
            average=Avg('score'),
            count=Count('id')
        ).order_by('-average')
        
        return Response({
            'total_assessments': queryset.count(),
            'average_score': round(float(average_score), 1),
            'score_distribution': list(score_distribution),
            'by_subject': list(by_subject),
            'filters': {
                'subject_id': subject_id,
                'term': term
            }
        })
