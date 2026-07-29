from rest_framework import serializers
from .models import AllocatedSubject, Teacher, Subject, ClassRoom, AcademicYear, Term


class AllocatedSubjectSerializer(serializers.ModelSerializer):
    """Serializer for AllocatedSubject model"""
    teacher_name = serializers.PrimaryKeyRelatedField(
        queryset=Teacher.objects.all(),
        required=True
    )
    teacher_display = serializers.SerializerMethodField()
    teacher_name_display = serializers.SerializerMethodField()
    
    subject = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.all()
    )
    subject_name = serializers.CharField(
        source='subject.name',
        read_only=True
    )
    
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all()
    )
    academic_year_display = serializers.CharField(
        source='academic_year.name',
        read_only=True
    )
    academic_year_name = serializers.CharField(
        source='academic_year.name',
        read_only=True
    )
    
    term = serializers.PrimaryKeyRelatedField(
        queryset=Term.objects.all(),
        required=False,
        allow_null=True
    )
    term_name = serializers.CharField(
        source='term.name',
        read_only=True,
        allow_null=True
    )
    
    class_room = serializers.PrimaryKeyRelatedField(
        queryset=ClassRoom.objects.all()
    )
    class_room_display = serializers.SerializerMethodField()
    class_room_name = serializers.SerializerMethodField()

    class Meta:
        model = AllocatedSubject
        fields = [
            'id',
            'teacher_name',
            'teacher_display',
            'teacher_name_display',
            'subject',
            'subject_name',
            'academic_year',
            'academic_year_display',
            'academic_year_name',
            'term',
            'term_name',
            'class_room',
            'class_room_display',
            'class_room_name',
            'weekly_periods',
            'max_daily_periods',
        ]
        read_only_fields = ['id']

    def get_teacher_display(self, obj):
        if obj.teacher_name:
            if obj.teacher_name.user:
                fname = obj.teacher_name.user.first_name or ''
                lname = obj.teacher_name.user.last_name or ''
                name = f"{fname} {lname}".strip()
                if name:
                    return name
                return obj.teacher_name.user.email or f"Teacher #{obj.teacher_name.id}"
            return str(obj.teacher_name)
        return "Unassigned"

    def get_teacher_name_display(self, obj):
        return self.get_teacher_display(obj)

    def get_class_room_display(self, obj):
        if obj.class_room:
            cr = obj.class_room
            if hasattr(cr, 'name_display') and cr.name_display:
                return str(cr.name_display)
            if cr.name:
                cname = cr.name.name if hasattr(cr.name, 'name') else str(cr.name)
                if hasattr(cr, 'stream') and cr.stream and hasattr(cr.stream, 'name'):
                    return f"{cname} {cr.stream.name}"
                return cname
            return str(cr)
        return "N/A"

    def get_class_room_name(self, obj):
        return self.get_class_room_display(obj)


class AllocatedSubjectListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views"""
    id = serializers.IntegerField(read_only=True)
    teacher_name = serializers.SerializerMethodField()
    teacher_display = serializers.SerializerMethodField()
    teacher_name_display = serializers.SerializerMethodField()
    teacher_id = serializers.SerializerMethodField()
    
    subject_id = serializers.IntegerField(source='subject.id', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    
    class_room_id = serializers.IntegerField(source='class_room.id', read_only=True)
    class_room_display = serializers.SerializerMethodField()
    class_room_name = serializers.SerializerMethodField()
    
    academic_year_id = serializers.IntegerField(source='academic_year.id', read_only=True)
    academic_year_display = serializers.CharField(source='academic_year.name', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    
    term_id = serializers.IntegerField(source='term.id', read_only=True, allow_null=True)
    term_name = serializers.CharField(source='term.name', read_only=True, allow_null=True)

    class Meta:
        model = AllocatedSubject
        fields = [
            'id',
            'teacher_name',
            'teacher_display',
            'teacher_name_display',
            'teacher_id',
            'subject',
            'subject_id',
            'subject_name',
            'class_room',
            'class_room_id',
            'class_room_display',
            'class_room_name',
            'academic_year',
            'academic_year_id',
            'academic_year_display',
            'academic_year_name',
            'term',
            'term_id',
            'term_name',
            'weekly_periods',
        ]

    def get_teacher_id(self, obj):
        return obj.teacher_name.id if obj.teacher_name else None

    def get_teacher_name(self, obj):
        if obj.teacher_name:
            if obj.teacher_name.user:
                fname = obj.teacher_name.user.first_name or ''
                lname = obj.teacher_name.user.last_name or ''
                name = f"{fname} {lname}".strip()
                if name:
                    return name
                return obj.teacher_name.user.email or f"Teacher #{obj.teacher_name.id}"
            return str(obj.teacher_name)
        return "Unassigned"

    def get_teacher_display(self, obj):
        return self.get_teacher_name(obj)

    def get_teacher_name_display(self, obj):
        return self.get_teacher_name(obj)

    def get_class_room_display(self, obj):
        if obj.class_room:
            cr = obj.class_room
            if hasattr(cr, 'name_display') and cr.name_display:
                return str(cr.name_display)
            if cr.name:
                cname = cr.name.name if hasattr(cr.name, 'name') else str(cr.name)
                if hasattr(cr, 'stream') and cr.stream and hasattr(cr.stream, 'name'):
                    return f"{cname} {cr.stream.name}"
                return cname
            return str(cr)
        return "N/A"

    def get_class_room_name(self, obj):
        return self.get_class_room_display(obj)
