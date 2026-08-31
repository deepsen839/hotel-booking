from itertools import combinations_with_replacement
from typing import Any, Dict, List

from app.models.schemas import (
    BookingState,
    RecommendedRoom,
    RoomRecommendation,
)


class RecommendationService:
    """
    Generates and ranks hotel room combinations.

    All room information and prices are received from inventory.json
    through InventoryService.
    """

    def __init__(self, inventory_service) -> None:
        self.inventory_service = inventory_service

    def get_recommendations(
        self,
        state: BookingState,
        nights: int
    ) -> List[RoomRecommendation]:
        """
        Generate at most 3 ranked room combinations.
        """

        total_guests = self._get_total_guests(state)

        if total_guests <= 0 or nights <= 0:
            return []

        available_rooms = (
            self.inventory_service.get_rooms_by_ac_preference(
                state.ac_preference
            )
        )

        if not available_rooms:
            return []

        room_counts = self._get_room_counts_to_try(
            state=state,
            total_guests=total_guests,
            available_rooms=available_rooms
        )

        all_combinations = []

        for room_count in room_counts:
            combinations = self._generate_combinations(
                rooms=available_rooms,
                room_count=room_count,
                total_guests=total_guests,
                nights=nights
            )

            all_combinations.extend(combinations)

        ranked_combinations = self._rank_combinations(
            all_combinations
        )

        return ranked_combinations[:3]

    def _get_total_guests(
        self,
        state: BookingState
    ) -> int:
        """
        Calculate the total number of guests.

        Adults and children are both considered when checking
        maximum room occupancy.
        """

        adults = state.adults or 0
        children = state.children or 0

        return adults + children

    def _get_room_counts_to_try(
        self,
        state: BookingState,
        total_guests: int,
        available_rooms: List[Dict[str, Any]]
    ) -> List[int]:
        """
        Determine how many rooms should be considered.

        If the guest explicitly requested a number of rooms,
        use exactly that number.

        Otherwise, try a reasonable range of room counts.
        """

        if state.rooms_requested is not None:
            return [state.rooms_requested]

        maximum_capacity = max(
            room["max_occupancy"]
            for room in available_rooms
        )

        minimum_rooms = max(
            1,
            (total_guests + maximum_capacity - 1)
            // maximum_capacity
        )

        # We try a few additional room counts so the guest can
        # receive alternative combinations.
        maximum_rooms = min(
            minimum_rooms + 2,
            total_guests
        )

        return list(
            range(
                minimum_rooms,
                maximum_rooms + 1
            )
        )

    def _generate_combinations(
        self,
        rooms: List[Dict[str, Any]],
        room_count: int,
        total_guests: int,
        nights: int
    ) -> List[RoomRecommendation]:
        """
        Generate all valid combinations for a specific number of rooms.
        """

        recommendations = []

        room_combinations = combinations_with_replacement(
            rooms,
            room_count
        )

        for combination in room_combinations:
            recommendation = self._build_recommendation(
                combination=list(combination),
                total_guests=total_guests,
                nights=nights
            )

            if recommendation is not None:
                recommendations.append(recommendation)

        return recommendations

    def _build_recommendation(
        self,
        combination: List[Dict[str, Any]],
        total_guests: int,
        nights: int
    ) -> RoomRecommendation | None:
        """
        Build one recommendation.

        A combination is valid only if its maximum occupancy
        can accommodate all guests.
        """

        total_max_capacity = sum(
            room["max_occupancy"]
            for room in combination
        )

        if total_max_capacity < total_guests:
            return None

        total_base_capacity = sum(
            room["base_occupancy"]
            for room in combination
        )

        extra_guests = max(
            0,
            total_guests - total_base_capacity
        )

        extra_bed_distribution = self._distribute_extra_beds(
            combination=combination,
            extra_guests=extra_guests
        )

        if extra_bed_distribution is None:
            return None

        room_summary = self._build_room_summary(
            combination=combination,
            extra_bed_distribution=extra_bed_distribution
        )

        total_extra_beds = sum(
            extra_bed_distribution
        )

        total_price = self._calculate_total_price(
            combination=combination,
            extra_bed_distribution=extra_bed_distribution,
            nights=nights
        )

        currency = self.inventory_service.get_currency()

        return RoomRecommendation(
            rank=0,
            rooms=room_summary,
            total_capacity=total_max_capacity,
            total_extra_beds=total_extra_beds,
            nights=nights,
            total_price=total_price,
            currency=currency,
            reason=self._generate_reason(
                combination=combination,
                total_guests=total_guests,
                total_max_capacity=total_max_capacity,
                total_extra_beds=total_extra_beds
            )
        )

    def _distribute_extra_beds(
        self,
        combination: List[Dict[str, Any]],
        extra_guests: int
    ) -> List[int] | None:
        """
        Distribute extra guests across rooms.

        Each room can accommodate:

            max_occupancy - base_occupancy

        extra beds.

        Returns a list where each value corresponds to the number
        of extra beds used in that room.
        """

        remaining_extra_guests = extra_guests
        extra_bed_distribution = []

        for room in combination:
            extra_bed_capacity = (
                room["max_occupancy"]
                - room["base_occupancy"]
            )

            extra_beds_for_room = min(
                remaining_extra_guests,
                extra_bed_capacity
            )

            extra_bed_distribution.append(
                extra_beds_for_room
            )

            remaining_extra_guests -= extra_beds_for_room

        if remaining_extra_guests > 0:
            return None

        return extra_bed_distribution

    def _build_room_summary(
        self,
        combination: List[Dict[str, Any]],
        extra_bed_distribution: List[int]
    ) -> List[RecommendedRoom]:
        """
        Combine identical room types into a compact response.
        """

        summary = {}

        for room, extra_beds in zip(
            combination,
            extra_bed_distribution
        ):
            room_type = room["type"]

            if room_type not in summary:
                summary[room_type] = {
                    "quantity": 0,
                    "capacity_used": 0,
                    "extra_beds": 0,
                    "base_occupancy": room["base_occupancy"]
                }

            summary[room_type]["quantity"] += 1
            summary[room_type]["extra_beds"] += extra_beds

        remaining_guests = sum(
            room["base_occupancy"]
            for room in combination
        ) + sum(extra_bed_distribution)

        # Calculate how many guests are actually assigned to each
        # room type for display purposes.
        for room_type, details in summary.items():
            room_capacity = (
                details["quantity"]
                * details["base_occupancy"]
                + details["extra_beds"]
            )

            details["capacity_used"] = min(
                room_capacity,
                remaining_guests
            )

            remaining_guests -= details["capacity_used"]

        result = []

        for room_type, details in summary.items():
            result.append(
                RecommendedRoom(
                    room_type=room_type,
                    quantity=details["quantity"],
                    capacity_used=details["capacity_used"],
                    extra_beds=details["extra_beds"]
                )
            )

        return result

    def _calculate_total_price(
        self,
        combination: List[Dict[str, Any]],
        extra_bed_distribution: List[int],
        nights: int
    ) -> float:
        """
        Calculate:

        (
            total room price per night
            +
            total extra bed price per night
        )
        × number of nights
        """

        total_price_per_night = 0.0

        for room, extra_beds in zip(
            combination,
            extra_bed_distribution
        ):
            room_price = float(
                room["price_per_night"]
            )

            extra_bed_price = float(
                room["extra_bed_price"]
            )

            total_price_per_night += room_price

            total_price_per_night += (
                extra_beds * extra_bed_price
            )

        return total_price_per_night * nights

    def _generate_reason(
        self,
        combination: List[Dict[str, Any]],
        total_guests: int,
        total_max_capacity: int,
        total_extra_beds: int
    ) -> str:
        """
        Generate a deterministic reason for recommending
        this combination.
        """

        unused_capacity = (
            total_max_capacity - total_guests
        )

        room_count = len(combination)

        if unused_capacity == 0:
            return (
                f"Exact capacity match for {total_guests} guests."
            )

        if total_extra_beds == 0:
            return (
                f"Comfortable fit for {total_guests} guests "
                f"using {room_count} room(s)."
            )

        return (
            f"Fits {total_guests} guests using "
            f"{total_extra_beds} extra bed(s)."
        )

    def _rank_combinations(
        self,
        recommendations: List[RoomRecommendation]
    ) -> List[RoomRecommendation]:
        """
        Rank combinations.

        Priority:
        1. Fewer extra beds
        2. Less unused capacity
        3. Fewer rooms
        4. Lower price
        """

        def ranking_key(
            recommendation: RoomRecommendation
        ):
            unused_capacity = (
                recommendation.total_capacity
                - sum(
                    room.capacity_used
                    for room in recommendation.rooms
                )
            )

            room_count = sum(
                room.quantity
                for room in recommendation.rooms
            )

            return (
                recommendation.total_extra_beds,
                unused_capacity,
                room_count,
                recommendation.total_price
            )

        sorted_recommendations = sorted(
            recommendations,
            key=ranking_key
        )

        for index, recommendation in enumerate(
            sorted_recommendations,
            start=1
        ):
            recommendation.rank = index

        return sorted_recommendations