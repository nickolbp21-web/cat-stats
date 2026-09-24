"""Configurable birthdays, computed on the household's local calendar date."""
from datetime import date

def pet_age(birth_date, today):
    try:
        born = date.fromisoformat(birth_date)
        if born > today:
            return {}
        anniversary = date(today.year, born.month, min(born.day, 28) if born.month == 2 and born.day == 29 and not (today.year % 4 == 0 and (today.year % 100 != 0 or today.year % 400 == 0)) else born.day)
        years = today.year - born.year
        if anniversary > today:
            years -= 1
            year = today.year - 1
            anniversary = date(year, born.month, min(born.day, 28) if born.month == 2 and born.day == 29 and not (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else born.day)
        return {'age_years': years, 'age_days': (today - anniversary).days}
    except (ValueError, TypeError):
        return {}
