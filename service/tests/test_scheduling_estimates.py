from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from service.estimates import approve_current, recalculate_locked
from service.models import EstimateItem, Order
from service.orders import transition
from service.scheduling import _has_conflict, _validate_interval, assign_worker, update_schedule

from .base import MotorCase


class SchedulingTests(MotorCase):
    def future(self, hours=24):
        start = timezone.now() + timedelta(hours=hours)
        return start, start + timedelta(hours=1)

    def test_both_values_required_start_only(self):
        start, _ = self.future()
        with self.assertRaises(ValidationError):
            _validate_interval(start, None)

    def test_both_values_required_end_only(self):
        _, end = self.future()
        with self.assertRaises(ValidationError):
            _validate_interval(None, end)

    def test_clearing_both(self):
        worker = self.employee()
        self.order.assigned_to = worker
        self.order.confirmed_start_at, self.order.confirmed_end_at = self.future()
        self.order.confirmed_by = worker
        self.order.booking_confirmed_at = timezone.now()
        self.order.save()
        update_schedule(self.order.pk, None, None, worker)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.confirmed_start_at)
        self.assertIsNone(self.order.confirmed_by)
        self.assertIsNone(self.order.booking_confirmed_at)

    def test_exact_boundary_allowed(self):
        worker = self.employee()
        start, end = self.future()
        self.order.assigned_to = worker
        self.order.confirmed_start_at = start
        self.order.confirmed_end_at = end
        self.order.save()
        self.assertFalse(_has_conflict(None, worker.pk, end, end + timedelta(hours=1)))

    def test_full_overlap(self):
        worker = self.employee()
        start, end = self.future()
        self.order.assigned_to = worker
        self.order.confirmed_start_at = start
        self.order.confirmed_end_at = end
        self.order.save()
        self.assertTrue(
            _has_conflict(None, worker.pk, start - timedelta(minutes=10), end + timedelta(minutes=10))
        )

    def test_partial_overlap(self):
        worker = self.employee()
        start, end = self.future()
        self.order.assigned_to = worker
        self.order.confirmed_start_at = start
        self.order.confirmed_end_at = end
        self.order.save()
        self.assertTrue(_has_conflict(None, worker.pk, end - timedelta(minutes=10), end + timedelta(hours=1)))

    def test_same_interval(self):
        worker = self.employee()
        start, end = self.future()
        self.order.assigned_to = worker
        self.order.confirmed_start_at = start
        self.order.confirmed_end_at = end
        self.order.save()
        self.assertTrue(_has_conflict(None, worker.pk, start, end))

    def test_different_workers(self):
        first = self.employee("first")
        second = self.employee("second")
        start, end = self.future()
        self.order.assigned_to = first
        self.order.confirmed_start_at = start
        self.order.confirmed_end_at = end
        self.order.save()
        self.assertFalse(_has_conflict(None, second.pk, start, end))

    def test_terminal_order_ignored(self):
        worker = self.employee()
        start, end = self.future()
        self.order.assigned_to = worker
        self.order.status = Order.Status.DONE
        self.order.confirmed_start_at = start
        self.order.confirmed_end_at = end
        self.order.save()
        self.assertFalse(_has_conflict(None, worker.pk, start, end))

    def test_conflict_on_assignment(self):
        worker = self.employee()
        start, end = self.future()
        self.order.assigned_to = worker
        self.order.confirmed_start_at = start
        self.order.confirmed_end_at = end
        self.order.save()
        other = Order.objects.create(
            number=Order.new_number(),
            customer=self.customer,
            vehicle=self.vehicle,
            service=self.service,
            service_name=self.service.name,
            service_price_from=self.service.price_from,
            problem="Другой",
            desired_date=self.order.desired_date,
            confirmed_start_at=start,
            confirmed_end_at=end,
        )
        with self.assertRaises(ValidationError):
            assign_worker(other.pk, worker, worker)

    def test_past_interval(self):
        end = timezone.now() - timedelta(hours=1)
        with self.assertRaises(ValidationError):
            _validate_interval(end - timedelta(hours=1), end)

    def test_naive_interval_rejected(self):
        start = timezone.now().replace(tzinfo=None) + timedelta(days=1)
        with self.assertRaises(ValidationError):
            _validate_interval(start, start + timedelta(hours=1))


class EstimateTests(MotorCase):
    def set_approval_stage(self):
        self.order.status = Order.Status.AWAITING_APPROVAL
        self.order.estimate = Decimal("100.00")
        self.order.save()

    def test_total_calculation(self):
        EstimateItem.objects.create(
            order=self.order, item_type="work", name="Работа", quantity=Decimal("2"), unit_price=Decimal("50")
        )
        recalculate_locked(self.order, None, "test")
        self.order.refresh_from_db()
        self.assertEqual(self.order.estimate, Decimal("100"))

    def test_version_increment(self):
        before = self.order.estimate_version
        recalculate_locked(self.order, None, "test")
        self.order.refresh_from_db()
        self.assertEqual(self.order.estimate_version, before + 1)

    def test_approval_invalidation(self):
        self.order.estimate = Decimal("100")
        self.order.estimate_approved = True
        self.order.approved_estimate_amount = Decimal("100")
        self.order.save()
        recalculate_locked(self.order, None, "change")
        self.order.refresh_from_db()
        self.assertFalse(self.order.estimate_approved)

    def test_client_approval_only_awaiting(self):
        self.order.estimate = Decimal("100")
        self.order.save()
        with self.assertRaises(ValidationError):
            approve_current(self.order.pk, self.order.estimate_version, "client_portal")

    def test_stale_version(self):
        self.set_approval_stage()
        with self.assertRaises(ValidationError):
            approve_current(self.order.pk, self.order.estimate_version + 1, "client_portal")

    def test_duplicate_approval_idempotent(self):
        self.set_approval_stage()
        _, created = approve_current(self.order.pk, self.order.estimate_version, "client_portal")
        _, duplicate = approve_current(self.order.pk, self.order.estimate_version, "client_portal")
        self.assertTrue(created)
        self.assertFalse(duplicate)

    def test_manual_approval_method(self):
        self.set_approval_stage()
        actor = self.employee("finance", "Менеджеры", ("manage_finance",))
        approve_current(self.order.pk, self.order.estimate_version, "phone", actor, "Подтверждено")
        self.order.refresh_from_db()
        self.assertEqual(self.order.estimate_approval_method, "phone")

    def test_terminal_approval_denied(self):
        self.order.status = Order.Status.DONE
        self.order.estimate = Decimal("100")
        self.order.save()
        with self.assertRaises(PermissionDenied):
            approve_current(self.order.pk, self.order.estimate_version, "client_portal")

    def test_transition_guard_without_approval(self):
        self.set_approval_stage()
        manager = self.employee("manager", "Менеджеры", ("view_all_orders",))
        with self.assertRaises(PermissionDenied):
            transition(self.order, Order.Status.REPAIR, manager)

    def test_transition_after_current_approval(self):
        self.set_approval_stage()
        manager = self.employee("manager", "Менеджеры", ("view_all_orders",))
        approve_current(self.order.pk, self.order.estimate_version, "phone", manager, "ok")
        changed = transition(self.order, Order.Status.REPAIR, manager)
        self.assertEqual(changed.status, Order.Status.REPAIR)

    def test_approval_method_display(self):
        self.set_approval_stage()
        token = __import__("service.links", fromlist=["issue_link"]).issue_link(self.order)
        self.client.get(reverse("client_exchange", args=[self.order.public_id, token]))
        approve_current(self.order.pk, self.order.estimate_version, "client_portal")
        response = self.client.get(reverse("client_order", args=[self.order.public_id]))
        self.assertContains(response, "Согласовано клиентом")
