"""Google Flights via fast-flights."""

from __future__ import annotations

import sys
from datetime import date as date_cls, timedelta

from providers import BaseProvider, FareResult, RouteConfig, register_provider

try:
    from fast_flights import FlightQuery, Passengers, ShoppingOptions, create_query, get_flights
    HAS_FF = True
    SHOPPING_CHEAPEST = ShoppingOptions(ranking_mode="cheapest", result_sort="price")
except ImportError:
    HAS_FF = False
    SHOPPING_CHEAPEST = None


def _simple_date_to_date(d: tuple[int, int, int] | list[int]) -> date_cls:
    return date_cls(d[0], d[1], d[2])


def _outbound_departure(legs: list, origin: str, fallback: date_cls) -> date_cls:
    for leg in legs:
        if leg.from_airport.code == origin:
            return _simple_date_to_date(leg.departure.date)
    return fallback


def _return_departure(legs: list, destination: str, origin: str, fallback: date_cls) -> date_cls:
    for leg in legs:
        if leg.from_airport.code == destination and leg.to_airport.code == origin:
            return _simple_date_to_date(leg.departure.date)
    return fallback


def _flight_to_fare(
    flight: object,
    *,
    route: RouteConfig,
    currency: str,
    provider_name: str,
    booking_url: str,
    trip_days: int | None = None,
    return_date: date_cls | None = None,
) -> FareResult:
    dep = flight.flights[0].departure  # type: ignore[attr-defined]
    fd = _simple_date_to_date(dep.date)
    airline = ", ".join(flight.airlines) if flight.airlines else "Multiple"  # type: ignore[attr-defined]
    return FareResult(
        airline=airline,
        origin=route.origin,
        destination=route.destination,
        flight_date=fd,
        price=float(flight.price),  # type: ignore[attr-defined]
        currency=currency or "THB",
        provider=provider_name,
        flight_number=flight.flights[0].flight_number or None,  # type: ignore[attr-defined]
        booking_url=booking_url,
        return_date=return_date,
        trip_days=trip_days,
    )


def fetch_google_flights(
    route: RouteConfig,
    *,
    airline_filter: str | None = None,
    provider_name: str = "google_flights",
) -> list[FareResult]:
    """Query Google Flights one-way; optionally keep only fares matching airline_filter (substring)."""
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
            results = get_flights(q, shopping=SHOPPING_CHEAPEST)
            for flight in results:
                if not flight.flights:
                    continue
                airline = ", ".join(flight.airlines) if flight.airlines else "Multiple"
                if needle and needle not in airline.lower():
                    continue
                fares.append(_flight_to_fare(
                    flight, route=route, currency=currency, provider_name=provider_name, booking_url=q.url()
                ))
        except Exception as exc:
            print(
                f"  [google_flights] {route.origin}->{route.destination} {d}: {exc}",
                file=sys.stderr,
            )
        d += timedelta(days=1)
    return fares


def fetch_google_flights_round_trip(
    route: RouteConfig,
    *,
    provider_name: str = "google_flights",
) -> list[FareResult]:
    """Search round-trip fares for each outbound date and trip length in range."""
    if not HAS_FF:
        raise ImportError("Install fast-flights: pip install faster-flights")
    if not route.is_round_trip or route.trip_duration_min is None or route.trip_duration_max is None:
        raise ValueError("fetch_google_flights_round_trip requires a round_trip RouteConfig")

    fares: list[FareResult] = []
    currency = route.currency.upper() if route.currency else ""
    pax = Passengers(adults=route.adults, children=route.children, infants_in_seat=route.infants)
    outbound = route.date_range_start

    while outbound <= route.date_range_end:
        for trip_days in range(route.trip_duration_min, route.trip_duration_max + 1):
            return_date = outbound + timedelta(days=trip_days)
            fq_out = FlightQuery(
                date=outbound.strftime("%Y-%m-%d"),
                from_airport=route.origin,
                to_airport=route.destination,
            )
            fq_ret = FlightQuery(
                date=return_date.strftime("%Y-%m-%d"),
                from_airport=route.destination,
                to_airport=route.origin,
            )
            q = create_query(
                flights=[fq_out, fq_ret],
                trip="round-trip",
                seat="economy",
                passengers=pax,
                currency=currency,
            )
            try:
                results = get_flights(q, shopping=SHOPPING_CHEAPEST)
                best: FareResult | None = None
                for flight in results:
                    if not flight.flights:
                        continue
                    legs = flight.flights
                    out_dep = _outbound_departure(legs, route.origin, outbound)
                    ret_dep = _return_departure(legs, route.destination, route.origin, return_date)
                    stay_days = (ret_dep - out_dep).days
                    if stay_days < 0:
                        stay_days = trip_days
                    candidate = _flight_to_fare(
                        flight,
                        route=route,
                        currency=currency,
                        provider_name=provider_name,
                        booking_url=q.url(),
                        trip_days=stay_days,
                        return_date=ret_dep,
                    )
                    candidate.flight_date = out_dep
                    if best is None or candidate.price < best.price:
                        best = candidate
                if best is not None:
                    fares.append(best)
            except Exception as exc:
                print(
                    f"  [google_flights] RT {route.origin}<->{route.destination} "
                    f"{outbound} +{trip_days}d: {exc}",
                    file=sys.stderr,
                )
        outbound += timedelta(days=1)
    return fares


@register_provider
class GoogleFlightsProvider(BaseProvider):
    name = "google_flights"

    def search_fares(self, route: RouteConfig) -> list[FareResult]:
        if route.is_round_trip:
            return fetch_google_flights_round_trip(route, provider_name=self.name)
        return fetch_google_flights(route, provider_name=self.name)
