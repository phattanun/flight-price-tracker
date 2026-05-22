"""Google Flights via fast-flights."""

from __future__ import annotations

from datetime import timedelta

from providers import BaseProvider, FareResult, RouteConfig, register_provider

try:
    from fast_flights import FlightQuery, Passengers, create_query, get_flights
    HAS_FF = True
except ImportError:
    HAS_FF = False


def fetch_google_flights(
    route: RouteConfig,
    *,
    airline_filter: str | None = None,
    provider_name: str = "google_flights",
) -> list[FareResult]:
    """Query Google Flights; optionally keep only fares matching airline_filter (substring)."""
    if not HAS_FF:
        raise ImportError("Install fast-flights: pip install faster-flights")

    fares: list[FareResult] = []
    d = route.date_range_start
    currency = route.currency.upper() if route.currency else ""
    needle = (airline_filter or "").lower()

    while d <= route.date_range_end:
        fq = FlightQuery(date=d.strftime("%Y-%m-%d"), from_airport=route.origin, to_airport=route.destination)
        pax = Passengers(adults=route.adults, children=route.children, infants_in_seat=route.infants)
        q = create_query(
            flights=[fq], trip="one-way", seat="economy", passengers=pax,
            currency=currency,
        )
        try:
            results = get_flights(q)
            for flight in results:
                if not flight.flights:
                    continue
                airline = ", ".join(flight.airlines) if flight.airlines else "Multiple"
                if needle and needle not in airline.lower():
                    continue
                dep = flight.flights[0].departure
                fd = dep.date  # (y, m, d)
                from datetime import date as date_cls
                flight_date = date_cls(fd[0], fd[1], fd[2])
                fares.append(FareResult(
                    airline=airline, origin=route.origin, destination=route.destination,
                    flight_date=flight_date, price=float(flight.price), currency=currency or "THB",
                    provider=provider_name,
                    flight_number=flight.flights[0].flight_number or None,
                    booking_url=q.url(),
                ))
        except Exception:
            pass
        d += timedelta(days=7)
    return fares


@register_provider
class GoogleFlightsProvider(BaseProvider):
    name = "google_flights"

    def search_fares(self, route: RouteConfig) -> list[FareResult]:
        return fetch_google_flights(route, provider_name=self.name)
