"""Wiki filters. Query params are part of the API contract (section 4).

`search` has to reach into `aliases` / `signals`, which are JSONFields. Those
are cast to text and matched as substrings rather than using the JSON `contains`
lookup: `contains` means JSON containment (whole-element equality) and would
never match a user typing half a word, and its support varies by backend.
"""

from django.db.models import Q, TextField
from django.db.models.functions import Cast
from django_filters import rest_framework as filters

from .models import Concept, Entity


class EntityFilter(filters.FilterSet):
    search = filters.CharFilter(method="search_name_or_alias", label="按名称或别名搜索")

    class Meta:
        model = Entity
        fields = ["entity_type"]

    def search_name_or_alias(self, queryset, name, value):
        return queryset.annotate(aliases_text=Cast("aliases", TextField())).filter(
            Q(name__icontains=value) | Q(normalized_name__icontains=value) | Q(aliases_text__icontains=value)
        )


class ConceptFilter(filters.FilterSet):
    search = filters.CharFilter(method="search_name_or_signal", label="按名称或信号词搜索")

    class Meta:
        model = Concept
        fields = ["namespace"]

    def search_name_or_signal(self, queryset, name, value):
        return queryset.annotate(signals_text=Cast("signals", TextField())).filter(
            Q(name__icontains=value) | Q(signals_text__icontains=value)
        )
