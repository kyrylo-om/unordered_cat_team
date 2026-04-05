from django.db import models
from django.core.validators import FileExtensionValidator

from .layout_parser import parse_dot_to_react_flow


class MapLayout(models.Model):
	name = models.CharField(max_length=120)
	dot_file = models.FileField(
		upload_to="map_layouts/",
		validators=[FileExtensionValidator(allowed_extensions=["dot"])],
	)
	parsed_layout = models.JSONField(default=dict, blank=True)
	is_active = models.BooleanField(default=True)
	parse_error = models.TextField(blank=True, default="")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-updated_at"]

	def __str__(self):
		return self.name

	def save(self, *args, **kwargs):
		previous_file_name = None
		if self.pk:
			previous = type(self).objects.filter(pk=self.pk).only("dot_file").first()
			if previous and previous.dot_file:
				previous_file_name = previous.dot_file.name

		super().save(*args, **kwargs)

		should_parse = (
			not self.parsed_layout
			or (self.dot_file and self.dot_file.name != previous_file_name)
		)

		updates = {}
		if should_parse:
			try:
				layout = parse_dot_to_react_flow(self.dot_file.path)
				updates["parsed_layout"] = layout
				updates["parse_error"] = ""
			except Exception as exc:
				updates["parsed_layout"] = {"nodes": [], "edges": []}
				updates["parse_error"] = str(exc)

		if self.is_active:
			type(self).objects.exclude(pk=self.pk).filter(is_active=True).update(
				is_active=False
			)

		if updates:
			type(self).objects.filter(pk=self.pk).update(**updates)
			for key, value in updates.items():
				setattr(self, key, value)
