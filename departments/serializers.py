from rest_framework import serializers
from .models import Department
from core.models import User

class DepartmentSerializer(serializers.ModelSerializer):
    head_name = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = [
            'id', 'name', 'description', 'facility', 'head', 'head_name', 
            'member_count', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'facility', 'created_at', 'updated_at']

    def get_head_name(self, obj):
        if obj.head:
            return f"{obj.head.first_name} {obj.head.last_name}"
        return "Unassigned"

    def get_member_count(self, obj):
        count = obj.members.count()
        if obj.head and not obj.members.filter(id=obj.head_id).exists():
            count += 1
        return count

    def validate(self, attrs):
        facility = self.context['request'].user.facility
        head = attrs.get('head')
        
        if head and head.facility != facility:
            raise serializers.ValidationError({"head": "The department head must belong to your facility."})
            
        return attrs

class DepartmentMemberListSerializer(serializers.ModelSerializer):
    """Used specifically for the paginated roster endpoint"""
    position = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'role', 'staff_id', 'is_active', 'position']

    def get_position(self, obj):
        head_id = self.context.get('head_id')
        if head_id and obj.id == head_id:
            return "Head of Department"
        return "Member"

class DepartmentMemberUpdateSerializer(serializers.Serializer):
    user_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        help_text="List of staff UUIDs to add or remove"
    )
