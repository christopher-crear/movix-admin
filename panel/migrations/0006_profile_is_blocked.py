from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("panel", "0005_driverinboxmessage_driverinvoice_paymentbankaccount")]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="is_blocked",
            field=models.BooleanField(default=False),
        ),
    ]
