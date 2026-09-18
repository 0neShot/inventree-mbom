"""Tests for inventree-mbom models."""

from decimal import Decimal
import django
import os

# These tests are designed to run within a live InvenTree Django environment.
# Run via: python manage.py test inventree_mbom

try:
    from django.test import TestCase

    from inventree_mbom.models import (
        LaborRate,
        MachineCenter,
        ProcessTemplate,
        ProcessTemplateStep,
        PartRouting,
        RoutingOperation,
    )


    class LaborRateTests(TestCase):
        """Test LaborRate model."""

        def setUp(self):
            self.lr = LaborRate.objects.create(
                name="Test Assembler",
                hourly_rate=Decimal("30.00"),
                currency="EUR",
            )

        def test_rate_per_minute(self):
            expected = Decimal("30.00") / Decimal("60")
            self.assertAlmostEqual(float(self.lr.rate_per_minute), float(expected), places=6)

        def test_str(self):
            self.assertIn("Test Assembler", str(self.lr))


    class MachineCenterTests(TestCase):
        """Test MachineCenter model."""

        def setUp(self):
            self.mc = MachineCenter.objects.create(
                name="Test CNC",
                hourly_rate=Decimal("120.00"),
                currency="EUR",
                co2_factor_per_minute=Decimal("0.002"),
            )

        def test_rate_per_minute(self):
            expected = Decimal("120.00") / Decimal("60")
            self.assertAlmostEqual(float(self.mc.rate_per_minute), float(expected), places=4)

        def test_str(self):
            self.assertIn("Test CNC", str(self.mc))


    class RoutingCostTests(TestCase):
        """Test cost calculation on RoutingOperation."""

        def setUp(self):
            from part.models import Part

            self.lr = LaborRate.objects.create(
                name="Cost Test Labor",
                hourly_rate=Decimal("60.00"),
                currency="EUR",
            )
            self.mc = MachineCenter.objects.create(
                name="Cost Test Machine",
                hourly_rate=Decimal("120.00"),
                currency="EUR",
                co2_factor_per_minute=Decimal("0.001"),
            )
            # Get or create a test assembly part
            self.part, _ = Part.objects.get_or_create(
                name="mBOM Test Assembly",
                defaults={
                    "assembly": True,
                    "component": False,
                }
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
                setup_time_minutes=Decimal("30.00"),   # 30 min setup
                run_time_per_unit_minutes=Decimal("2.00"),  # 2 min/unit
            )

        def test_labor_rate_per_minute(self):
            # 60 EUR/hr -> 1.00 EUR/min
            self.assertAlmostEqual(float(self.lr.rate_per_minute), 1.00, places=4)

        def test_machine_rate_per_minute(self):
            # 120 EUR/hr -> 2.00 EUR/min
            self.assertAlmostEqual(float(self.mc.rate_per_minute), 2.00, places=4)

        def test_labor_setup_cost(self):
            # 30 min * 1.00 EUR/min = 30.00 EUR
            self.assertAlmostEqual(float(self.op.labor_setup_cost()), 30.00, places=4)

        def test_labor_run_cost_per_unit(self):
            # 2 min * 1.00 EUR/min = 2.00 EUR/unit
            self.assertAlmostEqual(float(self.op.labor_run_cost_per_unit()), 2.00, places=4)

        def test_labor_total_batch_10(self):
            # Setup 30 + Run (2 * 10) = 50.00 EUR
            self.assertAlmostEqual(float(self.op.labor_cost(batch_size=10)), 50.00, places=4)

        def test_machine_setup_cost(self):
            # 30 min * 2.00 EUR/min = 60.00 EUR
            self.assertAlmostEqual(float(self.op.machine_setup_cost()), 60.00, places=4)

        def test_machine_total_batch_10(self):
            # Setup 60 + Run (2*2*10=40) = 100.00 EUR
            self.assertAlmostEqual(float(self.op.machine_cost(batch_size=10)), 100.00, places=4)

        def test_per_unit_cost_batch_10(self):
            # (30+50+60+100) / 10 = 240 / 10 = 24.00 EUR/unit
            # Wait - total_cost for batch 10 = labor(10) + machine(10) = 50 + 100 = 150
            # per_unit = 150 / 10 = 15.00
            self.assertAlmostEqual(float(self.op.per_unit_cost(batch_size=10)), 15.00, places=4)

        def test_co2_batch_10(self):
            # total machine minutes = setup 30 + run (2*10=20) = 50 min
            # CO2 = 50 * 0.001 = 0.05 kg
            self.assertAlmostEqual(float(self.op.co2_kg(batch_size=10)), 0.05, places=6)

        def test_routing_total_costs(self):
            # Single operation routing
            expected_labor = float(self.op.labor_cost(10))
            expected_machine = float(self.op.machine_cost(10))
            self.assertAlmostEqual(
                float(self.routing.total_labor_cost()), expected_labor, places=4
            )
            self.assertAlmostEqual(
                float(self.routing.total_machine_cost()), expected_machine, places=4
            )

        def tearDown(self):
            self.routing.delete()
            self.part.delete()
            self.op  # already deleted via cascade


except ImportError:
    # Django not configured - skip
    pass
