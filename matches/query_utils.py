from django.db.models import Case, IntegerField, Value, When


def order_with_finished_last(
    queryset,
    *order_fields,
    finished_field="finished",
    live_status_field="live_status",
    annotation_name="finished_sort",
):
    """Order querysets with unfinished/live matches first and finished matches last."""
    return queryset.annotate(
        **{
            annotation_name: Case(
                When(**{finished_field: True}, then=Value(1)),
                When(**{live_status_field: "FT"}, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        }
    ).order_by(annotation_name, *order_fields)

