# Generated by Django 3.2.7 on 2021-10-21 05:42

from django.db import migrations


class Migration(migrations.Migration):
	dependencies = [
		('mln', '0026_messagebody_type'),
	]

	operations = [
		migrations.RenameModel(
			old_name='ModuleYieldInfo',
			new_name='ModuleHarvestYield',
		),
	]
