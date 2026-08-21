from decimal import Decimal
from django.core.exceptions import ValidationError
from ..models import GradeRule

class GradeResolver:
    """
    Shared domain service to resolve a percentage to a GradeRule
    based on a GradingScheme.
    """
    
    def __init__(self, scheme):
        self.scheme = scheme
        self.rules = list(GradeRule.objects.filter(scheme=scheme))

    def resolve(self, percentage):
        dec_pct = Decimal(str(percentage))
        
        # Exact match
        for rule in self.rules:
            if rule.min_score <= dec_pct <= rule.max_score:
                return rule
                
        # Tolerance match for rounding boundaries
        for rule in self.rules:
            if (rule.min_score - Decimal("0.05")) <= dec_pct <= (rule.max_score + Decimal("0.05")):
                return rule
                
        raise ValidationError(f"No grade rule covers {percentage}% in scheme {self.scheme.name}.")
