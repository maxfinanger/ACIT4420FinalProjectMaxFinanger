"""The Marketplace is the main collaborator: it holds the loaded data and runs
the pipeline  filter (hard)  ->  rank (soft)  for one traveller request.
The CLI talks to this class and not to every module separately.
"""
from .filtering import FilterResult, filter_offers
from .models import Company, Destination, Offer, RankedOffer, TravelRequest
from .ranking import rank_offers


class Marketplace:
    def __init__(self, companies: list[Company], destinations: list[Destination],
                 offers: list[Offer], profiles: dict[str, dict[str, float]]):
        self.companies = companies
        self.destinations = destinations
        self.offers = offers
        self.profiles = profiles          # profile name -> criterion weights

    def search(self, request: TravelRequest,
               weights: dict | None = None) -> tuple[FilterResult, list[RankedOffer]]:
        """Apply hard constraints, then rank what is left with the profile's weights."""
        result = filter_offers(self.offers, request)
        weights = weights or self.profiles[request.profile]
        return result, rank_offers(result.kept, request, weights)
