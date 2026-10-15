"""Compare traveller profiles on the SAME request and the SAME offers (Section 6).

Only the weights differ between the profiles, so any difference in the winner is
caused by the weights alone.
"""
from .models import RankedOffer


def winner_rank_matrix(rankings: dict[str, list[RankedOffer]]
                       ) -> list[tuple[RankedOffer, dict[str, int]]]:
    """One row per DISTINCT winning offer (in profile order): the winner as ranked under the
    first profile it won, and its rank under every profile."""
    rows: list[tuple[RankedOffer, dict[str, int]]] = []
    seen: set[str] = set()
    for ranked in rankings.values():
        if not ranked or ranked[0].offer.offer_id in seen:
            continue
        winner = ranked[0]
        seen.add(winner.offer.offer_id)
        ranks = {}
        for profile, other in rankings.items():
            ranks[profile] = next((r.rank for r in other if r.offer.offer_id == winner.offer.offer_id), 0)
        rows.append((winner, ranks))
    return rows
