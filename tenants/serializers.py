"""
Tenant API Serializers
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from rest_framework import serializers
from .models import Client, Domain, Inspector


class SchoolSignupSerializer(serializers.Serializer):
    """Serializer for school registration"""
    school_name = serializers.CharField(
        max_length=100,
        help_text="Official name of the school"
    )
    subdomain = serializers.CharField(
        max_length=50,
        help_text="Subdomain for school portal (e.g., 'myschool' for myschool.yourdomain.com)"
    )
    admin_first_name = serializers.CharField(max_length=100)
    admin_last_name = serializers.CharField(max_length=100)
    admin_email = serializers.EmailField()
    admin_phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')

    # School contact info (separate from the admin account)
    contact_email = serializers.EmailField(required=False, allow_blank=True, default='')
    contact_phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')

    enable_mobile = serializers.BooleanField(
        default=False,
        required=False,
        help_text="Enable mobile app access (Premium feature)"
    )
    
    def validate_subdomain(self, value):
        """Validate subdomain format"""
        import re
        if not re.match(r'^[a-z0-9-]+$', value):
            raise serializers.ValidationError(
                "Subdomain must contain only lowercase letters, numbers, and hyphens"
            )
        if len(value) < 3:
            raise serializers.ValidationError(
                "Subdomain must be at least 3 characters long"
            )
        return value.lower()
    
    def validate_admin_email(self, value):
        """Check if email is already used by another school admin"""
        from django.contrib.auth import get_user_model
        from django_tenants.utils import schema_context
        
        # Check across all tenant schemas
        for tenant in Client.objects.exclude(schema_name='public'):
            try:
                with schema_context(tenant.schema_name):
                    User = get_user_model()
                    if User.objects.filter(email=value, is_admin=True).exists():
                        raise serializers.ValidationError(
                            "This email is already registered as a school administrator"
                        )
            except:
                continue
        
        return value


class TenantListSerializer(serializers.ModelSerializer):
    plan = serializers.SerializerMethodField()
    domain = serializers.SerializerMethodField()
    student_count = serializers.SerializerMethodField()
    teacher_count = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()
    admin_email = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            'id', 'schema_name', 'name', 'status',
            'created_on', 'has_mobile_access', 'plan',
            'domain', 'student_count', 'teacher_count',
            'admin_email', 'contact_email', 'contact_phone',
            'logo_url', 'website', 'address', 'motto',
            'approved_at', 'rejection_reason',
        ]

    def get_plan(self, obj):
        return obj.get_plan_name()

    def get_domain(self, obj):
        domain = obj.domains.filter(is_primary=True).first()
        return domain.domain if domain else None

    def get_student_count(self, obj):
        return obj.cached_student_count

    def get_teacher_count(self, obj):
        return obj.cached_teacher_count

    def get_logo_url(self, obj):
        return obj.get_logo_url()

    def get_admin_email(self, obj):
        try:
            from django_tenants.utils import schema_context
            User = get_user_model()
            with schema_context(obj.schema_name):
                admin = User.objects.filter(is_admin=True).first()
                return admin.email if admin else None
        except Exception:
            return None



class TenantDetailSerializer(TenantListSerializer):
    """Detailed serializer for tenant information"""
    total_revenue = serializers.SerializerMethodField()
    mobile_access_granted = serializers.DateField(read_only=True)
    
    class Meta(TenantListSerializer.Meta):
        fields = TenantListSerializer.Meta.fields + ['total_revenue', 'mobile_access_granted']
    
    def get_total_revenue(self, obj):
        """Get total revenue for this tenant"""
        try:
            from .services import TenantService
            stats = TenantService.get_tenant_stats(obj.schema_name)
            return float(stats.get('total_revenue', 0))
        except:
            return 0.0
        

# tenants/inspector_serializers.py
# Add these to tenants/serializers.py



User = get_user_model()


class InspectorSerializer(serializers.ModelSerializer):
    """Read serializer — used for list and detail views."""

    email        = serializers.EmailField(source='user.email',      read_only=True)
    first_name   = serializers.CharField(source='user.first_name',  read_only=True)
    last_name    = serializers.CharField(source='user.last_name',   read_only=True)
    full_name    = serializers.SerializerMethodField()
    access_label = serializers.CharField(
        source='get_access_level_display', read_only=True
    )
    assigned_tenant_count = serializers.SerializerMethodField()

    class Meta:
        model  = Inspector
        fields = [
            'id',
            'email',
            'first_name',
            'last_name',
            'full_name',
            'title',
            'organisation',
            'access_level',
            'access_label',
            'assigned_tenants',
            'assigned_tenant_count',
            'is_active',
            'notes',
            'created_at',
        ]

    def get_full_name(self, obj):
        u = obj.user
        name = f"{u.first_name or ''} {u.last_name or ''}".strip()
        return name or u.email

    def get_assigned_tenant_count(self, obj):
        return obj.assigned_tenants.count()


class InspectorCreateSerializer(serializers.Serializer):
    """
    Write serializer — creates both the CustomUser and Inspector profile
    in a single transaction, then sends credentials by email.
    """
    # User fields
    email      = serializers.EmailField()
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    last_name  = serializers.CharField(max_length=100, required=False, allow_blank=True)
    phone_number = serializers.CharField(
        max_length=15, required=False, allow_blank=True, default=''
    )

    # Inspector profile fields
    title        = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    organisation = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    access_level = serializers.ChoiceField(
        choices=Inspector.AccessLevel.choices,
        default=Inspector.AccessLevel.ASSIGNED,
    )
    assigned_tenant_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
        help_text='List of Client PKs — only needed when access_level=assigned',
    )
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                'A user with this email already exists.'
            )
        return value

    def validate(self, data):
        # If access_level is assigned, warn if no tenants provided
        # (not a hard error — super admin may assign later)
        return data

    @transaction.atomic
    def save(self):
        data = self.validated_data

        # ── 1. Generate temp password ─────────────────────────────────────────
        temp_password = User.objects.make_random_password(length=12)

        # ── 2. Create CustomUser ──────────────────────────────────────────────
        user = User.objects.create_user(
            email=data['email'],
            password=temp_password,
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            phone_number=data.get('phone_number') or None,
            is_active=True,
            is_inspector=True,       # ← the new flag on CustomUser
        )

        # Add to inspector group (consistent with teacher/parent/accountant pattern)
        group, _ = Group.objects.get_or_create(name='inspector')
        user.groups.add(group)

        # ── 3. Create Inspector profile ───────────────────────────────────────
        inspector = Inspector.objects.create(
            user=user,
            title=data.get('title', ''),
            organisation=data.get('organisation', ''),
            access_level=data.get('access_level', Inspector.AccessLevel.ASSIGNED),
            notes=data.get('notes', ''),
        )

        if data.get('assigned_tenant_ids'):
            inspector.assigned_tenants.set(data['assigned_tenant_ids'])

        # ── 4. Send credentials email ─────────────────────────────────────────
        try:
            from core.email_utils import send_inspector_credentials
            send_inspector_credentials(
                email=user.email,
                first_name=user.first_name or 'Inspector',
                organisation=inspector.organisation,
                temp_password=temp_password,
            )
        except Exception as e:
            # Don't fail creation if email fails — log it
            import logging
            logging.getLogger(__name__).warning(
                'Failed to send inspector credentials to %s: %s', user.email, e
            )

        # Return inspector + temp_password so the view can show it on screen
        return inspector, temp_password


class InspectorUpdateSerializer(serializers.ModelSerializer):
    """
    Partial update — allows changing profile fields and reassigning tenants.
    Does NOT change email or password (separate endpoints for those).
    """
    assigned_tenant_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        write_only=True,
    )

    class Meta:
        model  = Inspector
        fields = [
            'title',
            'organisation',
            'access_level',
            'assigned_tenant_ids',
            'is_active',
            'notes',
        ]

    def update(self, instance, validated_data):
        tenant_ids = validated_data.pop('assigned_tenant_ids', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if tenant_ids is not None:
            instance.assigned_tenants.set(tenant_ids)

        # Sync is_active on user account too
        if 'is_active' in validated_data:
            instance.user.is_active = validated_data['is_active']
            instance.user.save(update_fields=['is_active'])

        return instance