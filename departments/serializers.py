from rest_framework import serializers
from .models import Department
from core.models import User

class DepartmentMemberSerializer(serializers.ModelSerializer):
    """Simplified user serialization for listing members"""
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'role', 'staff_id', 'is_active']

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
        return obj.members.count()

    def validate(self, attrs):
        facility = self.context['request'].user.facility
        head = attrs.get('head')
        
        if head and head.facility != facility:
            raise serializers.ValidationError({"head": "The department head must belong to your facility."})
            
        return attrs

class DepartmentDetailSerializer(DepartmentSerializer):
    """Includes the full list of staff members, used only on retrieval of a specific department"""
    members_list = DepartmentMemberSerializer(source='members', many=True, read_only=True)

    class Meta(DepartmentSerializer.Meta):
        fields = DepartmentSerializer.Meta.fields + ['members_list']

class DepartmentMemberUpdateSerializer(serializers.Serializer):
    """Utility payload for bulk adding/removing staff"""
    user_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        help_text="List of staff UUIDs to add or remove"
    )
