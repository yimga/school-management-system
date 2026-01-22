"""
Phase 9 Task 3: ML-Based Predictions
Fee default likelihood, performance forecasting, churn risk prediction

INTEGRATION: Extends apps.analytics.services.AdvancedAnalyticsService
Uses existing PerformanceMetrics model for training data
"""

from django.db import models
from django.utils import timezone
from datetime import timedelta
import numpy as np
from typing import Dict, List, Tuple
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
import joblib
import os


class FeeDefaultPredictor:
    """
    Predict likelihood of fee payment default
    
    INTEGRATES WITH: apps.finance.models (Invoice, Payment)
    FEATURES: Payment history, outstanding balance, payment patterns
    """
    
    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.is_trained = False
    
    @staticmethod
    def extract_features(student) -> np.ndarray:
        """
        Extract features for fee default prediction
        
        Features:
        - Total outstanding balance
        - Number of late payments
        - Average days late
        - Payment consistency score
        - Months since last payment
        """
        from apps.finance.models import Invoice, Payment
        
        invoices = Invoice.objects.filter(student=student)
        payments = Payment.objects.filter(invoice__student=student)
        
        total_outstanding = invoices.filter(status='PENDING').aggregate(
            total=models.Sum('amount')
        )['total'] or 0
        
        late_payments = payments.filter(
            status='COMPLETED',
            paid_at__gt=models.F('invoice__due_date')
        ).count()
        
        # Average days late for completed payments
        late_payment_days = []
        for payment in payments.filter(status='COMPLETED'):
            if payment.paid_at and payment.invoice.due_date:
                days_late = (payment.paid_at.date() - payment.invoice.due_date).days
                if days_late > 0:
                    late_payment_days.append(days_late)
        
        avg_days_late = np.mean(late_payment_days) if late_payment_days else 0
        
        # Payment consistency (% of invoices paid on time)
        total_invoices = invoices.count()
        on_time_payments = payments.filter(
            status='COMPLETED',
            paid_at__lte=models.F('invoice__due_date')
        ).count()
        consistency_score = (on_time_payments / total_invoices) if total_invoices > 0 else 1.0
        
        # Months since last payment
        last_payment = payments.filter(status='COMPLETED').order_by('-paid_at').first()
        months_since_payment = 0
        if last_payment and last_payment.paid_at:
            months_since_payment = (timezone.now() - last_payment.paid_at).days / 30
        
        return np.array([
            float(total_outstanding),
            float(late_payments),
            float(avg_days_late),
            float(consistency_score),
            float(months_since_payment),
        ])
    
    def train(self, training_data: List[Tuple]):
        """
        Train the model on historical data
        
        Args:
            training_data: List of (student, defaulted_flag) tuples
        """
        X = []
        y = []
        
        for student, defaulted in training_data:
            features = self.extract_features(student)
            X.append(features)
            y.append(1 if defaulted else 0)
        
        X = np.array(X)
        y = np.array(y)
        
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        self.is_trained = True
    
    def predict_default_probability(self, student) -> float:
        """
        Predict probability of fee default for a student
        
        Returns:
            Float between 0 and 1 (0 = low risk, 1 = high risk)
        """
        if not self.is_trained:
            return 0.0
        
        features = self.extract_features(student).reshape(1, -1)
        features_scaled = self.scaler.transform(features)
        probability = self.model.predict_proba(features_scaled)[0][1]
        
        return float(probability)
    
    def get_risk_category(self, probability: float) -> str:
        """Categorize risk level"""
        if probability < 0.3:
            return 'LOW'
        elif probability < 0.6:
            return 'MEDIUM'
        elif probability < 0.8:
            return 'HIGH'
        else:
            return 'CRITICAL'


class PerformanceForecaster:
    """
    Forecast student academic performance for next term
    
    INTEGRATES WITH: apps.analytics.services.AdvancedAnalyticsService
    Uses existing get_performance_trends() for historical data
    """
    
    def __init__(self):
        self.model = GradientBoostingRegressor(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.is_trained = False
    
    @staticmethod
    def extract_features(student) -> np.ndarray:
        """
        Extract features for performance forecasting
        
        LEVERAGES: AdvancedAnalyticsService.get_performance_trends()
        
        Features:
        - Last 3 term averages
        - Trend slope (improving/declining)
        - Attendance rate
        - Number of subjects
        - At-risk status
        """
        from apps.analytics.services import AdvancedAnalyticsService
        from apps.evals.models import Evaluation
        from apps.academics.models import StudentProfile
        
        # Get performance trends using existing service
        trends = AdvancedAnalyticsService.get_performance_trends(student, days=270)  # ~3 terms
        
        # Extract last 3 term averages
        evaluations = Evaluation.objects.filter(
            student=student
        ).order_by('-term__start_date')[:3]
        
        term_averages = [eval.final_score for eval in evaluations]
        while len(term_averages) < 3:
            term_averages.append(0.0)
        
        # Calculate trend slope
        if len(term_averages) >= 2:
            trend_slope = term_averages[0] - term_averages[-1]
        else:
            trend_slope = 0.0
        
        # Attendance rate (from attendance app)
        try:
            profile = StudentProfile.objects.get(user=student)
            attendance_rate = profile.attendance_rate if hasattr(profile, 'attendance_rate') else 90.0
        except StudentProfile.DoesNotExist:
            attendance_rate = 90.0
        
        # Number of subjects enrolled
        subject_count = evaluations.values('subject').distinct().count()
        
        # At-risk status (use existing service)
        at_risk_students = AdvancedAnalyticsService.identify_at_risk_students(threshold=50)
        is_at_risk = 1.0 if student in at_risk_students else 0.0
        
        return np.array([
            float(term_averages[0]),
            float(term_averages[1]),
            float(term_averages[2]),
            float(trend_slope),
            float(attendance_rate),
            float(subject_count),
            float(is_at_risk),
        ])
    
    def train(self, training_data: List[Tuple]):
        """
        Train the model on historical data
        
        Args:
            training_data: List of (student, next_term_average) tuples
        """
        X = []
        y = []
        
        for student, actual_score in training_data:
            features = self.extract_features(student)
            X.append(features)
            y.append(actual_score)
        
        X = np.array(X)
        y = np.array(y)
        
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        self.is_trained = True
    
    def forecast_performance(self, student) -> Dict:
        """
        Forecast next term performance
        
        Returns:
            Dict with predicted_score, confidence_interval, trend
        """
        if not self.is_trained:
            return {
                'predicted_score': 0.0,
                'confidence_low': 0.0,
                'confidence_high': 0.0,
                'trend': 'UNKNOWN',
            }
        
        features = self.extract_features(student).reshape(1, -1)
        features_scaled = self.scaler.transform(features)
        predicted_score = self.model.predict(features_scaled)[0]
        
        # Simple confidence interval (±10%)
        confidence_low = max(0, predicted_score - 10)
        confidence_high = min(100, predicted_score + 10)
        
        # Determine trend
        trend_slope = features[0, 3]  # Feature 3 is trend_slope
        if trend_slope > 5:
            trend = 'IMPROVING'
        elif trend_slope < -5:
            trend = 'DECLINING'
        else:
            trend = 'STABLE'
        
        return {
            'predicted_score': float(predicted_score),
            'confidence_low': float(confidence_low),
            'confidence_high': float(confidence_high),
            'trend': trend,
        }


class ChurnRiskPredictor:
    """
    Predict student churn/dropout risk
    
    INTEGRATES WITH: apps.people.models (StudentProfile)
    Uses attendance, performance, engagement metrics
    """
    
    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.is_trained = False
    
    @staticmethod
    def extract_features(student) -> np.ndarray:
        """
        Extract features for churn prediction
        
        Features:
        - Attendance rate (last 30 days)
        - Performance trend
        - Days since last login (portal engagement)
        - Number of disciplinary incidents
        - Fee payment status
        """
        from apps.analytics.models import AttendanceLog
        from apps.evals.models import Evaluation
        from apps.finance.models import Invoice
        
        # Attendance rate (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        attendance_logs = AttendanceLog.objects.filter(
            student=student,
            date__gte=thirty_days_ago
        )
        present_count = attendance_logs.filter(status='present').count()
        total_logs = attendance_logs.count()
        attendance_rate = (present_count / total_logs * 100) if total_logs > 0 else 100.0
        
        # Performance trend
        recent_evals = Evaluation.objects.filter(
            student=student
        ).order_by('-created_at')[:5]
        
        if recent_evals.count() >= 2:
            avg_recent = sum([e.final_score for e in recent_evals]) / recent_evals.count()
            performance_trend = avg_recent
        else:
            performance_trend = 50.0
        
        # Days since last login (portal engagement)
        try:
            last_login = student.last_login
            days_since_login = (timezone.now() - last_login).days if last_login else 999
        except:
            days_since_login = 999
        
        # Disciplinary incidents (if compliance app has this)
        disciplinary_count = 0  # Placeholder
        
        # Fee payment status
        outstanding_invoices = Invoice.objects.filter(
            student=student,
            status='PENDING'
        ).count()
        
        return np.array([
            float(attendance_rate),
            float(performance_trend),
            float(days_since_login),
            float(disciplinary_count),
            float(outstanding_invoices),
        ])
    
    def train(self, training_data: List[Tuple]):
        """
        Train the model on historical data
        
        Args:
            training_data: List of (student, churned_flag) tuples
        """
        X = []
        y = []
        
        for student, churned in training_data:
            features = self.extract_features(student)
            X.append(features)
            y.append(1 if churned else 0)
        
        X = np.array(X)
        y = np.array(y)
        
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        self.is_trained = True
    
    def predict_churn_probability(self, student) -> float:
        """
        Predict probability of student dropout
        
        Returns:
            Float between 0 and 1 (0 = low risk, 1 = high risk)
        """
        if not self.is_trained:
            return 0.0
        
        features = self.extract_features(student).reshape(1, -1)
        features_scaled = self.scaler.transform(features)
        probability = self.model.predict_proba(features_scaled)[0][1]
        
        return float(probability)
    
    def get_risk_factors(self, student) -> List[str]:
        """Identify key risk factors for this student"""
        features = self.extract_features(student)
        
        risk_factors = []
        
        if features[0] < 70:  # Attendance rate
            risk_factors.append('Low attendance')
        if features[1] < 50:  # Performance
            risk_factors.append('Poor academic performance')
        if features[2] > 14:  # Days since login
            risk_factors.append('Low portal engagement')
        if features[4] > 2:  # Outstanding invoices
            risk_factors.append('Fee payment issues')
        
        return risk_factors


class MLPredictionService:
    """
    Service for managing ML predictions
    
    INTEGRATES WITH:
    - apps.analytics.services.AdvancedAnalyticsService
    - apps.analytics.models.PerformanceMetrics
    - apps.finance.models (Invoice, Payment)
    """
    
    def __init__(self):
        self.fee_predictor = FeeDefaultPredictor()
        self.performance_forecaster = PerformanceForecaster()
        self.churn_predictor = ChurnRiskPredictor()
    
    def generate_student_risk_report(self, student) -> Dict:
        """
        Comprehensive risk assessment for a student
        
        Combines fee default, performance forecast, and churn risk
        """
        report = {
            'student_id': student.id,
            'generated_at': timezone.now().isoformat(),
            'fee_default': {
                'probability': self.fee_predictor.predict_default_probability(student),
                'risk_category': '',
            },
            'performance': self.performance_forecaster.forecast_performance(student),
            'churn': {
                'probability': self.churn_predictor.predict_churn_probability(student),
                'risk_factors': self.churn_predictor.get_risk_factors(student),
            },
        }
        
        report['fee_default']['risk_category'] = self.fee_predictor.get_risk_category(
            report['fee_default']['probability']
        )
        
        return report
    
    def get_high_risk_students(self, threshold: float = 0.7) -> List:
        """
        Identify students with high risk across any category
        
        LEVERAGES: AdvancedAnalyticsService.identify_at_risk_students()
        """
        from apps.people.models import Student
        from apps.analytics.services import AdvancedAnalyticsService
        
        # Start with existing at-risk detection
        at_risk_base = AdvancedAnalyticsService.identify_at_risk_students(threshold=50)
        
        high_risk = []
        
        for student in Student.objects.filter(is_active=True):
            report = self.generate_student_risk_report(student)
            
            if (report['fee_default']['probability'] > threshold or
                report['churn']['probability'] > threshold or
                report['performance']['predicted_score'] < 40):
                
                high_risk.append({
                    'student': student,
                    'report': report,
                })
        
        return high_risk
