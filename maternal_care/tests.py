# maternal_care/tests.py

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient 
from django_tenants.test.cases import TenantTestCase
from core.models import User, PatientProfile
from facilities.models import Facility
from appointments.models import Appointment
from maternal_care.models import MaternalCareEpisode

class MaternalCareLifecycleTest(TenantTestCase):
    
    @classmethod
    def setup_tenant(cls, tenant):
        """Required by django-tenants to setup the schema before testing"""
        tenant.auto_create_schema = True

    def setUp(self):
        super().setUp()
        
        self.client = APIClient()
        self.client.defaults['HTTP_HOST'] = self.domain.domain

        self.facility = Facility.objects.create(
            name="Test General Hospital", 
            facility_type="Hospital", 
            lga="Test LGA", 
            level="Secondary"
        )
        
        self.doctor = User.objects.create_user(
            username='doctor@test.com', email='doctor@test.com', password='password123',
            first_name='John', last_name='Doe', role='DOCTOR', facility=self.facility
        )
        
        self.patient = User.objects.create_user(
            username='patient@test.com', email='patient@test.com', password='password123',
            first_name='Jane', last_name='Doe', role='PATIENT', facility=self.facility
        )
        PatientProfile.objects.create(
            user=self.patient, sex='F', date_of_birth='1995-01-01', blood_group='O+'
        )
        
        self.appointment = Appointment.objects.create(
            facility=self.facility, patient=self.patient, assigned_to=self.doctor,
            appointment_date='2026-05-10', appointment_time='09:00:00',
            visit_type='ANTENATAL', status='COMPLETED'
        )
        
        response = self.client.post('/api/v1/auth/login/', {
            'email': 'doctor@test.com', 'password': 'password123'
        })
        self.token = response.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')

    def test_create_maternal_care_episode(self):
        """Test that a doctor can start a new pregnancy episode for a patient"""
        
        url = reverse('maternal-episode-list')
        data = {
            "patient": str(self.patient.id),
            "status": "ACTIVE",
            "last_menstrual_period": "2026-01-01",
            "expected_date_of_delivery": "2026-10-08",
            "gravida": 1,
            "parity": 0,
            "living_children": 0
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MaternalCareEpisode.objects.count(), 1)
        self.assertEqual(MaternalCareEpisode.objects.first().patient, self.patient)
        self.assertIn('MAT-', response.data['episode_id'])

    def test_create_anc_visit(self):
        """Test logging an ANC visit against an active episode"""
        
        episode = MaternalCareEpisode.objects.create(
            patient=self.patient, created_by=self.doctor
        )
        
        url = reverse('anc-visit-list')
        data = {
            "episode": str(episode.id),
            "appointment": str(self.appointment.id),
            "attendance_type": "NEW",
            "tt_dose_given": "TT1",
            "iron_folate_given": True
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['iron_folate_given'])
