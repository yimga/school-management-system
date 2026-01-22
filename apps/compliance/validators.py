"""Compliance validators for enforcing regional legal requirements."""
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta
from django.utils import timezone

class ComplianceValidator:
    def __init__(self, region, language='en'):
        self.region = region
        self.language = language
        self.errors = []
        self.warnings = []
    
    def add_error(self, message):
        self.errors.append(message)
    
    def add_warning(self, message):
        self.warnings.append(message)
    
    def is_valid(self):
        return len(self.errors) == 0
    
    def get_issues_count(self):
        return len(self.errors) + len(self.warnings)

class StudentIDValidator(ComplianceValidator):
    def validate(self, student_id, id_format=None):
        if not id_format and hasattr(self.region, 'student_id_format'):
            id_format = self.region.student_id_format
        if not id_format:
            return True
        if not (id_format.min_length <= len(student_id) <= id_format.max_length):
            self.add_error(f"ID length must be between {id_format.min_length} and {id_format.max_length}")
        if not student_id.startswith(id_format.prefix):
            self.add_warning(f"ID should start with prefix: {id_format.prefix}")
        return self.is_valid()

class CertificateValidator(ComplianceValidator):
    REQUIRED_FIELDS = {'student_name': 'Student name', 'course': 'Course', 'date_issued': 'Date issued', 'achievement_level': 'Achievement level'}
    
    def validate(self, cert_data, template=None):
        for field, label in self.REQUIRED_FIELDS.items():
            if field not in cert_data or not cert_data[field]:
                self.add_error(f"Missing: {label}")
        if template:
            if template.requires_principal_signature and not cert_data.get('principal_signature'):
                self.add_error("Principal signature required")
        return self.is_valid()

class DataRetentionValidator(ComplianceValidator):
    def validate(self, record_type, last_accessed_date, retention_months=24):
        retention_deadline = last_accessed_date + timedelta(days=retention_months*30)
        if timezone.now().date() > retention_deadline:
            self.add_warning(f"{record_type} retention period expired")
        return self.is_valid()

class PrivacyPolicyValidator(ComplianceValidator):
    REQUIRED_SECTIONS = ['data_collection', 'data_usage', 'data_protection', 'user_rights', 'contact_information', 'effective_date']
    
    def validate(self, policy_content):
        content_lower = policy_content.lower()
        for section in self.REQUIRED_SECTIONS:
            if section.replace('_', ' ') not in content_lower:
                self.add_error(f"Missing section: {section}")
        if len(policy_content) < 500:
            self.add_warning("Policy too short")
        return self.is_valid()

class RegionalComplianceValidator(ComplianceValidator):
    def validate_region_compliance(self, requirements):
        if not requirements:
            self.add_warning("No requirements defined")
            return True
        pending = sum(1 for r in requirements if r.status == 'pending')
        overdue = sum(1 for r in requirements if r.is_overdue())
        if overdue > 0:
            self.add_error(f"{overdue} requirements overdue")
        return len(self.errors) == 0
    
    def generate_compliance_score(self, requirements):
        if not requirements:
            return 0
        requirements_list = list(requirements)
        total = len(requirements_list)
        if total == 0:
            return 0
        completed = sum(1 for r in requirements_list if r.status in ['implemented', 'active'])
        return round((completed / total) * 100, 1)
