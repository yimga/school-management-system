"""
Phase 9 Task 3: ML Predictions - Tests
Fee default, performance forecasting, churn risk prediction tests
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import numpy as np

from apps.analytics.ml_predictions import (
    FeeDefaultPredictor,
    PerformanceForecaster,
    ChurnRiskPredictor,
    MLPredictionService,
)

User = get_user_model()


class FeeDefaultPredictorTestCase(TestCase):
    """Test fee default prediction"""
    
    def setUp(self):
        self.student = User.objects.create_user(
            username='testfee',
            email='testfee@example.com',
            password='password123'
        )
        self.predictor = FeeDefaultPredictor()
    
    def test_extract_features(self):
        """Test feature extraction"""
        features = self.predictor.extract_features(self.student)
        
        self.assertEqual(len(features), 5)
        self.assertIsInstance(features, np.ndarray)
        
        # Features: outstanding, late_payments, avg_days_late, consistency, months_since
        self.assertGreaterEqual(features[0], 0)  # Outstanding balance
        self.assertGreaterEqual(features[1], 0)  # Late payments
    
    def test_train_model(self):
        """Test model training"""
        training_data = [
            (self.student, False),  # Not defaulted
        ]
        
        self.predictor.train(training_data)
        self.assertTrue(self.predictor.is_trained)
    
    def test_predict_default_probability(self):
        """Test default probability prediction"""
        # Train with dummy data
        training_data = [(self.student, False)]
        self.predictor.train(training_data)
        
        probability = self.predictor.predict_default_probability(self.student)
        
        self.assertIsInstance(probability, float)
        self.assertGreaterEqual(probability, 0.0)
        self.assertLessEqual(probability, 1.0)
    
    def test_get_risk_category(self):
        """Test risk categorization"""
        self.assertEqual(self.predictor.get_risk_category(0.2), 'LOW')
        self.assertEqual(self.predictor.get_risk_category(0.5), 'MEDIUM')
        self.assertEqual(self.predictor.get_risk_category(0.7), 'HIGH')
        self.assertEqual(self.predictor.get_risk_category(0.9), 'CRITICAL')


class PerformanceForecasterTestCase(TestCase):
    """Test performance forecasting"""
    
    def setUp(self):
        self.student = User.objects.create_user(
            username='testperf',
            email='testperf@example.com',
            password='password123'
        )
        self.forecaster = PerformanceForecaster()
    
    def test_extract_features(self):
        """Test feature extraction for performance"""
        features = self.forecaster.extract_features(self.student)
        
        self.assertEqual(len(features), 7)
        self.assertIsInstance(features, np.ndarray)
        
        # Features: term_avg1, term_avg2, term_avg3, trend_slope, attendance, subjects, at_risk
        for i in range(7):
            self.assertGreaterEqual(features[i], 0.0)
    
    def test_train_model(self):
        """Test model training"""
        training_data = [
            (self.student, 75.0),  # Next term average
        ]
        
        self.forecaster.train(training_data)
        self.assertTrue(self.forecaster.is_trained)
    
    def test_forecast_performance(self):
        """Test performance forecasting"""
        # Train with dummy data
        training_data = [(self.student, 75.0)]
        self.forecaster.train(training_data)
        
        forecast = self.forecaster.forecast_performance(self.student)
        
        self.assertIn('predicted_score', forecast)
        self.assertIn('confidence_low', forecast)
        self.assertIn('confidence_high', forecast)
        self.assertIn('trend', forecast)
        
        self.assertGreaterEqual(forecast['predicted_score'], 0.0)
        self.assertLessEqual(forecast['predicted_score'], 100.0)
        self.assertIn(forecast['trend'], ['IMPROVING', 'DECLINING', 'STABLE', 'UNKNOWN'])


class ChurnRiskPredictorTestCase(TestCase):
    """Test churn risk prediction"""
    
    def setUp(self):
        self.student = User.objects.create_user(
            username='testchurn',
            email='testchurn@example.com',
            password='password123'
        )
        self.predictor = ChurnRiskPredictor()
    
    def test_extract_features(self):
        """Test feature extraction for churn"""
        features = self.predictor.extract_features(self.student)
        
        self.assertEqual(len(features), 5)
        self.assertIsInstance(features, np.ndarray)
        
        # Features: attendance_rate, performance, days_since_login, disciplinary, outstanding
        self.assertGreaterEqual(features[0], 0.0)  # Attendance rate
        self.assertLessEqual(features[0], 100.0)
    
    def test_train_model(self):
        """Test model training"""
        training_data = [
            (self.student, False),  # Not churned
        ]
        
        self.predictor.train(training_data)
        self.assertTrue(self.predictor.is_trained)
    
    def test_predict_churn_probability(self):
        """Test churn probability prediction"""
        # Train with dummy data
        training_data = [(self.student, False)]
        self.predictor.train(training_data)
        
        probability = self.predictor.predict_churn_probability(self.student)
        
        self.assertIsInstance(probability, float)
        self.assertGreaterEqual(probability, 0.0)
        self.assertLessEqual(probability, 1.0)
    
    def test_get_risk_factors(self):
        """Test risk factor identification"""
        risk_factors = self.predictor.get_risk_factors(self.student)
        
        self.assertIsInstance(risk_factors, list)
        # All factors should be strings
        for factor in risk_factors:
            self.assertIsInstance(factor, str)


class MLPredictionServiceTestCase(TestCase):
    """Test ML prediction service"""
    
    def setUp(self):
        self.student = User.objects.create_user(
            username='testml',
            email='testml@example.com',
            password='password123'
        )
        self.service = MLPredictionService()
    
    def test_service_initialization(self):
        """Test service components are initialized"""
        self.assertIsNotNone(self.service.fee_predictor)
        self.assertIsNotNone(self.service.performance_forecaster)
        self.assertIsNotNone(self.service.churn_predictor)
    
    def test_generate_student_risk_report(self):
        """Test comprehensive risk report generation"""
        # Train models with dummy data
        self.service.fee_predictor.train([(self.student, False)])
        self.service.performance_forecaster.train([(self.student, 75.0)])
        self.service.churn_predictor.train([(self.student, False)])
        
        report = self.service.generate_student_risk_report(self.student)
        
        # Check report structure
        self.assertIn('student_id', report)
        self.assertIn('generated_at', report)
        self.assertIn('fee_default', report)
        self.assertIn('performance', report)
        self.assertIn('churn', report)
        
        # Check fee default section
        self.assertIn('probability', report['fee_default'])
        self.assertIn('risk_category', report['fee_default'])
        self.assertIn(report['fee_default']['risk_category'], ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'])
        
        # Check performance section
        self.assertIn('predicted_score', report['performance'])
        self.assertIn('trend', report['performance'])
        
        # Check churn section
        self.assertIn('probability', report['churn'])
        self.assertIn('risk_factors', report['churn'])
        self.assertIsInstance(report['churn']['risk_factors'], list)
    
    def test_get_high_risk_students(self):
        """Test high-risk student identification"""
        # Train models
        self.service.fee_predictor.train([(self.student, False)])
        self.service.performance_forecaster.train([(self.student, 75.0)])
        self.service.churn_predictor.train([(self.student, False)])
        
        high_risk = self.service.get_high_risk_students(threshold=0.7)
        
        self.assertIsInstance(high_risk, list)
        # Each item should have student and report
        for item in high_risk:
            self.assertIn('student', item)
            self.assertIn('report', item)
