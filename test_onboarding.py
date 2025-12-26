#!/usr/bin/env python
"""
Test script for the tenant onboarding system.
This script demonstrates the complete onboarding flow.
"""

import os
import django
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from django.contrib.sites.models import Site
from tenants.models import Tenant
from users.models import CustomUser


def test_onboarding_flow():
    """Test the complete onboarding flow"""

    print("=" * 60)
    print("TENANT ONBOARDING SYSTEM - TEST SCRIPT")
    print("=" * 60)

    # Step 1: Check if test tenant exists
    print("\n[Step 1] Checking for existing test tenant...")
    test_domain = "testschool.localhost"

    try:
        site = Site.objects.get(domain=test_domain)
        tenant = site.tenant
        print(f"✓ Found existing tenant: {tenant.school_name}")
        print(f"  - Onboarding completed: {tenant.onboarding_completed}")
        print(f"  - Admin user: {tenant.admin_user}")

        # Cleanup for fresh test
        print("\n  Cleaning up for fresh test...")
        if tenant.admin_user:
            tenant.admin_user.delete()
        tenant.delete()
        site.delete()
        print("  ✓ Cleanup complete")

    except Site.DoesNotExist:
        print("✓ No existing test tenant found (good for fresh test)")

    # Step 2: Create a new tenant
    print("\n[Step 2] Creating new tenant...")
    site = Site.objects.create(
        domain=test_domain,
        name="Test School"
    )

    tenant = Tenant.objects.create(
        site=site,
        school_name="Test School",
        primary_color="#1E40AF",
        secondary_color="#BA770F",
        address="123 Test Street",
        contact_email="admin@testschool.com",
        contact_phone="+1234567890",
        onboarding_completed=False  # Important: starts as False
    )

    print(f"✓ Tenant created successfully")
    print(f"  - ID: {tenant.id}")
    print(f"  - Domain: {site.domain}")
    print(f"  - School: {tenant.school_name}")
    print(f"  - Onboarding completed: {tenant.onboarding_completed}")
    print(f"  - Needs onboarding: {tenant.needs_onboarding}")

    # Step 3: Create admin user
    print("\n[Step 3] Creating admin user...")
    admin_user = CustomUser.objects.create_user(
        email="admin@testschool.com",
        password="TestPassword123!",
        first_name="Test",
        last_name="Admin",
        is_staff=True,
        is_superuser=True,
        is_active=True
    )

    # Link admin to tenant
    tenant.admin_user = admin_user
    tenant.save()

    print(f"✓ Admin user created successfully")
    print(f"  - Email: {admin_user.email}")
    print(f"  - Name: {admin_user.first_name} {admin_user.last_name}")
    print(f"  - Is staff: {admin_user.is_staff}")
    print(f"  - Is superuser: {admin_user.is_superuser}")

    # Step 4: Verify onboarding is still incomplete
    tenant.refresh_from_db()
    print("\n[Step 4] Verifying onboarding status...")
    print(f"  - Onboarding completed: {tenant.onboarding_completed}")
    print(f"  - Needs onboarding: {tenant.needs_onboarding}")

    assert not tenant.onboarding_completed, "Onboarding should not be completed yet!"
    assert tenant.needs_onboarding, "Tenant should need onboarding!"
    print("✓ Onboarding is correctly marked as incomplete")

    # Step 5: Complete onboarding
    print("\n[Step 5] Completing onboarding...")
    tenant.onboarding_completed = True
    tenant.save()

    tenant.refresh_from_db()
    print(f"✓ Onboarding marked as complete")
    print(f"  - Onboarding completed: {tenant.onboarding_completed}")
    print(f"  - Needs onboarding: {tenant.needs_onboarding}")

    assert tenant.onboarding_completed, "Onboarding should be completed!"
    assert not tenant.needs_onboarding, "Tenant should not need onboarding!"
    print("✓ Onboarding flow completed successfully!")

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print("✓ All tests passed!")
    print(f"\nTenant Details:")
    print(f"  - School: {tenant.school_name}")
    print(f"  - Domain: {tenant.site.domain}")
    print(f"  - Admin: {tenant.admin_user.email}")
    print(f"  - Onboarding: {'✓ Complete' if tenant.onboarding_completed else '✗ Incomplete'}")
    print("\nYou can now test the API endpoints:")
    print(f"  - Check status: GET http://{test_domain}:8000/api/tenants/onboarding/check/")
    print(f"  - Debug: GET http://{test_domain}:8000/api/tenants/debug/")

    print("\n" + "=" * 60)
    print("Test tenant will remain in database for API testing.")
    print("To clean up, run: python manage.py shell")
    print("Then: Site.objects.get(domain='testschool.localhost').delete()")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_onboarding_flow()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
