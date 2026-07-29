import sys
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from schedule.models import PeriodSlot, TimetableEntry, TeacherAvailability
from academic.models import AllocatedSubject, Term, ClassRoom


class Command(BaseCommand):
    help = "Auto-generate a timetable for a term via backtracking search (best-effort)."

    def add_arguments(self, parser):
        parser.add_argument("--term", type=int, required=True, help="Term ID to generate for.")
        parser.add_argument("--dry-run", action="store_true", help="Preview without saving.")
        parser.add_argument(
            "--max-backtracks", type=int, default=5000,
            help="Safety cap on search steps before returning the best partial result found."
        )

    def handle(self, *args, **options):
        term_id = options["term"]
        dry_run = options["dry_run"]
        max_backtracks = options["max_backtracks"]

        try:
            term = Term.objects.get(pk=term_id)
        except Term.DoesNotExist:
            raise CommandError(f"Term {term_id} does not exist.")

        slots = list(
            PeriodSlot.objects.filter(term=term, is_break=False).order_by("day_of_week", "period_number")
        )
        if not slots:
            raise CommandError("No non-break PeriodSlot rows exist for this term — set up the daily grid first.")

        from django.db.models import Q
        allocations = list(
            AllocatedSubject.objects.filter(
                Q(term=term) | Q(term__isnull=True, academic_year=term.academic_year)
            ).select_related("teacher_name", "class_room", "subject")
        )
        if not allocations:
            raise CommandError("No AllocatedSubject records found for this academic year / term.")

        # Existing active entries are treated as fixed/locked — generation
        # fills gaps around them, never overwrites what's already scheduled.
        existing_entries = list(
            TimetableEntry.objects.filter(term=term, is_active=True).select_related("slot")
        )

        teacher_busy = defaultdict(set)    # teacher_id -> {slot_id, ...}
        classroom_busy = defaultdict(set)  # classroom_id -> {slot_id, ...}
        daily_count = defaultdict(int)     # (allocation_id, day_of_week) -> count so far

        for entry in existing_entries:
            if entry.teacher_id:
                teacher_busy[entry.teacher_id].add(entry.slot_id)
            classroom_busy[entry.classroom_id].add(entry.slot_id)

        unavailable = defaultdict(set)  # teacher_id -> {slot_id, ...} explicitly blocked
        for ta in TeacherAvailability.objects.filter(term=term, is_available=False):
            unavailable[ta.teacher_id].add(ta.slot_id)

        # Expand each AllocatedSubject into one "variable" per weekly occurrence,
        # e.g. Maths/JSS1A needing 5 periods/week becomes 5 separate variables.
        variables = []
        for alloc in allocations:
            for occurrence in range(alloc.weekly_periods):
                variables.append({"allocation": alloc, "occurrence": occurrence})

        if not variables:
            self.stdout.write("Nothing to schedule — every allocation has weekly_periods=0.")
            return

        # Most-constrained-first ordering: busiest teachers get first pick of
        # slots, since they have the least flexibility left as the week fills up.
        teacher_load = defaultdict(int)
        for alloc in allocations:
            teacher_load[alloc.teacher_name_id] += alloc.weekly_periods

        variables.sort(
            key=lambda v: (
                -teacher_load[v["allocation"].teacher_name_id],
                v["allocation"].max_daily_periods,
                v["allocation"].id,
            )
        )

        state = {"backtracks": 0}
        best = {"assignments": {}, "count": 0}

        def is_valid(var, slot):
            alloc = var["allocation"]
            teacher_id = alloc.teacher_name_id
            classroom_id = alloc.class_room_id

            if slot.id in teacher_busy[teacher_id]:
                return False
            if slot.id in classroom_busy[classroom_id]:
                return False
            if slot.id in unavailable[teacher_id]:
                return False
            if daily_count[(alloc.id, slot.day_of_week)] >= alloc.max_daily_periods:
                return False
            return True

        def place(var, slot):
            alloc = var["allocation"]
            teacher_busy[alloc.teacher_name_id].add(slot.id)
            classroom_busy[alloc.class_room_id].add(slot.id)
            daily_count[(alloc.id, slot.day_of_week)] += 1

        def unplace(var, slot):
            alloc = var["allocation"]
            teacher_busy[alloc.teacher_name_id].discard(slot.id)
            classroom_busy[alloc.class_room_id].discard(slot.id)
            daily_count[(alloc.id, slot.day_of_week)] -= 1

        def backtrack(i, current):
            if len(current) > best["count"]:
                best["count"] = len(current)
                best["assignments"] = dict(current)

            if i == len(variables):
                return True
            if state["backtracks"] > max_backtracks:
                return False

            var = variables[i]
            for slot in slots:
                if not is_valid(var, slot):
                    continue
                place(var, slot)
                current[i] = slot
                if backtrack(i + 1, current):
                    return True
                unplace(var, slot)
                del current[i]
                state["backtracks"] += 1

            return False

        sys.setrecursionlimit(max(1000, len(variables) + 200))
        complete = backtrack(0, {})
        assignments = best["assignments"]  # best partial (or full) result found
        unplaced = [v for i, v in enumerate(variables) if i not in assignments]

        if dry_run:
            label = "complete" if complete else "partial"
            self.stdout.write(f"[DRY RUN] {label.title()} solution — would create {len(assignments)} entries.")
            if unplaced:
                self.stdout.write(f"[DRY RUN] {len(unplaced)} occurrences could not be placed:")
                for v in unplaced:
                    alloc = v["allocation"]
                    self.stdout.write(f"  - {alloc.subject} / {alloc.class_room} (occurrence {v['occurrence'] + 1})")

            # Preview free-period fill without writing anything.
            all_classrooms = {c.id: c for c in ClassRoom.objects.all()}
            covered = {(e.classroom_id, e.slot_id) for e in existing_entries}
            covered.update(
                (variables[i]["allocation"].class_room_id, slot.id) for i, slot in assignments.items()
            )
            would_be_free = sum(
                1 for classroom_id in all_classrooms for slot in slots
                if (classroom_id, slot.id) not in covered
            )
            self.stdout.write(f"[DRY RUN] Would additionally auto-fill {would_be_free} slots as free periods.")
            return

        created = []
        with transaction.atomic():
            for i, slot in assignments.items():
                alloc = variables[i]["allocation"]
                entry = TimetableEntry(
                    term=term,
                    slot=slot,
                    classroom=alloc.class_room,
                    subject=alloc,
                    teacher=alloc.teacher_name,
                )
                entry.full_clean()
                entry.save()
                created.append(entry)

            # Auto-fill anything still uncovered as a free period — must run
            # AFTER real subject placement, so it only fills genuinely empty
            # cells, and covers EVERY classroom in the school, not just ones
            # with allocations, so no classroom is left with ambiguous gaps.
            free_created = 0
            all_classrooms = {c.id: c for c in ClassRoom.objects.all()}
            covered = set(
                TimetableEntry.objects.filter(term=term, is_active=True)
                .values_list("classroom_id", "slot_id")
            )
            for classroom_id, classroom in all_classrooms.items():
                for slot in slots:
                    if (classroom_id, slot.id) not in covered:
                        free_entry = TimetableEntry(
                            term=term, slot=slot, classroom=classroom, is_free_period=True,
                        )
                        free_entry.full_clean()
                        free_entry.save()
                        free_created += 1

        if free_created:
            self.stdout.write(f"Auto-filled {free_created} remaining slots as free periods.")

        if complete:
            self.stdout.write(self.style.SUCCESS(f"Generated a complete timetable — {len(created)} entries created."))
        else:
            self.stdout.write(self.style.WARNING(
                f"Generated a partial timetable — {len(created)} entries created, "
                f"{len(unplaced)} occurrences need manual placement:"
            ))
            for v in unplaced:
                alloc = v["allocation"]
                self.stdout.write(f"  - {alloc.subject} / {alloc.class_room} (occurrence {v['occurrence'] + 1})")