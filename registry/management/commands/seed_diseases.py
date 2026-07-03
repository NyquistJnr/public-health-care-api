# registry/management/commands/seed_diseases.py
from django.core.management.base import BaseCommand

from registry.models import Disease

DISEASES = [
    # CRITICAL - dangerous, outbreak-prone
    ("Lassa Fever", "CRITICAL", "Acute viral haemorrhagic fever transmitted by rodents."),
    ("Cholera", "CRITICAL", "Acute diarrhoeal infection from contaminated water/food, can be fatal within hours if untreated."),
    ("Meningitis", "CRITICAL", "Inflammation of the membranes around the brain and spinal cord."),
    ("Ebola Virus Disease", "CRITICAL", "Severe viral haemorrhagic fever with high case fatality."),
    ("Measles", "CRITICAL", "Highly contagious viral disease, outbreak-prone in under-vaccinated populations."),
    ("Yellow Fever", "CRITICAL", "Mosquito-borne viral haemorrhagic disease."),
    ("Diphtheria", "CRITICAL", "Acute bacterial infection affecting the throat and airway."),

    # MODERATE
    ("Tuberculosis", "MODERATE", "Chronic bacterial infection primarily affecting the lungs."),
    ("Typhoid Fever", "MODERATE", "Bacterial infection spread through contaminated food/water."),
    ("HIV/AIDS", "MODERATE", "Chronic viral infection affecting the immune system."),
    ("Malaria", "MODERATE", "Mosquito-borne parasitic disease, endemic and high-volume."),
    ("Hepatitis B", "MODERATE", "Viral infection affecting the liver."),
    ("Pneumonia", "MODERATE", "Acute lower respiratory infection."),
    ("Tetanus", "MODERATE", "Bacterial infection affecting the nervous system."),

    # LOW
    ("Common Cold", "LOW", "Mild viral upper respiratory infection."),
    ("Mild Diarrhea", "LOW", "Self-limiting gastrointestinal upset."),
    ("Seasonal Influenza", "LOW", "Common viral respiratory illness."),
    ("Mild Skin Infection", "LOW", "Localised, non-systemic skin infection."),
    ("Tension Headache", "LOW", "Common, non-infectious headache."),
]


class Command(BaseCommand):
    help = "Seeds the global disease registry (public schema). Idempotent - safe to re-run."

    def handle(self, *args, **kwargs):
        created_count = 0
        for name, severity, description in DISEASES:
            _, created = Disease.objects.get_or_create(
                name=name,
                defaults={"severity": severity, "description": description},
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Disease registry seeded: {created_count} created, {len(DISEASES) - created_count} already existed."
        ))
