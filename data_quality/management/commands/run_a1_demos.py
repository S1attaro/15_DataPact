"""
Demonstrate the P1-A1 Part 4 requirements: relationships, the multi-field
UniqueConstraint, and each on_delete behaviour.

Usage:
    python manage.py run_a1_demos

Every destructive demonstration runs inside a transaction that is rolled back
afterwards, so the seeded database is unchanged when the command finishes and
the same evidence can be reproduced on demand.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.db.models import Count, ProtectedError, Sum

from data_quality.models import (
    Contract,
    Dataset,
    ValidationRule,
    ValidationRun,
    Violation,
)


class Rollback(Exception):
    """Raised to undo a demonstration once its result has been captured."""


class Command(BaseCommand):
    help = "Run the P1-A1 Part 4 demonstrations (relationships, constraints, on_delete)."

    def head(self, text):
        self.stdout.write("")
        self.stdout.write("=" * 74)
        self.stdout.write(text)
        self.stdout.write("=" * 74)

    def ok(self, text):
        self.stdout.write(self.style.SUCCESS("  PASS  " + text))

    def info(self, text):
        self.stdout.write("        " + text)

    def handle(self, *args, **options):
        self.demo_relationships()
        self.demo_unique_contract()
        self.demo_unique_violation()
        self.demo_unique_dataset()
        self.demo_cascade()
        self.demo_protect_contract()
        self.demo_protect_owner()
        self.demo_set_null()
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            "All demonstrations complete. The database is unchanged."))

    # ------------------------------------------------------------------
    # A / B : relationships
    # ------------------------------------------------------------------
    def demo_relationships(self):
        self.head("1. FOREIGN-KEY RELATIONSHIPS")
        ds = Dataset.objects.get(name="Monthly Enrollment Export")
        self.info(f"Dataset: {ds.name}  (owner: {ds.owner.username}, team: {ds.source_team})")
        for c in ds.contracts.all():
            self.info(f"  Contract v{c.version_number} [{c.status}] "
                      f"- {c.rules.count()} rules, {c.runs.count()} runs "
                      f"- {c.change_note}")
        run = ValidationRun.objects.get(file_name="enrollment_2026_09.csv")
        self.info("")
        self.info(f"Run: {run.file_name} ({run.status}), checked against "
                  f"v{run.contract.version_number}, submitted by {run.submitted_by.username}")
        for v in run.violations.all():
            self.info(f"  {v.rule.column_name} / {v.rule.get_rule_type_display()} "
                      f"- {v.failed_row_count} rows - resolution: {v.get_resolution_display()}")

        self.info("")
        self.info("Relationship-spanning query (ValidationRun -> Contract -> Dataset):")
        n = ValidationRun.objects.filter(
            contract__dataset__name="Monthly Enrollment Export").count()
        self.info(f"  ValidationRun.objects.filter(contract__dataset__name=...).count() = {n}")

        self.info("")
        self.info("Grouped summary of violations by column:")
        rows = (Violation.objects
                .values("rule__column_name")
                .annotate(failures=Count("id"), rows_affected=Sum("failed_row_count"))
                .order_by("-rows_affected"))
        for r in rows:
            self.info(f"  {r['rule__column_name']:<16} {r['failures']} violation(s), "
                      f"{r['rows_affected']} rows affected")
        self.ok("Relationships traversed in both directions.")

    # ------------------------------------------------------------------
    # C : uniqueness constraints
    # ------------------------------------------------------------------
    def demo_unique_contract(self):
        self.head("2. UNIQUE CONSTRAINT - uniq_contract_dataset_version")
        ds = Dataset.objects.get(name="Monthly Enrollment Export")
        self.info("Rule: a dataset cannot have two contracts with the same version number.")
        self.info(f"Existing versions: "
                  f"{sorted(ds.contracts.values_list('version_number', flat=True))}")
        self.info("Attempting: Contract.objects.create(dataset=<enrollment>, version_number=3)")
        try:
            with transaction.atomic():
                Contract.objects.create(dataset=ds, version_number=3,
                                        status=Contract.Status.DRAFT,
                                        change_note="Duplicate version - should fail")
            self.stdout.write(self.style.ERROR("  FAIL  No error raised."))
        except IntegrityError as exc:
            self.ok(f"IntegrityError: {exc}")

    def demo_unique_violation(self):
        self.head("3. UNIQUE CONSTRAINT - uniq_violation_run_rule")
        run = ValidationRun.objects.get(file_name="enrollment_2026_09.csv")
        existing = run.violations.first()
        self.info("Rule: a run records one aggregated violation per rule, "
                  "not one record per bad cell.")
        self.info(f"Attempting a second violation for rule "
                  f"'{existing.rule.column_name} / {existing.rule.get_rule_type_display()}' "
                  f"on the same run.")
        try:
            with transaction.atomic():
                Violation.objects.create(run=run, rule=existing.rule, failed_row_count=1,
                                         message="Duplicate violation - should fail")
            self.stdout.write(self.style.ERROR("  FAIL  No error raised."))
        except IntegrityError as exc:
            self.ok(f"IntegrityError: {exc}")

    def demo_unique_dataset(self):
        self.head("4. UNIQUE CONSTRAINT - uniq_dataset_owner_name")
        ds = Dataset.objects.get(name="Monthly Enrollment Export")
        self.info("Rule: one analyst cannot register two datasets under the same name.")
        self.info(f"Attempting a second '{ds.name}' owned by {ds.owner.username}.")
        try:
            with transaction.atomic():
                Dataset.objects.create(name=ds.name, owner=ds.owner,
                                       source_team="Registrar")
            self.stdout.write(self.style.ERROR("  FAIL  No error raised."))
        except IntegrityError as exc:
            self.ok(f"IntegrityError: {exc}")

    # ------------------------------------------------------------------
    # D : on_delete behaviour
    # ------------------------------------------------------------------
    def demo_cascade(self):
        self.head("5. on_delete=CASCADE - Contract -> ValidationRule")
        self.info("A rule has no meaning outside the contract version it belongs to.")
        try:
            with transaction.atomic():
                draft = Contract.objects.get(dataset__name="Course Catalog Snapshot",
                                             version_number=1)
                before = ValidationRule.objects.count()
                owned = draft.rules.count()
                self.info(f"Contract '{draft}' has {owned} rules. "
                          f"Total rules in database: {before}.")
                draft.delete()
                after = ValidationRule.objects.count()
                self.info(f"After deleting the contract, total rules: {after}.")
                self.ok(f"{before - after} rules were removed with their parent contract.")
                raise Rollback
        except Rollback:
            self.info("(rolled back)")

    def demo_protect_contract(self):
        self.head("6. on_delete=PROTECT - Contract <- ValidationRun")
        self.info("Deleting a contract version that has been used to validate a file")
        self.info("would leave those runs uninterpretable. A used contract is retired,")
        self.info("never deleted.")
        c = Contract.objects.get(dataset__name="Monthly Enrollment Export", version_number=3)
        self.info(f"Contract '{c}' has {c.runs.count()} validation run(s).")
        try:
            with transaction.atomic():
                c.delete()
            self.stdout.write(self.style.ERROR("  FAIL  No error raised."))
        except ProtectedError as exc:
            self.ok(f"ProtectedError: {exc.args[0]}")

    def demo_protect_owner(self):
        self.head("7. on_delete=PROTECT - User <- Dataset.owner")
        self.info("Ownership records who is accountable for a feed, so removing an")
        self.info("account must not silently orphan the datasets it owns.")
        user = User.objects.get(username="tejasj2")
        self.info(f"User '{user.username}' owns {user.datasets.count()} dataset(s).")
        try:
            with transaction.atomic():
                user.delete()
            self.stdout.write(self.style.ERROR("  FAIL  No error raised."))
        except ProtectedError as exc:
            self.ok(f"ProtectedError: {exc.args[0]}")

    def demo_set_null(self):
        self.head("8. on_delete=SET_NULL - User <- ValidationRun.submitted_by")
        self.info("The audit record must outlive the account. Losing who ran a check is")
        self.info("acceptable; losing the check itself is not.")
        try:
            with transaction.atomic():
                user = User.objects.get(username="adaily")
                runs = list(user.submitted_runs.values_list("pk", flat=True))
                self.info(f"User '{user.username}' owns {user.datasets.count()} datasets "
                          f"and submitted {len(runs)} run(s): "
                          f"{list(ValidationRun.objects.filter(pk__in=runs).values_list('file_name', flat=True))}")
                user.delete()
                surviving = ValidationRun.objects.filter(pk__in=runs)
                self.info(f"After deleting the account, {surviving.count()} run(s) survive.")
                for r in surviving:
                    self.info(f"  {r.file_name}: submitted_by = {r.submitted_by}")
                self.ok("Runs preserved with submitted_by set to NULL.")
                raise Rollback
        except Rollback:
            self.info("(rolled back)")
