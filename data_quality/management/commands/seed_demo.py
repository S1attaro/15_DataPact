"""
Seed realistic DataPact test data for the P1-A1 Part 4 demonstration.

Usage:
    python manage.py seed_demo

Creates the two superusers required by the assignment, three analyst accounts,
seven datasets, versioned contracts with rules, validation runs across several
months, and the violations those runs produced. Safe to re-run: it clears the
application tables first, leaving auth accounts intact.
"""

import datetime

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from data_quality.models import (
    Contract,
    Dataset,
    ValidationRule,
    ValidationRun,
    Violation,
)

RT = ValidationRule.RuleType


def dt(y, m, d, hh=9, mm=0):
    return timezone.make_aware(datetime.datetime(y, m, d, hh, mm))


class Command(BaseCommand):
    help = "Seed realistic DataPact demonstration data."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Clearing existing DataPact records...")
        Violation.objects.all().delete()
        ValidationRun.objects.all().delete()
        ValidationRule.objects.all().delete()
        Contract.objects.all().delete()
        Dataset.objects.all().delete()

        # ---------------------------------------------------------------
        # Accounts
        # ---------------------------------------------------------------
        # The assignment text gives two different superuser names in two
        # places, so both are created.
        for uname in ("mohitg2", "tester"):
            if not User.objects.filter(username=uname).exists():
                User.objects.create_superuser(uname, f"{uname}@illinois.edu", "uiuc12345")

        def analyst(username, first, last):
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@illinois.edu",
                    "first_name": first,
                    "last_name": last,
                    "is_staff": True,
                },
            )
            return user

        tejas = analyst("tejasj2", "Tejas", "Jaggi")
        hriday = analyst("hda3", "Hriday", "Agarwal")
        connor = analyst("cslat", "Connor", "Slattery")
        # Submits runs but owns no datasets, so the account can be deleted to
        # demonstrate SET_NULL without tripping the PROTECT on Dataset.owner.
        contractor = analyst("adaily", "Avery", "Daily")

        # ---------------------------------------------------------------
        # Datasets
        # ---------------------------------------------------------------
        def dataset(name, owner, team, desc):
            return Dataset.objects.create(
                name=name, owner=owner, source_team=team, description=desc
            )

        enrollment = dataset(
            "Monthly Enrollment Export", tejas, "Registrar",
            "One row per student per term. Delivered on the first working day of each month.",
        )
        sales = dataset(
            "Weekly Sales Extract", hriday, "Finance",
            "Order-level revenue for the preceding week, exported every Monday.",
        )
        workorders = dataset(
            "Facilities Work Orders", connor, "Operations",
            "Open and closed maintenance requests across campus buildings.",
        )
        sensors = dataset(
            "Sensor Readings - Lab 3", hriday, "Research",
            "Temperature and humidity readings collected on a fixed hourly cycle.",
        )
        catalog = dataset(
            "Course Catalog Snapshot", tejas, "Provost Office",
            "Full course listing captured at the start of each registration window.",
        )
        payroll = dataset(
            "Payroll Deductions Export", connor, "Human Resources",
            "Per-employee deduction totals for the current pay period.",
        )
        library = dataset(
            "Library Circulation Log", tejas, "University Library",
            "Checkout and return events aggregated daily by branch.",
        )

        # ---------------------------------------------------------------
        # Contracts and rules
        # ---------------------------------------------------------------
        def contract(ds, version, status, note, created):
            c = Contract.objects.create(
                dataset=ds, version_number=version, status=status, change_note=note
            )
            Contract.objects.filter(pk=c.pk).update(created_at=created)
            c.refresh_from_db()
            return c

        def rule(c, column, rule_type, params=None):
            return ValidationRule.objects.create(
                contract=c, column_name=column, rule_type=rule_type,
                parameters=params or {},
            )

        # -- Monthly Enrollment Export: four versions telling the AUDIT story --
        enr_v1 = contract(enrollment, 1, Contract.Status.RETIRED,
                          "Initial contract.", dt(2026, 4, 11))
        rule(enr_v1, "student_id", RT.NOT_NULL)
        rule(enr_v1, "term_code", RT.NOT_NULL)
        rule(enr_v1, "credit_hours", RT.TYPE_MATCH, {"type": "integer"})
        rule(enr_v1, "status", RT.ALLOWED_VALUES, {"values": ["ACTIVE", "INACTIVE"]})

        enr_v2 = contract(enrollment, 2, Contract.Status.RETIRED,
                          "Added uniqueness rule on student_id.", dt(2026, 6, 2))
        rule(enr_v2, "student_id", RT.NOT_NULL)
        rule(enr_v2, "student_id", RT.UNIQUE)
        rule(enr_v2, "term_code", RT.NOT_NULL)
        rule(enr_v2, "term_code", RT.REGEX, {"pattern": "^[0-9]{4}[A-Z]$"})
        rule(enr_v2, "credit_hours", RT.TYPE_MATCH, {"type": "integer"})
        rule(enr_v2, "status", RT.ALLOWED_VALUES, {"values": ["ACTIVE", "INACTIVE"]})

        enr_v3 = contract(enrollment, 3, Contract.Status.RETIRED,
                          "Tightened credit_hours range to 0-24.", dt(2026, 8, 19))
        v3_sid_nn = rule(enr_v3, "student_id", RT.NOT_NULL)
        rule(enr_v3, "student_id", RT.UNIQUE)
        rule(enr_v3, "term_code", RT.NOT_NULL)
        rule(enr_v3, "term_code", RT.REGEX, {"pattern": "^[0-9]{4}[A-Z]$"})
        rule(enr_v3, "credit_hours", RT.NOT_NULL)
        rule(enr_v3, "credit_hours", RT.TYPE_MATCH, {"type": "integer"})
        v3_credit_range = rule(enr_v3, "credit_hours", RT.RANGE, {"min": 0, "max": 24})
        rule(enr_v3, "status", RT.NOT_NULL)
        v3_status_allowed = rule(enr_v3, "status", RT.ALLOWED_VALUES,
                                 {"values": ["ACTIVE", "INACTIVE"]})
        rule(enr_v3, "enrolled_on", RT.NOT_NULL)
        rule(enr_v3, "enrolled_on", RT.TYPE_MATCH, {"type": "date"})

        # Created in response to the September run: AUDIT is legitimate.
        enr_v4 = contract(enrollment, 4, Contract.Status.ACTIVE,
                          "Added AUDIT to allowed status values after Registrar "
                          "introduced the audit enrolment category.", dt(2026, 9, 2))
        rule(enr_v4, "student_id", RT.NOT_NULL)
        rule(enr_v4, "student_id", RT.UNIQUE)
        rule(enr_v4, "term_code", RT.NOT_NULL)
        rule(enr_v4, "term_code", RT.REGEX, {"pattern": "^[0-9]{4}[A-Z]$"})
        rule(enr_v4, "credit_hours", RT.NOT_NULL)
        rule(enr_v4, "credit_hours", RT.TYPE_MATCH, {"type": "integer"})
        rule(enr_v4, "credit_hours", RT.RANGE, {"min": 0, "max": 24})
        rule(enr_v4, "status", RT.NOT_NULL)
        rule(enr_v4, "status", RT.ALLOWED_VALUES,
             {"values": ["ACTIVE", "INACTIVE", "AUDIT"]})
        rule(enr_v4, "enrolled_on", RT.NOT_NULL)
        rule(enr_v4, "enrolled_on", RT.TYPE_MATCH, {"type": "date"})

        # -- Other datasets: one contract each --
        sales_v1 = contract(sales, 1, Contract.Status.ACTIVE,
                            "Initial contract.", dt(2026, 5, 4))
        rule(sales_v1, "order_id", RT.UNIQUE)
        rule(sales_v1, "order_total", RT.NOT_NULL)
        s_total_range = rule(sales_v1, "order_total", RT.RANGE, {"min": 0, "max": 100000})
        rule(sales_v1, "currency", RT.ALLOWED_VALUES, {"values": ["USD", "CAD"]})
        rule(sales_v1, "ordered_on", RT.TYPE_MATCH, {"type": "date"})

        wo_v1 = contract(workorders, 1, Contract.Status.ACTIVE,
                         "Initial contract.", dt(2026, 5, 20))
        rule(wo_v1, "work_order_id", RT.UNIQUE)
        rule(wo_v1, "building_code", RT.REGEX, {"pattern": "^[A-Z]{3}-[0-9]{3}$"})
        wo_priority = rule(wo_v1, "priority", RT.ALLOWED_VALUES,
                           {"values": ["LOW", "MEDIUM", "HIGH", "URGENT"]})
        rule(wo_v1, "opened_on", RT.NOT_NULL)

        sen_v1 = contract(sensors, 1, Contract.Status.ACTIVE,
                          "Initial contract.", dt(2026, 6, 15))
        rule(sen_v1, "reading_id", RT.UNIQUE)
        sen_temp = rule(sen_v1, "temperature_c", RT.RANGE, {"min": -20, "max": 60})
        rule(sen_v1, "humidity_pct", RT.RANGE, {"min": 0, "max": 100})
        rule(sen_v1, "recorded_at", RT.NOT_NULL)

        cat_v1 = contract(catalog, 1, Contract.Status.DRAFT,
                          "Draft contract, not yet in use.", dt(2026, 9, 4))
        rule(cat_v1, "crn", RT.UNIQUE)
        rule(cat_v1, "subject_code", RT.REGEX, {"pattern": "^[A-Z]{2,4}$"})
        rule(cat_v1, "credit_hours", RT.RANGE, {"min": 0, "max": 20})

        pay_v1 = contract(payroll, 1, Contract.Status.ACTIVE,
                          "Initial contract.", dt(2026, 7, 1))
        rule(pay_v1, "employee_id", RT.NOT_NULL)
        rule(pay_v1, "deduction_total", RT.RANGE, {"min": 0, "max": 25000})

        lib_v1 = contract(library, 1, Contract.Status.ACTIVE,
                          "Initial contract.", dt(2026, 7, 14))
        rule(lib_v1, "branch_code", RT.NOT_NULL)
        rule(lib_v1, "checkouts", RT.TYPE_MATCH, {"type": "integer"})

        # ---------------------------------------------------------------
        # Validation runs
        # ---------------------------------------------------------------
        def run(c, fname, rows, status, when, user):
            return ValidationRun.objects.create(
                contract=c, submitted_by=user, file_name=fname, row_count=rows,
                status=status, started_at=when,
                finished_at=when + datetime.timedelta(seconds=9),
            )

        S = ValidationRun.Status

        r_apr = run(enr_v1, "enrollment_2026_04.csv", 4611, S.FAILED, dt(2026, 4, 30, 8, 12), tejas)
        r_may = run(enr_v1, "enrollment_2026_05.csv", 4640, S.FAILED, dt(2026, 5, 31, 8, 9), tejas)
        r_jun = run(enr_v2, "enrollment_2026_06.csv", 4702, S.PASSED, dt(2026, 6, 30, 8, 15), hriday)
        r_jul = run(enr_v2, "enrollment_2026_07.csv", 4755, S.FAILED, dt(2026, 7, 31, 8, 4), contractor)
        r_aug = run(enr_v3, "enrollment_2026_08.csv", 4780, S.PASSED, dt(2026, 8, 31, 8, 21), tejas)
        r_sep = run(enr_v3, "enrollment_2026_09.csv", 4812, S.FAILED, dt(2026, 9, 1, 8, 14), tejas)

        r_sales1 = run(sales_v1, "sales_2026_w35.csv", 12904, S.PASSED, dt(2026, 8, 31, 6, 2), hriday)
        r_sales2 = run(sales_v1, "sales_2026_w36.csv", 13120, S.FAILED, dt(2026, 9, 4, 6, 2), hriday)
        r_wo = run(wo_v1, "workorders_2026_08.csv", 2210, S.FAILED, dt(2026, 8, 28, 17, 40), connor)
        r_sen = run(sen_v1, "sensors_lab3_2026_09.csv", 8640, S.FAILED, dt(2026, 9, 5, 11, 23), contractor)
        r_pay = run(pay_v1, "payroll_2026_08.csv", 3402, S.PASSED, dt(2026, 8, 15, 7, 30), connor)
        r_lib = run(lib_v1, "circulation_2026_08.csv", 980, S.ERROR, dt(2026, 8, 20, 22, 5), tejas)

        # ---------------------------------------------------------------
        # Violations
        # ---------------------------------------------------------------
        def violation(r, rl, count, samples, msg, resolution=Violation.Resolution.OPEN):
            return Violation.objects.create(
                run=r, rule=rl, failed_row_count=count, sample_values=samples,
                message=msg, resolution=resolution,
            )

        RES = Violation.Resolution

        v1_status = enr_v1.rules.get(column_name="status", rule_type=RT.ALLOWED_VALUES)
        v1_credit = enr_v1.rules.get(column_name="credit_hours", rule_type=RT.TYPE_MATCH)
        v2_term_rx = enr_v2.rules.get(column_name="term_code", rule_type=RT.REGEX)

        violation(r_apr, v1_credit, 12,
                  [{"row": 209, "value": "12.5"}, {"row": 814, "value": "n/a"}],
                  "12 rows in credit_hours are not whole numbers. The rule requires an integer.",
                  RES.DATA_ISSUE)
        violation(r_apr, v1_status, 3,
                  [{"row": 77, "value": "active"}, {"row": 1902, "value": "Active"}],
                  "3 rows in status use lower-case values. The rule permits only ACTIVE and INACTIVE.",
                  RES.DATA_ISSUE)
        violation(r_may, v1_credit, 5,
                  [{"row": 340, "value": "15.0"}],
                  "5 rows in credit_hours are not whole numbers. The rule requires an integer.",
                  RES.DATA_ISSUE)
        violation(r_jul, v2_term_rx, 8,
                  [{"row": 51, "value": "2026-FA"}, {"row": 3300, "value": "26FA"}],
                  "8 rows in term_code do not match the required format ^[0-9]{4}[A-Z]$.",
                  RES.DATA_ISSUE)

        # The September run: one genuine data error and one legitimate change.
        violation(r_sep, v3_credit_range, 47,
                  [{"row": 118, "value": -3}, {"row": 902, "value": -1}, {"row": 4120, "value": -12}],
                  "47 rows in credit_hours contain a negative value. The rule requires 0 to 24.",
                  RES.DATA_ISSUE)
        violation(r_sep, v3_status_allowed, 4,
                  [{"row": 118, "value": "AUDIT"}, {"row": 442, "value": "AUDIT"},
                   {"row": 2910, "value": "AUDIT"}, {"row": 3377, "value": "AUDIT"}],
                  "4 rows in status contain the value AUDIT. The rule permits only "
                  "ACTIVE and INACTIVE.",
                  RES.CONTRACT_UPDATED)

        violation(r_sales2, s_total_range, 23,
                  [{"row": 88, "value": -14.5}, {"row": 6001, "value": -220.0}],
                  "23 rows in order_total are negative. The rule requires 0 to 100000.",
                  RES.OPEN)
        violation(r_wo, wo_priority, 61,
                  [{"row": 14, "value": "P1"}, {"row": 990, "value": "CRITICAL"}],
                  "61 rows in priority use values outside the permitted set.",
                  RES.OPEN)
        violation(r_sen, sen_temp, 140,
                  [{"row": 3301, "value": 98.4}, {"row": 3302, "value": 101.2}],
                  "140 rows in temperature_c fall outside the permitted range of -20 to 60.",
                  RES.DATA_ISSUE)

        # ---------------------------------------------------------------
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {User.objects.count()} users, "
            f"{Dataset.objects.count()} datasets, "
            f"{Contract.objects.count()} contracts, "
            f"{ValidationRule.objects.count()} rules, "
            f"{ValidationRun.objects.count()} runs, "
            f"{Violation.objects.count()} violations."
        ))
