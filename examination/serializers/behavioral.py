from rest_framework import serializers
from examination.models import BehavioralTrait, StudentBehavioralRating

class BehavioralTraitSerializer(serializers.ModelSerializer):
    class Meta:
        model = BehavioralTrait
        fields = ['id', 'domain', 'name', 'section', 'order', 'is_active', 'created_at', 'updated_at']

class StudentBehavioralRatingSerializer(serializers.ModelSerializer):
    trait_name = serializers.CharField(source='trait.name', read_only=True)
    domain = serializers.CharField(source='trait.domain', read_only=True)

    class Meta:
        model = StudentBehavioralRating
        fields = ['id', 'term_result', 'trait', 'trait_name', 'domain', 'rating', 'entered_by', 'updated_at']
        read_only_fields = ['entered_by']

class BulkBehavioralRatingItemSerializer(serializers.Serializer):
    trait_id = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)

class BulkBehavioralRatingSerializer(serializers.Serializer):
    term_result = serializers.IntegerField(required=False)
    term_result_id = serializers.IntegerField(required=False)
    ratings = BulkBehavioralRatingItemSerializer(many=True)

    def validate(self, attrs):
        if not attrs.get('term_result') and not attrs.get('term_result_id'):
            raise serializers.ValidationError("Either 'term_result' or 'term_result_id' is required.")
        return attrs
