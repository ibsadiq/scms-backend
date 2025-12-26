"""
core/models.py
Re-exports SchoolSettings from tenants app for backward compatibility.
All school settings are now centralized in the tenants app.
"""
from tenants.models import SchoolSettings

__all__ = ['SchoolSettings']