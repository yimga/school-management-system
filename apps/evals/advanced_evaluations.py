"""
Phase 8 Task 4: Advanced Evaluations - Ranking and Mock Exams
Implements class ranking engine, mock exam management, and performance analysis
"""

from django.db import models
from django.utils import timezone
from django.db.models import Avg, Count, Q, F
import statistics


class RankingEngine:
    """Class ranking calculation engine"""
    
    @staticmethod
    def calculate_class_rankings(classroom, subject=None):
        """Calculate student rankings for classroom"""
        from apps.evals.models import Evaluation
        from apps.people.models import StudentProfile
        
        # Get all students in classroom
        students = StudentProfile.objects.filter(
            classroom=classroom
        ).select_related('student')
        
        rankings = []
        
        for student in students:
            evals = Evaluation.objects.filter(
                student=student.student,
                classroom=classroom
            )
            
            if subject:
                evals = evals.filter(subject=subject)
            
            if not evals.exists():
                continue
            
            avg_score = evals.aggregate(Avg('score'))['score__avg']
            
            rankings.append({
                'student': student,
                'average_score': round(avg_score, 2),
                'total_evals': evals.count(),
                'grade_dist': RankingEngine._get_grade_distribution(evals),
                'percentile': None  # To be calculated after sorting
            })
        
        # Sort by average score (descending)
        rankings.sort(key=lambda x: x['average_score'], reverse=True)
        
        # Calculate percentiles and ranks
        total = len(rankings)
        for idx, ranking in enumerate(rankings, 1):
            ranking['rank'] = idx
            ranking['percentile'] = round((1 - (idx - 1) / total) * 100, 2)
        
        return rankings
    
    @staticmethod
    def _get_grade_distribution(evaluations):
        """Get grade distribution"""
        dist = {
            'A': evaluations.filter(score__gte=80).count(),
            'B': evaluations.filter(score__gte=70, score__lt=80).count(),
            'C': evaluations.filter(score__gte=60, score__lt=70).count(),
            'D': evaluations.filter(score__gte=50, score__lt=60).count(),
            'F': evaluations.filter(score__lt=50).count(),
        }
        return dist
    
    @staticmethod
    def get_top_performers(classroom, count=10):
        """Get top performing students"""
        rankings = RankingEngine.calculate_class_rankings(classroom)
        return rankings[:count]
    
    @staticmethod
    def get_struggling_students(classroom, threshold=50):
        """Get students below threshold"""
        rankings = RankingEngine.calculate_class_rankings(classroom)
        return [r for r in rankings if r['average_score'] < threshold]


class MockExamManager:
    """Mock exam management"""
    
    @staticmethod
    def create_mock_exam_series(classroom, subject, num_exams=3):
        """Create series of mock exams"""
        exams = []
        for i in range(num_exams):
            exam_name = f"Mock Exam {i+1} - {subject.name}"
            exam = {
                'name': exam_name,
                'sequence': i + 1,
                'subject': subject,
                'classroom': classroom,
                'created_at': timezone.now(),
            }
            exams.append(exam)
        return exams
    
    @staticmethod
    def analyze_mock_exam_performance(classroom, exam_sequence):
        """Analyze performance on specific mock exam"""
        from apps.evals.models import Evaluation
        
        exams = Evaluation.objects.filter(
            classroom=classroom,
            exam_sequence=exam_sequence
        )
        
        if not exams.exists():
            return None
        
        scores = [e.score for e in exams]
        
        return {
            'total_students': len(scores),
            'average': round(statistics.mean(scores), 2),
            'median': statistics.median(scores),
            'std_dev': round(statistics.stdev(scores), 2) if len(scores) > 1 else 0,
            'pass_rate': round(len([s for s in scores if s >= 40]) / len(scores) * 100, 2),
            'min_score': min(scores),
            'max_score': max(scores),
        }


class NotificationService:
    """Performance notifications"""
    
    @staticmethod
    def generate_grade_notifications(student):
        """Generate notifications for student grades"""
        from apps.evals.models import Evaluation
        
        notifications = []
        
        # Get recent grades
        recent = Evaluation.objects.filter(
            student=student,
            created_at__gte=timezone.now() - __import__('datetime').timedelta(days=7)
        ).order_by('-created_at')
        
        if recent.exists():
            latest = recent.first()
            
            # High grade notification
            if latest.score >= 80:
                notifications.append({
                    'type': 'HIGH_GRADE',
                    'message': f'Excellent! You scored {latest.score}% in {latest.subject.name}',
                    'recipient': student,
                })
            
            # Low grade notification
            elif latest.score < 50:
                notifications.append({
                    'type': 'LOW_GRADE',
                    'message': f'You scored {latest.score}% in {latest.subject.name}. Please seek help.',
                    'recipient': student,
                })
        
        return notifications
    
    @staticmethod
    def generate_parent_notifications(student):
        """Generate notifications for parents"""
        from apps.evals.models import Evaluation
        
        notifications = []
        
        # Get recent grades summary
        recent = Evaluation.objects.filter(
            student=student,
            created_at__gte=timezone.now() - __import__('datetime').timedelta(days=30)
        )
        
        if recent.exists():
            avg = recent.aggregate(
                avg=__import__('django.db.models').Avg('score')
            )['avg']
            
            if avg < 50:
                notifications.append({
                    'type': 'PARENT_ALERT',
                    'message': f'{student.get_full_name()} needs academic support',
                    'recipient': student.studentprofile.student,
                })
        
        return notifications


class OfflineSyncManager:
    """Offline synchronization for evaluations"""
    
    @staticmethod
    def prepare_sync_package(classroom):
        """Prepare data for offline sync"""
        from apps.evals.models import Evaluation
        
        data = {
            'classroom': classroom.id,
            'timestamp': timezone.now().isoformat(),
            'students': [],
            'evaluations': []
        }
        
        # Export evaluations
        evals = Evaluation.objects.filter(classroom=classroom)
        for eval in evals:
            data['evaluations'].append({
                'id': eval.id,
                'student_id': eval.student_id,
                'subject_id': eval.subject_id,
                'score': eval.score,
            })
        
        return data
    
    @staticmethod
    def sync_offline_changes(sync_data):
        """Merge offline changes back"""
        from apps.evals.models import Evaluation
        
        conflicts = []
        merged = 0
        
        for eval_data in sync_data.get('evaluations', []):
            try:
                eval = Evaluation.objects.get(id=eval_data['id'])
                
                # Check for conflicts
                if eval.updated_at > sync_data['timestamp']:
                    conflicts.append(eval_data)
                else:
                    eval.score = eval_data['score']
                    eval.save()
                    merged += 1
            except Evaluation.DoesNotExist:
                pass
        
        return {
            'merged': merged,
            'conflicts': conflicts,
        }


class ImportEnhancedService:
    """Enhanced grade import with validation"""
    
    @staticmethod
    def validate_import_data(import_data):
        """Validate imported grade data"""
        errors = []
        
        for idx, row in enumerate(import_data, 1):
            # Validate student exists
            if 'student_id' not in row:
                errors.append(f"Row {idx}: Missing student_id")
                continue
            
            # Validate score range
            if 'score' not in row or not (0 <= float(row['score']) <= 100):
                errors.append(f"Row {idx}: Invalid score {row.get('score')}")
            
            # Validate subject exists
            if 'subject_id' not in row:
                errors.append(f"Row {idx}: Missing subject_id")
        
        return errors
    
    @staticmethod
    def import_grades_with_conflict_resolution(import_data):
        """Import grades with conflict handling"""
        from apps.evals.models import Evaluation
        
        results = {
            'imported': 0,
            'skipped': 0,
            'updated': 0,
            'conflicts': []
        }
        
        for row in import_data:
            try:
                eval, created = Evaluation.objects.get_or_create(
                    student_id=row['student_id'],
                    subject_id=row['subject_id'],
                    assignment_id=row.get('assignment_id'),
                    defaults={'score': row['score']}
                )
                
                if created:
                    results['imported'] += 1
                else:
                    # Check if newer version exists
                    if hasattr(eval, 'updated_at'):
                        results['conflicts'].append(row)
                    else:
                        eval.score = row['score']
                        eval.save()
                        results['updated'] += 1
            except Exception as e:
                results['skipped'] += 1
        
        return results
