from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('movies', '0001_initial')]
    operations = [
        migrations.AddField(model_name='seat', name='price', field=models.DecimalField(decimal_places=2, default=100, max_digits=8)),
        migrations.CreateModel(name='PaymentTransaction', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('seat_ids', models.JSONField(default=list)), ('amount_paise', models.PositiveIntegerField()),
            ('razorpay_order_id', models.CharField(max_length=100, unique=True)), ('razorpay_payment_id', models.CharField(blank=True, max_length=100)),
            ('status', models.CharField(choices=[('created','Created'),('paid','Paid'),('failed','Failed')], default='created', max_length=20)),
            ('created_at', models.DateTimeField(auto_now_add=True)), ('paid_at', models.DateTimeField(blank=True, null=True)),
            ('theater', models.ForeignKey(on_delete=models.deletion.CASCADE, to='movies.theater')),
            ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='payment_transactions', to='auth.user')),
        ]),
    ]
