# maternal_care/serializers.py
from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from .models import (
    MaternalCareEpisode, ANCVisit, PNCVisit, 
    PNCNewbornAssessment, MaternalScheduleRule
)
from core.models import User, PatientProfile
from .services import MaternalScheduleEngine
from appointments.models import Appointment

class MaternalScheduleRuleSerializer(serializers.ModelSerializer):
    """Serializer for configuring Global State-Level ANC/PNC Scheduling Rules."""
    class Meta:
        model = MaternalScheduleRule
        fields = [
            'id', 'care_type', 'rule_type', 'interval_days', 
            'intervals_sequence', 'visit_tasks', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        rule_type = attrs.get('rule_type')
        if rule_type == 'RECURRING' and not attrs.get('interval_days'):
            raise serializers.ValidationError({"interval_days": "Must provide interval_days for RECURRING rules."})
        if rule_type == 'VARIABLE_SEQUENCE' and not attrs.get('intervals_sequence'):
            raise serializers.ValidationError({"intervals_sequence": "Must provide intervals_sequence array for VARIABLE_SEQUENCE rules."})
        return attrs


class MaternalCareEpisodeSerializer(serializers.ModelSerializer):
    """Main serializer for Pregnancy Episodes, including patient details and custom override schedules."""
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    patient_display_id = serializers.CharField(source='patient.patient_profile.patient_id', read_only=True)
    
    class Meta:
        model = MaternalCareEpisode
        fields = [
            'id', 'episode_id', 'patient', 'patient_name', 'patient_display_id', 'status',
            'last_menstrual_period', 'expected_date_of_delivery', 'gravida', 'parity',
            'living_children', 'partner_name', 'partner_phone', 
            'custom_anc_schedule', 'custom_pnc_schedule', 'created_at'
        ]
        read_only_fields = ['id', 'episode_id', 'expected_date_of_delivery', 'created_at']


class ANCVisitSerializer(serializers.ModelSerializer):
    """Serializer for individual Antenatal Care visits."""
    appointment_date = serializers.DateField(source='appointment.appointment_date', read_only=True)
    
    class Meta:
        model = ANCVisit
        fields = '__all__'
        read_only_fields = [
            'id', 'visit_sequence_number', 'next_visit_date', 
            'recommended_tasks', 'created_at', 'updated_at', 'created_by'
        ]


class PNCNewbornAssessmentSerializer(serializers.ModelSerializer):
    """Serializer for assessing newborns during a PNC visit."""
    baby_name = serializers.CharField(source='baby.get_full_name', read_only=True)
    baby_display_id = serializers.CharField(source='baby.patient_profile.patient_id', read_only=True)

    class Meta:
        model = PNCNewbornAssessment
        fields = [
            'id', 'pnc_visit', 'baby', 'baby_name', 'baby_display_id', 'cord_care_assessed',
            'temperature', 'exclusive_breastfeeding', 'newborn_danger_signs',
            'neonatal_jaundice', 'first_dose_antibiotics_given', 'kmc_provided', 'outcome'
        ]


class PNCVisitSerializer(serializers.ModelSerializer):
    """Serializer for Postnatal Care visits, including nested newborn assessments."""
    appointment_date = serializers.DateField(source='appointment.appointment_date', read_only=True)
    newborn_assessments = PNCNewbornAssessmentSerializer(many=True, read_only=True)
    
    class Meta:
        model = PNCVisit
        fields = [
            'id', 'episode', 'appointment', 'appointment_date', 'attendance_type',
            'visit_sequence_number', 'next_visit_date', 'recommended_tasks',
            'timing_of_visit', 'vaginal_examination_conducted', 'hemoglobin_pcv',
            'urinalysis', 'counselling_topics', 'outcome', 'referral_reason',
            'newborn_assessments', 'created_at'
        ]
        read_only_fields = [
            'id', 'visit_sequence_number', 'next_visit_date', 
            'recommended_tasks', 'created_at', 'updated_at', 'created_by'
        ]

class NewbornRegistrationSerializer(serializers.Serializer):
    """Details for a single newborn (used during delivery recording)."""
    first_name = serializers.CharField(max_length=150, help_text="e.g., Baby 1, or actual name if given")
    last_name = serializers.CharField(max_length=150, help_text="Usually the father's or mother's surname")
    sex = serializers.ChoiceField(choices=PatientProfile.SEX_CHOICES)
    weight_kg = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)


class RecordDeliverySerializer(serializers.Serializer):
    """Payload for recording a delivery and auto-registering the babies."""
    delivery_date = serializers.DateField()
    babies = NewbornRegistrationSerializer(many=True, help_text="List of babies born (handles twins/triplets)")


class EpisodeBabySerializer(serializers.Serializer):
    """Formats the output for babies born during a specific episode."""
    id = serializers.UUIDField()
    patient_display_id = serializers.CharField(source='patient_profile.patient_id', read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    sex = serializers.CharField(source='patient_profile.sex', read_only=True)
    date_of_birth = serializers.DateField(source='patient_profile.date_of_birth', read_only=True)

class AppointmentForANCSerializer(serializers.Serializer):
    # --- 1. Appointment / Core Info ---
    patient_id = serializers.UUIDField(help_text="UUID of the Patient")
    assigned_to_id = serializers.UUIDField(required=False, allow_null=True, help_text="Optional UUID of the Doctor/Nurse")
    appointment_date = serializers.DateField(default=timezone.now)
    appointment_time = serializers.TimeField(default=timezone.now)
    
    # --- 2. Episode Info (Required ONLY if NEW Pregnancy) ---
    last_menstrual_period = serializers.DateField(required=False, allow_null=True)
    gravida = serializers.IntegerField(required=False, allow_null=True)
    parity = serializers.IntegerField(required=False, allow_null=True)
    living_children = serializers.IntegerField(required=False, allow_null=True)
    partner_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    partner_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    # --- 3. ANC Clinical Data ---
    hiv_status = serializers.CharField(max_length=50, required=False, allow_blank=True)
    vdrl_syphilis = serializers.CharField(max_length=50, required=False, allow_blank=True)
    hepatitis_b = serializers.CharField(max_length=50, required=False, allow_blank=True)
    hemoglobin = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    urinalysis = serializers.CharField(required=False, allow_blank=True)
    
    tt_dose_given = serializers.CharField(max_length=20, required=False, allow_blank=True)
    iptp_dose_given = serializers.CharField(max_length=20, required=False, allow_blank=True)
    iron_folate_given = serializers.BooleanField(default=False)
    
    risk_factors = serializers.CharField(required=False, allow_blank=True)
    clinical_notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        patient_id = attrs.get('patient_id')
        facility = self.context['request'].user.facility

        try:
            patient = User.objects.get(id=patient_id, role='PATIENT', facility=facility)
            attrs['patient_instance'] = patient
        except User.DoesNotExist:
            raise serializers.ValidationError({"patient_id": "Valid patient not found in this facility."})

        active_episode = MaternalCareEpisode.objects.filter(patient=patient, status='ACTIVE').first()
        
        if active_episode:
            attrs['episode_instance'] = active_episode
            attrs['attendance_type'] = 'RETURN'
        else:
            if attrs.get('last_menstrual_period') is None or attrs.get('gravida') is None or attrs.get('parity') is None:
                raise serializers.ValidationError(
                    "This patient has no active pregnancy. You must provide 'last_menstrual_period', 'gravida', and 'parity' to initiate a new episode."
                )
            attrs['attendance_type'] = 'NEW'

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user = self.context['request'].user
        patient = validated_data.pop('patient_instance')
        attendance_type = validated_data.pop('attendance_type')
        episode = validated_data.get('episode_instance')

        if attendance_type == 'NEW':
            episode = MaternalCareEpisode.objects.create(
                patient=patient,
                last_menstrual_period=validated_data.get('last_menstrual_period'),
                gravida=validated_data.get('gravida'),
                parity=validated_data.get('parity'),
                living_children=validated_data.get('living_children', 0),
                partner_name=validated_data.get('partner_name', ''),
                partner_phone=validated_data.get('partner_phone', ''),
                created_by=user
            )

        assigned_to_id = validated_data.get('assigned_to_id')
        assigned_to = User.objects.filter(id=assigned_to_id).first() if assigned_to_id else user

        appointment = Appointment.objects.create(
            facility=user.facility,
            patient=patient,
            assigned_to=assigned_to,
            appointment_date=validated_data.get('appointment_date'),
            appointment_time=validated_data.get('appointment_time'),
            visit_type='ANTENATAL',
            status='COMPLETED',
            reason_for_visit="Routine ANC Visit",
            notes=validated_data.get('clinical_notes', ''),
            created_by=user
        )

        anc_visit = ANCVisit.objects.create(
            episode=episode,
            appointment=appointment,
            attendance_type=attendance_type,
            hiv_status=validated_data.get('hiv_status', ''),
            vdrl_syphilis=validated_data.get('vdrl_syphilis', ''),
            hepatitis_b=validated_data.get('hepatitis_b', ''),
            hemoglobin=validated_data.get('hemoglobin'),
            urinalysis=validated_data.get('urinalysis', ''),
            tt_dose_given=validated_data.get('tt_dose_given', ''),
            iptp_dose_given=validated_data.get('iptp_dose_given', ''),
            iron_folate_given=validated_data.get('iron_folate_given', False),
            risk_factors=validated_data.get('risk_factors', ''),
            notes=validated_data.get('clinical_notes', ''),
            created_by=user
        )

        previous_visits_count = ANCVisit.objects.filter(episode=episode).count()
        anc_visit.visit_sequence_number = previous_visits_count
        
        next_date, recommended_tasks = MaternalScheduleEngine.calculate_next_visit(
            episode=episode,
            care_type='ANC',
            current_visit_sequence=anc_visit.visit_sequence_number,
            last_visit_date=appointment.appointment_date
        )
        
        anc_visit.next_visit_date = next_date
        anc_visit.recommended_tasks = recommended_tasks
        anc_visit.save(update_fields=['visit_sequence_number', 'next_visit_date', 'recommended_tasks'])

        return anc_visit

class WalkInDeliverySerializer(serializers.Serializer):
    """Used only if the patient delivered elsewhere and has no existing episode in our system"""
    delivery_date = serializers.DateField()
    gravida = serializers.IntegerField()
    parity = serializers.IntegerField()
    babies_to_register = NewbornRegistrationSerializer(many=True)

class PNCBabyAssessmentInputSerializer(serializers.Serializer):
    """Clinical assessment for each baby during the PNC visit"""
    baby_id = serializers.UUIDField(help_text="UUID of the existing baby user record")
    cord_care_assessed = serializers.BooleanField(default=False)
    temperature = serializers.DecimalField(max_digits=4, decimal_places=1, required=False, allow_null=True)
    exclusive_breastfeeding = serializers.CharField(max_length=50, required=False, allow_blank=True)
    newborn_danger_signs = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    neonatal_jaundice = serializers.BooleanField(default=False)
    first_dose_antibiotics_given = serializers.BooleanField(default=False)
    kmc_provided = serializers.BooleanField(default=False)
    outcome = serializers.ChoiceField(choices=PNCNewbornAssessment.OUTCOME_CHOICES, default='HEALTHY')

class AppointmentForPNCSerializer(serializers.Serializer):
    # --- 1. Core Info ---
    patient_id = serializers.UUIDField(help_text="UUID of the Mother")
    assigned_to_id = serializers.UUIDField(required=False, allow_null=True)
    appointment_date = serializers.DateField(default=timezone.now)
    appointment_time = serializers.TimeField(default=timezone.now)
    
    # --- 2. Walk-In Edge Case (Optional) ---
    walk_in_delivery_data = WalkInDeliverySerializer(
        required=False, 
        help_text="Provide this ONLY if the mother delivered elsewhere and has no Episode in this system."
    )

    # --- 3. Maternal PNC Data ---
    timing_of_visit = serializers.CharField(max_length=50, help_text="e.g., 3 Days, 6 Weeks")
    vaginal_examination_conducted = serializers.BooleanField(default=False)
    hemoglobin_pcv = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    urinalysis = serializers.CharField(required=False, allow_blank=True)
    counselling_topics = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    outcome = serializers.ChoiceField(choices=PNCVisit.OUTCOME_CHOICES, default='TREATED')
    referral_reason = serializers.CharField(required=False, allow_blank=True)
    clinical_notes = serializers.CharField(required=False, allow_blank=True)

    # --- 4. Newborn Assessments ---
    baby_assessments = PNCBabyAssessmentInputSerializer(
        many=True, required=False, 
        help_text="Assessments for the babies. If walk-in, pass empty array and we will register them first."
    )

    def validate(self, attrs):
        patient_id = attrs.get('patient_id')
        facility = self.context['request'].user.facility

        try:
            patient = User.objects.get(id=patient_id, role='PATIENT', facility=facility)
            attrs['patient_instance'] = patient
        except User.DoesNotExist:
            raise serializers.ValidationError({"patient_id": "Valid patient not found in this facility."})

        episode = MaternalCareEpisode.objects.filter(
            patient=patient, 
            status__in=['ACTIVE', 'DELIVERED']
        ).order_by('-created_at').first()
        
        walk_in_data = attrs.get('walk_in_delivery_data')

        if episode:
            if episode.status == 'ACTIVE':
                episode.status = 'DELIVERED'
                episode.save(update_fields=['status', 'updated_at'])
            
            attrs['episode_instance'] = episode
            attrs['attendance_type'] = 'RETURN' if PNCVisit.objects.filter(episode=episode).exists() else 'NEW'
        else:
            if not walk_in_data:
                raise serializers.ValidationError(
                    "This patient has no pregnancy record on file. You must provide 'walk_in_delivery_data' to register her past delivery before conducting a PNC visit."
                )
            attrs['attendance_type'] = 'NEW'

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        import uuid
        from django.contrib.auth.models import Group
        
        user = self.context['request'].user
        facility = user.facility
        patient = validated_data.pop('patient_instance')
        attendance_type = validated_data.pop('attendance_type')
        episode = validated_data.get('episode_instance')
        walk_in_data = validated_data.get('walk_in_delivery_data')

        if not episode and walk_in_data:
            episode = MaternalCareEpisode.objects.create(
                patient=patient,
                status='DELIVERED',
                gravida=walk_in_data['gravida'],
                parity=walk_in_data['parity'],
                created_by=user
            )
            
            patient_group = Group.objects.filter(name='PATIENT').first()
            for baby_data in walk_in_data['babies_to_register']:
                dummy_email = f"baby_{uuid.uuid4().hex[:10]}@placeholder.com"
                baby_user = User.objects.create(
                    username=dummy_email, email='', first_name=baby_data['first_name'],
                    last_name=baby_data['last_name'], role='PATIENT', facility=facility, created_by=user
                )
                baby_user.set_unusable_password()
                baby_user.save()
                if patient_group:
                    baby_user.groups.add(patient_group)
                    
                PatientProfile.objects.create(
                    user=baby_user, sex=baby_data['sex'], date_of_birth=walk_in_data['delivery_date'],
                    mother=patient, birth_episode=episode, created_by=user
                )

        assigned_to_id = validated_data.get('assigned_to_id')
        assigned_to = User.objects.filter(id=assigned_to_id).first() if assigned_to_id else user

        appointment = Appointment.objects.create(
            facility=facility,
            patient=patient,
            assigned_to=assigned_to,
            appointment_date=validated_data.get('appointment_date'),
            appointment_time=validated_data.get('appointment_time'),
            visit_type='POSTNATAL',
            status='COMPLETED', 
            reason_for_visit="Routine PNC Visit",
            notes=validated_data.get('clinical_notes', ''),
            created_by=user
        )

        pnc_visit = PNCVisit.objects.create(
            episode=episode,
            appointment=appointment,
            attendance_type=attendance_type,
            timing_of_visit=validated_data.get('timing_of_visit'),
            vaginal_examination_conducted=validated_data.get('vaginal_examination_conducted', False),
            hemoglobin_pcv=validated_data.get('hemoglobin_pcv'),
            urinalysis=validated_data.get('urinalysis', ''),
            counselling_topics=validated_data.get('counselling_topics', []),
            outcome=validated_data.get('outcome', 'TREATED'),
            referral_reason=validated_data.get('referral_reason', ''),
            created_by=user
        )

        baby_assessments = validated_data.get('baby_assessments', [])
        for assessment in baby_assessments:
            try:
                baby_user = User.objects.get(id=assessment['baby_id'], role='PATIENT')
                PNCNewbornAssessment.objects.create(
                    pnc_visit=pnc_visit,
                    baby=baby_user,
                    cord_care_assessed=assessment.get('cord_care_assessed', False),
                    temperature=assessment.get('temperature'),
                    exclusive_breastfeeding=assessment.get('exclusive_breastfeeding', ''),
                    newborn_danger_signs=assessment.get('newborn_danger_signs', []),
                    neonatal_jaundice=assessment.get('neonatal_jaundice', False),
                    first_dose_antibiotics_given=assessment.get('first_dose_antibiotics_given', False),
                    kmc_provided=assessment.get('kmc_provided', False),
                    outcome=assessment.get('outcome', 'HEALTHY'),
                    created_by=user
                )
            except User.DoesNotExist:
                continue

        previous_visits_count = PNCVisit.objects.filter(episode=episode).count()
        pnc_visit.visit_sequence_number = previous_visits_count
        
        next_date, recommended_tasks = MaternalScheduleEngine.calculate_next_visit(
            episode=episode,
            care_type='PNC',
            current_visit_sequence=pnc_visit.visit_sequence_number,
            last_visit_date=appointment.appointment_date
        )
        
        pnc_visit.next_visit_date = next_date
        pnc_visit.recommended_tasks = recommended_tasks
        pnc_visit.save(update_fields=['visit_sequence_number', 'next_visit_date', 'recommended_tasks'])

        if not next_date:
            episode.status = 'CLOSED'
            episode.save(update_fields=['status', 'updated_at'])

        return pnc_visit
