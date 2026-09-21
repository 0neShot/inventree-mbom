"""Management command: create a test dataset for the inventree-mbom plugin.

Usage (inside InvenTree environment):
    python manage.py mbom_create_test_data

Creates:
    - 2 LaborRates (Assembler @ 28 EUR/hr, Engineer @ 95 EUR/hr)
    - 2 MachineCenters (CNC Mill @ 120 EUR/hr, Reflow Oven @ 35 EUR/hr)
    - 1 ProcessTemplate (SMT Assembly Standard) with 3 hierarchical steps
    - Applies the template to a test assembly part (created if needed)

After running, navigate to the test assembly in InvenTree to verify the
mBOM panel appears with cost calculations.
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Create test data for the inventree-mbom plugin"

    @transaction.atomic
    def handle(self, *args, **options):
        from inventree_mbom.models import (
            LaborRate,
            MachineCenter,
            ProcessTemplate,
            ProcessTemplateStep,
            PartRouting,
            RoutingOperation,
        )

        self.stdout.write(
            self.style.MIGRATE_HEADING("=== inventree-mbom Test Data Setup ===")
        )

        # ----------------------------------------------------------------
        # 1. Labor Rates
        # ----------------------------------------------------------------
        self.stdout.write("\n[1/5] Creating Labor Rates...")

        assembler, created = LaborRate.objects.get_or_create(
            name="Assembler",
            defaults={
                "description": "PCB assembly and soldering technician",
                "hourly_rate": Decimal("28.00"),
                "currency": "EUR",
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Exists'}: {assembler}")

        engineer, created = LaborRate.objects.get_or_create(
            name="Engineer",
            defaults={
                "description": "Process and quality engineer",
                "hourly_rate": Decimal("95.00"),
                "currency": "EUR",
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Exists'}: {engineer}")

        # ----------------------------------------------------------------
        # 2. Machine Centers
        # ----------------------------------------------------------------
        self.stdout.write("\n[2/5] Creating Machine Centers...")

        cnc, created = MachineCenter.objects.get_or_create(
            name="CNC Mill",
            defaults={
                "description": "3-axis CNC milling machine",
                "hourly_rate": Decimal("120.00"),
                "currency": "EUR",
                "co2_factor_per_minute": Decimal("0.003500"),
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Exists'}: {cnc}")

        reflow, created = MachineCenter.objects.get_or_create(
            name="Reflow Oven",
            defaults={
                "description": "SMT reflow soldering oven",
                "hourly_rate": Decimal("35.00"),
                "currency": "EUR",
                "co2_factor_per_minute": Decimal("0.001200"),
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Exists'}: {reflow}")

        # ----------------------------------------------------------------
        # 3. Process Template
        # ----------------------------------------------------------------
        self.stdout.write("\n[3/5] Creating Process Template...")

        template, created = ProcessTemplate.objects.get_or_create(
            name="SMT Assembly Standard",
            defaults={"description": "Standard SMT PCB assembly process"},
        )
        self.stdout.write(f"  {'Created' if created else 'Exists'}: {template}")

        if created:
            # Parent step: Op 10 - SMT Assembly
            op10 = ProcessTemplateStep.objects.create(
                template=template,
                sequence_number="10",
                name="SMT Assembly",
                description="Full SMT placement and soldering",
                labor_rate=assembler,
                machine_center=reflow,
                setup_time_minutes=Decimal("30.00"),
                run_time_per_unit_minutes=Decimal("3.00"),
            )

            # Sub-steps under Op 10
            ProcessTemplateStep.objects.create(
                template=template,
                parent_step=op10,
                sequence_number="10.1",
                name="Stencil Paste Application",
                labor_rate=assembler,
                setup_time_minutes=Decimal("10.00"),
                run_time_per_unit_minutes=Decimal("0.50"),
            )
            ProcessTemplateStep.objects.create(
                template=template,
                parent_step=op10,
                sequence_number="10.2",
                name="Pick & Place",
                labor_rate=assembler,
                machine_center=reflow,
                setup_time_minutes=Decimal("5.00"),
                run_time_per_unit_minutes=Decimal("1.50"),
            )
            ProcessTemplateStep.objects.create(
                template=template,
                parent_step=op10,
                sequence_number="10.3",
                name="Reflow Soldering",
                machine_center=reflow,
                setup_time_minutes=Decimal("0.00"),
                run_time_per_unit_minutes=Decimal("0.80"),
            )

            # Parent step: Op 20 - Final Inspection
            ProcessTemplateStep.objects.create(
                template=template,
                sequence_number="20",
                name="Final Inspection & Test",
                description="AOI and functional test",
                labor_rate=engineer,
                setup_time_minutes=Decimal("15.00"),
                run_time_per_unit_minutes=Decimal("5.00"),
            )

            self.stdout.write(
                f"  Created 5 template steps (Op 10 with 3 sub-steps + Op 20)"
            )
        else:
            self.stdout.write(
                f"  Template steps already exist ({template.steps.count()} steps)"
            )

        # ----------------------------------------------------------------
        # 4. Test Assembly Part
        # ----------------------------------------------------------------
        self.stdout.write("\n[4/5] Creating Test Assembly Part...")

        try:
            from part.models import Part, PartCategory

            # Get or create a test category
            category, _ = PartCategory.objects.get_or_create(
                name="mBOM Test Category",
                defaults={"description": "Test category for inventree-mbom plugin"},
            )

            test_part, created = Part.objects.get_or_create(
                name="mBOM Test Assembly PCB",
                defaults={
                    "description": "Test assembly for the inventree-mbom plugin",
                    "assembly": True,
                    "component": False,
                    "category": category,
                    "IPN": "TEST-MBOM-001",
                },
            )
            self.stdout.write(
                f"  {'Created' if created else 'Exists'}: {test_part} (pk={test_part.pk})"
            )

            # ----------------------------------------------------------------
            # 5. Apply Template to Part
            # ----------------------------------------------------------------
            self.stdout.write("\n[5/5] Applying template to test assembly...")

            routing, routing_created = PartRouting.objects.get_or_create(
                part=test_part,
                defaults={
                    "source_template": template,
                    "standard_batch_size": 50,
                    "notes": "Test routing created by mbom_create_test_data command",
                },
            )

            if routing_created:
                # Deep-copy template steps to routing operations
                def copy_steps(steps, parent_op=None):
                    for step in steps.order_by("sequence_number"):
                        op = RoutingOperation.objects.create(
                            routing=routing,
                            parent_operation=parent_op,
                            sequence_number=step.sequence_number,
                            name=step.name,
                            description=step.description or "",
                            labor_rate=step.labor_rate,
                            machine_center=step.machine_center,
                            setup_time_minutes=step.setup_time_minutes,
                            run_time_per_unit_minutes=step.run_time_per_unit_minutes,
                        )
                        copy_steps(step.sub_steps.all(), parent_op=op)

                copy_steps(template.steps.filter(parent_step__isnull=True))
                op_count = routing.operations.count()
                self.stdout.write(
                    f"  Routing created with {op_count} operations (batch=50)"
                )
            else:
                self.stdout.write(f"  Routing already exists (pk={routing.pk})")

            # ----------------------------------------------------------------
            # 6. Print cost summary
            # ----------------------------------------------------------------
            self.stdout.write(
                self.style.MIGRATE_HEADING("\n=== Cost Summary (batch=50) ===")
            )
            total_labor = routing.total_labor_cost(50)
            total_machine = routing.total_machine_cost(50)
            total_mfg = routing.total_manufacturing_cost(50)
            per_unit = routing.per_unit_manufacturing_cost()
            co2 = routing.total_co2_kg(50)

            self.stdout.write(f"  Labor cost (batch 50):    {total_labor:.4f} EUR")
            self.stdout.write(f"  Machine cost (batch 50):  {total_machine:.4f} EUR")
            self.stdout.write(f"  Total mfg cost:           {total_mfg:.4f} EUR")
            self.stdout.write(f"  Per-unit mfg cost:        {per_unit:.4f} EUR")
            self.stdout.write(f"  CO2 estimate (batch):     {co2:.4f} kg")

            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ Test data ready! Navigate to part pk={test_part.pk} "
                    f"at http://127.0.0.1:8000/web/part/{test_part.pk}/ "
                    f"to see the mBOM tab."
                )
            )

        except ImportError:
            self.stdout.write(
                self.style.WARNING(
                    "  Could not import InvenTree Part model. "
                    "Run this command from inside the InvenTree environment."
                )
            )
