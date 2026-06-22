from django.views.generic import TemplateView

from rankings.services.ranking_service import RankingService


class RankingView(TemplateView):
    template_name = "rankings/list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = RankingService()
        context["ranking"] = service.get_ranking()
        return context
