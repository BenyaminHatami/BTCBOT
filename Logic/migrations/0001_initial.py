# Generated by Django 5.1 on 2024-08-07 20:48

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Position',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('trace', models.TextField(blank=True, null=True)),
                ('pnl', models.DecimalField(blank=True, decimal_places=5, default=0, max_digits=10, null=True)),
                ('coin', models.CharField(choices=[(str, 'type'), ('BTCUSDT_SPBL', 'btc_spot'), ('BTCUSDT_UMCBL', 'btc_futures')], max_length=50)),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=10)),
                ('state', models.IntegerField(blank=True, choices=[(int, 'type'), (1, 'Active'), (2, 'Inactive'), (3, 'Pending')], null=True)),
                ('direction', models.CharField(choices=[(str, 'type'), ('long', 'long'), ('short', 'short')], max_length=50)),
                ('is_ever_updated', models.BooleanField(default=False)),
                ('number_of_openings', models.IntegerField(default=0)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Trader',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('trace', models.TextField(blank=True, null=True)),
                ('name', models.CharField(max_length=100)),
                ('api_key', models.CharField(max_length=100)),
                ('secret_key', models.CharField(max_length=100)),
                ('api_passphrase', models.CharField(max_length=100)),
                ('pnl', models.DecimalField(blank=True, decimal_places=5, default=0, max_digits=10, null=True)),
            ],
            options={
                'unique_together': {('name',)},
            },
        ),
        migrations.CreateModel(
            name='SLTPOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('trace', models.TextField(blank=True, null=True)),
                ('coin', models.CharField(choices=[(str, 'type'), ('BTCUSDT_SPBL', 'btc_spot'), ('BTCUSDT_UMCBL', 'btc_futures')], max_length=50)),
                ('quantity', models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ('plan_type', models.CharField(choices=[(str, 'type'), ('profit_plan', 'tp'), ('loss_plan', 'sl')], max_length=50)),
                ('trigger_price', models.DecimalField(blank=True, decimal_places=1, max_digits=10, null=True)),
                ('state', models.IntegerField(choices=[(int, 'type'), (1, 'Active'), (2, 'Inactive'), (3, 'Pending')])),
                ('remote_id', models.CharField(max_length=200)),
                ('position', models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, to='Logic.position')),
                ('trader', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='Logic.trader')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='PositionAction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('trace', models.TextField(blank=True, null=True)),
                ('action_side', models.CharField(choices=[(str, 'type'), ('open_long', 'open_long'), ('close_long', 'close_long'), ('open_short', 'open_short'), ('close_short', 'close_short'), ('unknown', 'unknown')], max_length=50)),
                ('price', models.DecimalField(decimal_places=1, max_digits=10)),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=10)),
                ('coin', models.CharField(choices=[(str, 'type'), ('BTCUSDT_SPBL', 'btc_spot'), ('BTCUSDT_UMCBL', 'btc_futures')], max_length=50)),
                ('remote_id', models.CharField(max_length=200)),
                ('profit', models.DecimalField(decimal_places=5, max_digits=10)),
                ('fee', models.DecimalField(decimal_places=5, default=0, max_digits=10)),
                ('position', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='Logic.position')),
                ('trader', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='Logic.trader')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='position',
            name='trader',
            field=models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='Logic.trader'),
        ),
    ]
