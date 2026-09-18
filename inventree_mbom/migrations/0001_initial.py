"""Initial database migration for the inventree-mbom plugin.

Creates:
  - LaborRate
  - MachineCenter
  - ProcessTemplate
  - ProcessTemplateStep
  - PartRouting
  - RoutingOperation
"""

import decimal
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("part", "0001_initial"),  # Reference InvenTree Part model
    ]

    operations = [
        # LaborRate
        migrations.CreateModel(
            name="LaborRate",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Labor classification name (e.g. Assembler, Engineer)", max_length=100, unique=True, verbose_name="Name")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                ("hourly_rate", models.DecimalField(decimal_places=4, max_digits=12, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.00"))], verbose_name="Hourly Rate")),
                ("currency", models.CharField(default="EUR", max_length=10, verbose_name="Currency")),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Labor Rate", "verbose_name_plural": "Labor Rates", "ordering": ["name"], "app_label": "inventree_mbom"},
        ),
        # MachineCenter
        migrations.CreateModel(
            name="MachineCenter",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Machine center name", max_length=100, unique=True, verbose_name="Name")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                ("hourly_rate", models.DecimalField(decimal_places=4, max_digits=12, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.00"))], verbose_name="Hourly Rate")),
                ("currency", models.CharField(default="EUR", max_length=10, verbose_name="Currency")),
                ("co2_factor_per_minute", models.DecimalField(decimal_places=6, default=decimal.Decimal("0.000000"), max_digits=10, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.00"))], verbose_name="CO\u2082 Factor (kg/min)")),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Machine Center", "verbose_name_plural": "Machine Centers", "ordering": ["name"], "app_label": "inventree_mbom"},
        ),
        # ProcessTemplate
        migrations.CreateModel(
            name="ProcessTemplate",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, unique=True, verbose_name="Template Name")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Process Template", "verbose_name_plural": "Process Templates", "ordering": ["name"], "app_label": "inventree_mbom"},
        ),
        # ProcessTemplateStep
        migrations.CreateModel(
            name="ProcessTemplateStep",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="steps", to="inventree_mbom.processtemplate", verbose_name="Process Template")),
                ("parent_step", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="sub_steps", to="inventree_mbom.processtemplatestep", verbose_name="Parent Step")),
                ("sequence_number", models.CharField(help_text="Operation sequence (e.g. 10, 10.1, 20)", max_length=20, verbose_name="Sequence Number")),
                ("name", models.CharField(max_length=200, verbose_name="Step Name")),
                ("description", models.TextField(blank=True, verbose_name="Description / Tool Notes")),
                ("labor_rate", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="template_steps", to="inventree_mbom.laborrate", verbose_name="Labor Rate")),
                ("machine_center", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="template_steps", to="inventree_mbom.machinecenter", verbose_name="Machine Center")),
                ("setup_time_minutes", models.DecimalField(decimal_places=4, default=decimal.Decimal("0.0000"), max_digits=10, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.00"))], verbose_name="Setup Time (min)")),
                ("run_time_per_unit_minutes", models.DecimalField(decimal_places=4, default=decimal.Decimal("0.0000"), max_digits=10, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.00"))], verbose_name="Run Time per Unit (min)")),
            ],
            options={"verbose_name": "Process Template Step", "verbose_name_plural": "Process Template Steps", "ordering": ["template", "sequence_number"], "app_label": "inventree_mbom"},
        ),
        # PartRouting
        migrations.CreateModel(
            name="PartRouting",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("part", models.OneToOneField(limit_choices_to={"assembly": True}, on_delete=django.db.models.deletion.CASCADE, related_name="mbom_routing", to="part.part", verbose_name="Part")),
                ("source_template", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="applied_routings", to="inventree_mbom.processtemplate", verbose_name="Source Template")),
                ("standard_batch_size", models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)], verbose_name="Standard Batch Size")),
                ("notes", models.TextField(blank=True, verbose_name="Notes")),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Part Routing", "verbose_name_plural": "Part Routings", "app_label": "inventree_mbom"},
        ),
        # RoutingOperation
        migrations.CreateModel(
            name="RoutingOperation",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("routing", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="operations", to="inventree_mbom.partrouting", verbose_name="Part Routing")),
                ("parent_operation", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="sub_operations", to="inventree_mbom.routingoperation", verbose_name="Parent Operation")),
                ("sequence_number", models.CharField(help_text="e.g. 10, 10.1, 10.2, 20", max_length=20, verbose_name="Sequence")),
                ("name", models.CharField(max_length=200, verbose_name="Operation Name")),
                ("description", models.TextField(blank=True, verbose_name="Description / Tool Notes")),
                ("labor_rate", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="routing_operations", to="inventree_mbom.laborrate", verbose_name="Labor Rate")),
                ("machine_center", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="routing_operations", to="inventree_mbom.machinecenter", verbose_name="Machine Center")),
                ("setup_time_minutes", models.DecimalField(decimal_places=4, default=decimal.Decimal("0.0000"), max_digits=10, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.00"))], verbose_name="Setup Time (min)")),
                ("run_time_per_unit_minutes", models.DecimalField(decimal_places=4, default=decimal.Decimal("0.0000"), max_digits=10, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.00"))], verbose_name="Run Time per Unit (min)")),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
            ],
            options={"verbose_name": "Routing Operation", "verbose_name_plural": "Routing Operations", "ordering": ["routing", "sequence_number"], "app_label": "inventree_mbom"},
        ),
    ]
