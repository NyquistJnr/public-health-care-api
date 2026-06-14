# maternal_care/services.py
from datetime import timedelta, date
from typing import Tuple, Optional, List
from .models import MaternalScheduleRule, MaternalCareEpisode

class MaternalScheduleEngine:
    @staticmethod
    def calculate_next_visit(
        episode: MaternalCareEpisode, 
        care_type: str, 
        current_visit_sequence: int, 
        last_visit_date: date
    ) -> Tuple[Optional[date], List[str]]:
        """
        Computes the next appointment date and returns tasks due for that next visit.
        Prioritizes Episode custom overrides over Global State Rules.
        """
        
        rule_dict = None
        
        if care_type == 'ANC' and episode.custom_anc_schedule:
            rule_dict = episode.custom_anc_schedule
        elif care_type == 'PNC' and episode.custom_pnc_schedule:
            rule_dict = episode.custom_pnc_schedule
        else:
            global_rule = MaternalScheduleRule.objects.filter(care_type=care_type).first()
            if global_rule:
                rule_dict = {
                    "rule_type": global_rule.rule_type,
                    "interval_days": global_rule.interval_days,
                    "intervals_sequence": global_rule.intervals_sequence,
                    "visit_tasks": global_rule.visit_tasks
                }

        if not rule_dict:
            return None, []

        rule_type = rule_dict.get("rule_type", "ONCE")
        next_date = None
        
        index = current_visit_sequence - 1

        if rule_type == "ONCE":
            return None, []

        elif rule_type == "RECURRING":
            interval = rule_dict.get("interval_days", 0)
            if interval > 0:
                next_date = last_visit_date + timedelta(days=interval)

        elif rule_type == "VARIABLE_SEQUENCE":
            intervals = rule_dict.get("intervals_sequence", [])
            if isinstance(intervals, list) and index < len(intervals):
                days_until_next = intervals[index]
                next_date = last_visit_date + timedelta(days=days_until_next)

        next_visit_sequence = current_visit_sequence + 1
        tasks_dict = rule_dict.get("visit_tasks", {})
        next_tasks = tasks_dict.get(str(next_visit_sequence), [])

        return next_date, next_tasks
