# Generated for inventree_mbom

import django.core.validators
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "inventree_mbom",
            "0002_partrouting_updated_by_alter_laborrate_hourly_rate_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="partrouting",
            name="overhead_percent",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="General overhead percentage applied to labor and machine costs",
                max_digits=6,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                verbose_name="Overhead Percentage",
            ),
        ),
    ]
