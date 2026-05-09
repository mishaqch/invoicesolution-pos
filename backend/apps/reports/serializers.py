"""Serializers for the reports API.

Most reports return ad-hoc rows shaped by their `columns`. The wire
format is { columns, rows, totals, chart, row_count, truncated, freshness }
so the admin UI can render any report uniformly.
"""

from __future__ import annotations

from rest_framework import serializers

from .models import ReportFavorite, ReportRun


class ReportFavoriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportFavorite
        fields = [
            "id", "report_name", "label", "filters_json", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ReportRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportRun
        fields = [
            "id", "report_name", "filters_json", "export_format",
            "status", "error", "output_path", "row_count",
            "started_at", "finished_at", "created_at",
        ]
        read_only_fields = [
            "id", "status", "error", "output_path", "row_count",
            "started_at", "finished_at", "created_at",
        ]
