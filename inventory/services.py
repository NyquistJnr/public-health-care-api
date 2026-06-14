# inventory/services.py
from datetime import timedelta, date
from typing import Optional

class ScheduleEngine:
    @staticmethod
    def calculate_next_due_date(schedule_rules: dict, previous_doses_count: int, last_dose_date: date) -> Optional[date]:
        """
        Calculates the next due date based on the item's custom JSON rules and the patient's history.
        """
        if not schedule_rules or not last_dose_date:
            return None

        rule_type = schedule_rules.get("type")

        if rule_type == "ONCE":
            return None

        elif rule_type == "RECURRING":
            interval = schedule_rules.get("interval_days", 0)
            return last_dose_date + timedelta(days=interval)

        elif rule_type == "VARIABLE_SEQUENCE":
            intervals = schedule_rules.get("intervals_in_days", [])
            if previous_doses_count < len(intervals):
                days_until_next = intervals[previous_doses_count]
                return last_dose_date + timedelta(days=days_until_next)

        return None
