"""Everything the program prints about offers: load summary, ranking, recommendation and
profile comparison. Used by both the command-line options (cli.py) and the interactive
menu (interactive.py), so the two always show the same thing.
"""
from .comparison import winner_rank_matrix
from .explain import explain_top_offer
from .filtering import hard_constraint_lines, soft_preference_lines
from .marketplace import Marketplace
from .models import RankedOffer, TravelRequest
from .ranking import influence_share

MAX_REJECTED_SHOWN = 25


def print_load_summary(companies, destinations, profiles, result, path, service) -> None:
    print("=== BusBidder Spain ===")
    print(f"Companies    : {len(companies)}")
    print(f"Destinations : {len(destinations)}")
    print(f"Profiles     : {', '.join(profiles)}")
    print(f"Offers       : {len(result.offers)} loaded, {len(result.rejected)} rejected ({path})")
    print(f"Bookings     : {len(service.load())} saved ({service.store_path})")
    if result.rejected:
        print("\nRejected records (details in logs/busbidder.log):")
        for rec in result.rejected[:MAX_REJECTED_SHOWN]:
            print(f"  row {rec.row:>3}  {rec.offer_id:<9} {rec.category}: {rec.message}")
        if len(result.rejected) > MAX_REJECTED_SHOWN:
            print(f"  ... and {len(result.rejected) - MAX_REJECTED_SHOWN} more")


def duration_text(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}"


def print_ranking(ranked: list[RankedOffer], weights: dict, top: int) -> None:
    names = list(weights)
    print(f"\nRANKING ({len(ranked)} offers, best first). Scores are 0-100, higher is better; "
          "price, duration and\nemissions are scored relative to these offers, see docs/scoring.md.")
    head = (f"{'#':>3}  {'Offer':<8} {'Company':<15} {'Departure':<12} {'EUR':>6} {'Dur':>6} "
            f"{'Tr':>2} {'Fare':<8}")
    head += " |" + "".join(f" {n[:6]:>6}" for n in names) + " | TOTAL"
    print(head)
    for r in ranked[:top]:
        o = r.offer
        row = (f"{r.rank:>3}  {o.offer_id:<8} {o.company:<15} "
               f"{o.travel_date:%d %b} {o.departure_time:%H:%M} {o.price:>6.2f} "
               f"{duration_text(o.duration_minutes):>6} {o.transfers:>2} {o.fare.fare_type:<8}")
        row += " |" + "".join(f" {r.criterion_scores[n]:>6.1f}" for n in names)
        row += f" | {r.total_score:>5.1f}" + ("  (tie-break)" if r.tie_broken else "")
        print(row)
    if len(ranked) > top:
        print(f"... {len(ranked) - top} more offers not shown (use --top)")
    shares = influence_share(ranked, weights)
    print("\nWeight vs. real influence on the order (weight x spread of the scores):")
    for n in names:
        print(f"  {n:<12} weight {weights[n]*100:>3.0f}%   influence {shares[n]*100:>3.0f}%")


def print_search(request: TravelRequest, weights: dict, marketplace: Marketplace,
                  top: int) -> list:
    label = "custom weights" if request.profile == "(custom)" else f"profile {request.profile}"
    print(f"\nRequest: Madrid to {request.destination}, "
          f"{request.date_from} to {request.date_to}, {label}")
    print("\nHARD constraints (an offer that breaks one is removed before ranking):")
    for line in hard_constraint_lines(request):
        print(f"  - {line}")
    print("\nSOFT preferences (only affect the score, never remove an offer):")
    for line in soft_preference_lines(request, weights):
        print(f"  - {line}")
    print("  (price is both: the budget is hard, and within it a lower price scores higher)\n")

    result, ranked = marketplace.search(request, weights)
    for line in result.report_lines():
        print(line)
    if ranked:
        print_ranking(ranked, weights, top)
        print("\nRECOMMENDATION")
        print(explain_top_offer(ranked, request, weights).text())
    return ranked


def print_compare(request: TravelRequest, marketplace: Marketplace) -> None:
    print(f"\nRequest: Madrid to {request.destination}, "
          f"{request.date_from} to {request.date_to}, preferred departure "
          f"{request.preferred_departure:%H:%M}")
    print("\nHARD constraints (the same for every profile):")
    for line in hard_constraint_lines(request):
        print(f"  - {line}")
    print()
    result, rankings = marketplace.compare_profiles(request)
    for line in result.report_lines():
        print(line)
    if not result.kept:
        return
    print(f"\nPROFILE COMPARISON: the same {len(result.kept)} offers, only the weights change")
    print(f"{'Profile':<20} {'Winner':<8} {'Company':<15} {'Departure':<12} {'EUR':>6} {'Dur':>6} "
          f"{'Fare':<8} {'Total':>5}  Runner-up")
    for name, ranked in rankings.items():
        top, second = ranked[0], (ranked[1] if len(ranked) > 1 else None)
        o = top.offer
        print(f"{name:<20} {o.offer_id:<8} {o.company:<15} {o.travel_date:%d %b} {o.departure_time:%H:%M} "
              f"{o.price:>6.2f} {duration_text(o.duration_minutes):>6} {o.fare.fare_type:<8} "
              f"{top.total_score:>5.1f}  " + (f"{second.offer.offer_id} ({second.total_score:.1f})" if second else "-"))
    matrix = winner_rank_matrix(rankings)
    print("\nRank of each winner under every profile (1 = recommended):")
    print(f"{'Winner':<24}" + "".join(f"{n[:12]:>14}" for n in rankings))
    for winner, ranks in matrix:
        print(f"{winner.offer.offer_id + ' ' + winner.offer.company:<24}"
              + "".join(f"{ranks[n]:>14}" for n in rankings))
    if len(matrix) == 1:
        print("\nAll profiles recommend the same offer for this request.")
    else:
        print(f"\n{len(matrix)} different winners from "
              f"{len({w.offer.company for w, _ in matrix})} company/companies. "
              "The offers are the same, so only the weights make the difference.")
