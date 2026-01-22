from datetime import timedelta
from django.utils import timezone

class ComplianceValidator:
    def __init__(self, region, language='en'):
        self.region = region
        self.language = language
        self.errors = []
        self.warnings = []
    
    def is_valid(self):
        return len(self.errors) == 0
    
    def add_error(self, msg):
        self.errors.append(msg)
    
    def add_warning(self, msg):
        self.warnings.append(msg)

class RegionalComplianceValidator(ComplianceValidator):
    def generate_compliance_score(self, requirements):
        if not requirements:
            return 0
        requirements_list = list(requirements)
        total = len(requirements_list)
        if total == 0:
            return 0
        completed = sum(1 for r in requirements_list if r.status in ['implemented', 'active'])
        return round((completed / total) * 100, 1)
