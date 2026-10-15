"""The Marketplace is the main collaborator: it holds the loaded data and runs
the pipeline  filter (hard)  ->  rank (soft)  for one traveller request.
The CLI talks to this class and not to every module separately.
"""
from .filtering import FilterResult, filter_offers
from .validation import validate_request
from .exceptions import ValidationError
from .models import Company, Destination, Offer, RankedOffer, TravelRequest
from .ranking import rank_offers


class Marketplace:
    def __init__(self, companies: list[Company], destinations: list[Destination],
                 offers: list[Offer], profiles: dict[str, dict[str, float]]):
        self.companies = companies
        self.destinations = destinations
        self.offers = offers
        self.profiles = profiles          # profile name -> criterion weights

    def filter(self, request: TravelRequest) -> FilterResult:
        """Hard constraints only (no ranking). Also checks that the request makes sense."""
        validate_request(request, {d.name for d in self.destinations})
        return filter_offers(self.offers, request)

    def compare_profiles(self, request: TravelRequest, profile_names: list[str] | None = None
                         ) -> tuple[FilterResult, dict[str, list[RankedOffer]]]:
        """Filter ONCE, then rank the same offers with the weights of each profile."""
        names = profile_names if profile_names is not None else list(self.profiles)
        unknown = [n for n in names if n not in self.profiles]
        if unknown:
            raise ValidationError("unknown_profile", f"unknown profile '{unknown[0]}'")
        result = self.filter(request)
        return result, {n: rank_offers(result.kept, request, self.profiles[n]) for n in names}

    def search(self, request: TravelRequest,
               weights: dict | None = None) -> tuple[FilterResult, list[RankedOffer]]:
        """Apply hard constraints, then rank what is left with the profile's weights."""
        result = self.filter(request)
        if weights is None:
            if request.profile not in self.profiles:
                raise ValidationError("unknown_profile", f"unknown profile '{request.profile}'")
            weights = self.profiles[request.profile]
        return result, rank_offers(result.kept, request, weights)
