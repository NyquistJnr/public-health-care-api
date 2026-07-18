from departments.models import Department
d = Department.objects.filter(id="c0446b93-3a21-4711-bddd-4f11dda58931").first()
print(f"Department exists: {d is not None}")
if d:
    print(f"Department Facility: {d.facility_id}")
