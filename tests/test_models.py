"""
Tests for inventree-mbom: models, cost calculations, and pricing engine.

Run via InvenTree's test runner:
    python manage.py test inventree_mbom

Or with pytest from inside InvenTree environment:
    pytest inventree_mbom/tests/ -v
"""

from decimal import Decimal

try:
    from django.test import TestCase

    from inventree_mbom.models import (
        LaborRate, MachineCenter,
        ProcessTemplate, ProcessTemplateStep,
        PartRouting, RoutingOperation,
    )


    class LaborRateTests(TestCase):
        """Tests for LaborRate model and cost helpers."""

        def setUp(self):
            self.lr = LaborRate.objects.create(
                name="Test Assembler",
                hourly_rate=Decimal("30.00"),
                currency="EUR",
            )

        def test_str(self):
            s = str(self.lr)
            self.assertIn("Test Assembler", s)
            self.assertIn("30.00", s)

        def test_rate_per_minute(self):
            expected = Decimal("30.00") / Decimal("60")
            self.assertAlmostEqual(float(self.lr.rate_per_minute), float(expected), places=6)

        def test_rate_per_minute_60eur(self):
            lr = LaborRate.objects.create(name="60EUR", hourly_rate=Decimal("60.00"), currency="EUR")
            self.assertAlmostEqual(float(lr.rate_per_minute), 1.00, places=4)


    class MachineCenterTests(TestCase):
        """Tests for MachineCenter model."""

        def setUp(self):
            self.mc = MachineCenter.objects.create(
                name="Test CNC",
                hourly_rate=Decimal("120.00"),
                currency="EUR",
                co2_factor_per_minute=Decimal("0.002"),
            )

        def test_str(self):
            self.assertIn("Test CNC", str(self.mc))

        def test_rate_per_minute(self):
            expected = Decimal("120.00") / Decimal("60")
            self.assertAlmostEqual(float(self.mc.rate_per_minute), float(expected), places=4)


    class RoutingOperationCostTests(TestCase):
        """Detailed cost calculation tests for RoutingOperation."""

        def setUp(self):
            from part.models import Part

            self.lr = LaborRate.objects.create(
                name="Cost Test Labor",
                hourly_rate=Decimal("60.00"),  # 1.00 EUR/min
                currency="EUR",
            )
            self.mc = MachineCenter.objects.create(
                name="Cost Test Machine",
                hourly_rate=Decimal("120.00"),  # 2.00 EUR/min
                currency="EUR",
                co2_factor_per_minute=Decimal("0.001"),
            )
            self.part, _ = Part.objects.get_or_create(
                name="mBOM Cost Test Assembly",
                defaults={"assembly": True, "component": False}
            )
            self.routing = PartRouting.objects.create(
                part=self.part,
                standard_batch_size=10,
            )
            self.op = RoutingOperation.objects.create(
                routing=self.routing,
                sequence_number="10",
                name="Test Op",
                labor_rate=self.lr,
                machine_center=self.mc,
                setup_time_minutes=Decimal("30.00"),    # 30 min setup
                run_time_per_unit_minutes=Decimal("2.00"),  # 2 min/unit
            )

        def tearDown(self):
            try:
                self.routing.delete()
                self.part.delete()
            except Exception:
                pass

        # --- Labor ---

        def test_labor_rate_per_minute_is_1(self):
            self.assertAlmostEqual(float(self.lr.rate_per_minute), 1.00, places=4)

        def test_labor_setup_cost_is_30(self):
            # 30 min * 1.00 EUR/min = 30.00
            self.assertAlmostEqual(float(self.op.labor_setup_cost()), 30.00, places=4)

        def test_labor_run_cost_per_unit_is_2(self):
            # 2 min * 1.00 EUR/min = 2.00
            self.assertAlmostEqual(float(self.op.labor_run_cost_per_unit()), 2.00, places=4)

        def test_labor_cost_batch_10(self):
            # 30 + (2 * 10) = 50.00
            self.assertAlmostEqual(float(self.op.labor_cost(batch_size=10)), 50.00, places=4)

        # --- Machine ---

        def test_machine_rate_per_minute_is_2(self):
            self.assertAlmostEqual(float(self.mc.rate_per_minute), 2.00, places=4)

        def test_machine_setup_cost_is_60(self):
            # 30 min * 2.00 EUR/min = 60.00
            self.assertAlmostEqual(float(self.op.machine_setup_cost()), 60.00, places=4)

        def test_machine_run_cost_per_unit_is_4(self):
            # 2 min * 2.00 EUR/min = 4.00
            self.assertAlmostEqual(float(self.op.machine_run_cost_per_unit()), 4.00, places=4)

        def test_machine_cost_batch_10(self):
            # 60 + (4 * 10) = 100.00
            self.assertAlmostEqual(float(self.op.machine_cost(batch_size=10)), 100.00, places=4)

        # --- Combined ---

        def test_total_cost_batch_10(self):
            # labor(10) + machine(10) = 50 + 100 = 150.00
            self.assertAlmostEqual(float(self.op.total_cost(batch_size=10)), 150.00, places=4)

        def test_per_unit_cost_batch_10(self):
            # 150.00 / 10 = 15.00
            self.assertAlmostEqual(float(self.op.per_unit_cost(batch_size=10)), 15.00, places=4)

        # --- CO2 ---

        def test_co2_batch_10(self):
            # total machine min = 30 + (2*10) = 50 min
            # CO2 = 50 * 0.001 = 0.05 kg
            self.assertAlmostEqual(float(self.op.co2_kg(batch_size=10)), 0.05, places=6)

        # --- Routing-level aggregation ---

        def test_routing_total_labor_cost(self):
            expected = float(self.op.labor_cost(10))
            self.assertAlmostEqual(float(self.routing.total_labor_cost()), expected, places=4)

        def test_routing_total_machine_cost(self):
            expected = float(self.op.machine_cost(10))
            self.assertAlmostEqual(float(self.routing.total_machine_cost()), expected, places=4)

        def test_routing_total_mfg_cost(self):
            self.assertAlmostEqual(
                float(self.routing.total_manufacturing_cost()),
                float(self.op.total_cost(10)),
                places=4
            )

        def test_routing_per_unit_cost(self):
            # batch=10, total=150, per_unit=15
            self.assertAlmostEqual(float(self.routing.per_unit_manufacturing_cost()), 15.00, places=4)

        def test_routing_co2(self):
            self.assertAlmostEqual(float(self.routing.total_co2_kg()), 0.05, places=6)


    class HierarchicalOperationsTest(TestCase):
        """Tests for parent/child operation hierarchy."""

        def setUp(self):
            from part.models import Part

            self.lr = LaborRate.objects.create(
                name="Hier Test Labor",
                hourly_rate=Decimal("60.00"),
            )
            self.part, _ = Part.objects.get_or_create(
                name="mBOM Hier Test",
                defaults={"assembly": True, "component": False}
            )
            self.routing = PartRouting.objects.create(
                part=self.part,
                standard_batch_size=1,
            )
            # Parent op: 10 min setup, 5 min/unit
            self.parent_op = RoutingOperation.objects.create(
                routing=self.routing,
                sequence_number="10",
                name="Parent Op",
                labor_rate=self.lr,
                setup_time_minutes=Decimal("10.00"),
                run_time_per_unit_minutes=Decimal("5.00"),
            )
            # Child op: 2 min setup, 1 min/unit
            self.child_op = RoutingOperation.objects.create(
                routing=self.routing,
                parent_operation=self.parent_op,
                sequence_number="10.1",
                name="Child Op",
                labor_rate=self.lr,
                setup_time_minutes=Decimal("2.00"),
                run_time_per_unit_minutes=Decimal("1.00"),
            )

        def tearDown(self):
            try:
                self.routing.delete()
                self.part.delete()
            except Exception:
                pass

        def test_child_has_parent(self):
            self.assertEqual(self.child_op.parent_operation, self.parent_op)

        def test_parent_has_child_in_sub_operations(self):
            self.assertIn(self.child_op, self.parent_op.sub_operations.all())

        def test_routing_aggregates_all_operations(self):
            # Routing total should include BOTH parent and child ops
            # Parent: setup(10) + run(5*1) = 15 labor
            # Child:  setup(2)  + run(1*1) = 3  labor
            # Total: 18
            # labor rate = 60/hr = 1/min
            expected = (10 + 5 + 2 + 1) * 1.0  # = 18.00 EUR
            self.assertAlmostEqual(float(self.routing.total_labor_cost(1)), expected, places=4)


    class ProcessTemplateTests(TestCase):
        """Tests for ProcessTemplate and step hierarchy."""

        def setUp(self):
            self.lr = LaborRate.objects.create(
                name="Tmpl Test Labor",
                hourly_rate=Decimal("60.00"),
            )
            self.template = ProcessTemplate.objects.create(
                name="Test Template",
                description="A test template",
            )
            self.step1 = ProcessTemplateStep.objects.create(
                template=self.template,
                sequence_number="10",
                name="Step 1",
                labor_rate=self.lr,
                setup_time_minutes=Decimal("5.00"),
                run_time_per_unit_minutes=Decimal("2.00"),
            )
            self.step1_1 = ProcessTemplateStep.objects.create(
                template=self.template,
                parent_step=self.step1,
                sequence_number="10.1",
                name="Step 1.1",
                labor_rate=self.lr,
                setup_time_minutes=Decimal("1.00"),
                run_time_per_unit_minutes=Decimal("0.50"),
            )

        def test_template_step_count(self):
            self.assertEqual(self.template.steps.count(), 2)

        def test_top_level_steps(self):
            top = self.template.steps.filter(parent_step__isnull=True)
            self.assertEqual(top.count(), 1)
            self.assertEqual(top.first(), self.step1)

        def test_sub_steps(self):
            self.assertEqual(self.step1.sub_steps.count(), 1)
            self.assertEqual(self.step1.sub_steps.first(), self.step1_1)

        def test_step_str(self):
            self.assertIn("10", str(self.step1))
            self.assertIn("Step 1", str(self.step1))


    class PricingEngineTests(TestCase):
        """Tests for the pricing engine (pricing.py)."""

        def setUp(self):
            from part.models import Part

            self.lr = LaborRate.objects.create(
                name="Pricing Test Labor",
                hourly_rate=Decimal("60.00"),
            )
            self.mc = MachineCenter.objects.create(
                name="Pricing Test Machine",
                hourly_rate=Decimal("120.00"),
                co2_factor_per_minute=Decimal("0.001"),
            )
            self.part, _ = Part.objects.get_or_create(
                name="mBOM Pricing Engine Test",
                defaults={"assembly": True, "component": False}
            )
            self.routing = PartRouting.objects.create(
                part=self.part,
                standard_batch_size=10,
            )
            RoutingOperation.objects.create(
                routing=self.routing,
                sequence_number="10",
                name="Test Op",
                labor_rate=self.lr,
                machine_center=self.mc,
                setup_time_minutes=Decimal("30.00"),
                run_time_per_unit_minutes=Decimal("2.00"),
            )

        def tearDown(self):
            try:
                self.routing.delete()
                self.part.delete()
            except Exception:
                pass

        def test_get_mbom_unit_cost_returns_dict(self):
            from inventree_mbom.pricing import get_mbom_unit_cost
            result = get_mbom_unit_cost(self.part, batch_size=10)
            self.assertTrue(result['has_routing'])
            self.assertIn('per_unit_mfg', result)
            self.assertIn('co2_kg', result)

        def test_get_mbom_unit_cost_values(self):
            from inventree_mbom.pricing import get_mbom_unit_cost
            result = get_mbom_unit_cost(self.part, batch_size=10)
            # labor: 50.00, machine: 100.00, total: 150.00, per_unit: 15.00
            self.assertAlmostEqual(float(result['mfg_cost']), 150.00, places=2)
            self.assertAlmostEqual(float(result['per_unit_mfg']), 15.00, places=2)

        def test_no_routing_returns_empty(self):
            from inventree_mbom.pricing import get_mbom_unit_cost
            from part.models import Part
            other_part, _ = Part.objects.get_or_create(
                name="mBOM No Routing Part",
                defaults={"assembly": True, "component": False}
            )
            result = get_mbom_unit_cost(other_part)
            self.assertFalse(result['has_routing'])
            self.assertEqual(result['per_unit_mfg'], Decimal('0.00'))
            other_part.delete()

        def test_get_assembly_full_cost(self):
            from inventree_mbom.pricing import get_assembly_full_cost
            result = get_assembly_full_cost(self.part, batch_size=10)
            self.assertIn('per_unit_total_min', result)
            self.assertIn('batch_size', result)
            self.assertEqual(result['batch_size'], 10)
            self.assertTrue(result['has_routing'])


except ImportError:
    pass  # Django not available in this context
