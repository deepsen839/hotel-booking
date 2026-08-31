import re
from copy import deepcopy
from typing import Dict, List, Optional, Tuple

from app.agent.extractor import BookingExtractor
from app.models.schemas import (
    BookingState,
    ChatResponse,
    ExtractedBookingInfo,
    RoomRecommendation,
)
from app.services.inventory_service import InventoryService
from app.services.recommendation_service import RecommendationService
from app.utils.date_utils import (
    calculate_nights,
    is_valid_stay,
    parse_date_range,
    parse_guest_date,
    parse_weekend_range,
)

class BookingAgent:
    """
    Main hotel booking conversation agent.

    Responsibilities:
    - Maintain in-memory conversation state
    - Extract information using Groq + LangChain
    - Merge new information with previous state
    - Ask only for missing information
    - Handle policy and out-of-scope questions
    - Generate room recommendations
    - Confirm a selected recommendation
    """

    def __init__(
        self,
        inventory_service: InventoryService
    ) -> None:
        self.inventory_service = inventory_service
        self.extractor = BookingExtractor()

        self.recommendation_service = RecommendationService(
            inventory_service
        )

        # In-memory conversation storage.
        # Key: session_id
        # Value: BookingState
        self.sessions: Dict[str, BookingState] = {}

    def chat(
        self,
        session_id: str,
        message: str
    ) -> ChatResponse:

        current_state = self._get_state(session_id)

        extracted = self.extractor.extract(
            message=message,
            current_state=current_state.model_dump()
        )

        # Resolve explicit ranges first.
        extracted = self._apply_date_range_fallback(
            message=message,
            extracted=extracted
        )

        # Apply contextual date handling.
        extracted = self._apply_contextual_fallback(
            message=message,
            current_state=current_state,
            extracted=extracted
        )

        # Apply single-date fallback.
        extracted = self._apply_date_fallback(
            message=message,
            current_state=current_state,
            extracted=extracted
        )

        # ------------------------------------------
        # VALIDATE DATES HERE
        # ------------------------------------------

        if (
            extracted.check_in is not None
            and extracted.check_out is not None
        ):
            if not is_valid_stay(
                extracted.check_in,
                extracted.check_out
            ):
                return self._invalid_checkout_response(
                    session_id=session_id,
                    state=current_state,
                    check_in=extracted.check_in
                )

        elif (
            current_state.check_in is not None
            and extracted.check_out is not None
        ):
            if not is_valid_stay(
                current_state.check_in,
                extracted.check_out
            ):
                return self._invalid_checkout_response(
                    session_id=session_id,
                    state=current_state,
                    check_in=current_state.check_in
                )

        # Handle confirmation.
        if extracted.wants_confirmation:
            return self._handle_confirmation(
                session_id=session_id,
                state=current_state
            )

        updated_state = self._merge_state(
            current_state=current_state,
            extracted=extracted
        )

        self._save_state(
            session_id=session_id,
            state=updated_state
        )

        if extracted.intent == "policy_query":
            return self._handle_policy_query(
                session_id=session_id,
                state=updated_state,
                extracted=extracted
            )

        if extracted.intent == "out_of_scope":
            return self._handle_out_of_scope(
                session_id=session_id,
                state=updated_state
            )

        return self._handle_booking_flow(
            session_id=session_id,
            state=updated_state
        )

    def _get_state(
        self,
        session_id: str
    ) -> BookingState:
        """
        Get the existing state for a session.

        Create an empty state for a new conversation.
        """

        if session_id not in self.sessions:
            self.sessions[session_id] = BookingState()

        return deepcopy(self.sessions[session_id])

    def _save_state(
        self,
        session_id: str,
        state: BookingState
    ) -> None:
        """
        Save state in memory.
        """

        self.sessions[session_id] = deepcopy(state)

    def _apply_contextual_fallback(
        self,
        message: str,
        current_state: BookingState,
        extracted: ExtractedBookingInfo
    ) -> ExtractedBookingInfo:
        """
        Handle short contextual replies that an LLM may fail to
        interpret correctly.

        Example:

        Bot: How many adults will be staying?
        Guest: 2

        Since adults are missing from the current state, interpret
        the numeric reply as the number of adults.
        """

        clean_message = message.strip().lower()

        # Extract a message containing only one integer.
        match = re.fullmatch(
            r"(\d+)",
            clean_message
        )

        if not match:
            return extracted

        number = int(
            match.group(1)
        )

        # If adults are missing, a short numeric response is most
        # likely answering the previous question about adults.
        if (
            current_state.adults is None
            and extracted.adults is None
        ):
            extracted.adults = number

            return extracted

        # If the agent already knows adults but children are missing,
        # interpret a numeric response as children.
        if (
            current_state.adults is not None
            and current_state.children is None
            and extracted.children is None
        ):
            extracted.children = number

        return extracted



    def _merge_state(
        self,
        current_state: BookingState,
        extracted: ExtractedBookingInfo
    ) -> BookingState:
        """
        Merge newly extracted information.

        Only overwrite a field when the guest explicitly
        provides a new value.
        """

        state = deepcopy(current_state)

        if extracted.check_in is not None:
            state.check_in = extracted.check_in

        if extracted.check_out is not None:
            state.check_out = extracted.check_out

        if extracted.adults is not None:
            state.adults = extracted.adults

        if extracted.children is not None:
            state.children = extracted.children

        if extracted.children_ages is not None:
            state.children_ages = extracted.children_ages

        if extracted.rooms_requested is not None:
            state.rooms_requested = extracted.rooms_requested

        if extracted.ac_preference is not None:
            state.ac_preference = extracted.ac_preference

        if extracted.special_requests:
            for request in extracted.special_requests:
                if request not in state.special_requests:
                    state.special_requests.append(request)

        if extracted.selected_option is not None:
            state.selected_option = extracted.selected_option

        # If children ages are known but children count was not
        # explicitly extracted, derive the count safely.
        if (
            state.children_ages
            and state.children is None
        ):
            state.children = len(state.children_ages)

        return state

    def _handle_booking_flow(
        self,
        session_id: str,
        state: BookingState
    ) -> ChatResponse:
        """
        Continue the normal booking flow.
        """
        if state.children is None:
            state.children = 0
        # A single check-in date is interpreted as a one-night stay.
        # This avoids asking an unnecessary follow-up for common
        # requests such as "Room available for tomorrow?"
        # if state.check_in and not state.check_out:
        #     state.check_out = get_default_check_out(
        #         state.check_in
        #     )

        #     self._save_state(
        #         session_id=session_id,
        #         state=state
        #     )

        missing_field = self._get_next_missing_field(
            state
        )

        if missing_field is not None:
            reply = self._get_missing_field_question(
                missing_field
            )

            return ChatResponse(
                reply=reply,
                state=state,
                status="gathering",
                recommendations=[]
            )

        if not is_valid_stay(
            state.check_in,
            state.check_out
        ):
            return ChatResponse(
                reply=(
                    "Your check-out date should be after your "
                    "check-in date. Please share the correct dates."
                ),
                state=state,
                status="gathering",
                recommendations=[]
            )

        nights = calculate_nights(
            state.check_in,
            state.check_out
        )

        if nights is None:
            return ChatResponse(
                reply=(
                    "I couldn't understand the stay dates. "
                    "Please share your check-in and check-out dates."
                ),
                state=state,
                status="gathering",
                recommendations=[]
            )

        recommendations = (
            self.recommendation_service.get_recommendations(
                state=state,
                nights=nights
            )
        )

        state.recommendations = recommendations

        self._save_state(
            session_id=session_id,
            state=state
        )

        if not recommendations:
            return ChatResponse(
                reply=(
                    "I couldn't find a suitable room combination "
                    "for the details provided. You can try changing "
                    "the room preference or number of rooms."
                ),
                state=state,
                status="gathering",
                recommendations=[]
            )

        reply = self._format_recommendations(
            state=state,
            recommendations=recommendations
        )

        return ChatResponse(
            reply=reply,
            state=state,
            status="recommending",
            recommendations=recommendations
        )

    def _get_next_missing_field(
        self,
        state: BookingState
    ) -> Optional[str]:
        """
        Return only the next missing field.

        Asking one focused question at a time keeps the conversation
        short and avoids unnecessary follow-ups.
        """

        if state.check_in is None:
            return "check_in"

        if state.check_out is None:
            return "check_out"

        if state.adults is None:
            return "adults"

        # if state.children is None:
        #     return "children"

        return None

    def _get_missing_field_question(
        self,
        field_name: str
    ) -> str:
        """
        Return a focused question for the next missing field.
        """

        questions = {
            "check_in": (
                "What date would you like to check in?"
            ),
            "check_out": (
                "What date would you like to check out?"
            ),
            "adults": (
                "How many adults will be staying?"
            ),
        }

        return questions.get(
            field_name,
            "Could you share the missing booking details?"
        )

    def _format_recommendations(
        self,
        state: BookingState,
        recommendations: List[RoomRecommendation]
    ) -> str:
        """
        Convert deterministic recommendations into a guest-facing reply.
        """

        hotel_name = self.inventory_service.get_hotel_name()

        guests = (
            (state.adults or 0)
            + (state.children or 0)
        )

        lines = [
            (
                f"Here are the best options at {hotel_name} "
                f"for {guests} guest(s), from {state.check_in} "
                f"to {state.check_out}:"
            )
        ]

        for recommendation in recommendations:
            room_parts = []

            for room in recommendation.rooms:
                room_text = (
                    f"{room.quantity} × {room.room_type}"
                )

                if room.extra_beds > 0:
                    room_text += (
                        f" + {room.extra_beds} extra bed(s)"
                    )

                room_parts.append(room_text)

            rooms_text = ", ".join(room_parts)

            lines.append(
                (
                    f"{recommendation.rank}. {rooms_text} "
                    f"— ₹{recommendation.total_price:.0f} "
                    f"total for {recommendation.nights} night(s). "
                    f"{recommendation.reason}"
                )
            )

        lines.append(
            "Reply with the option number if you would like to book."
        )

        return "\n".join(lines)

    def _handle_confirmation(
        self,
        session_id: str,
        state: BookingState
    ) -> ChatResponse:
        """
        Confirm the booking when the guest explicitly confirms
        a selected option.
        """

        if not state.recommendations:
            return ChatResponse(
                reply=(
                    "Please choose a room option first. "
                    "I can then help confirm your booking."
                ),
                state=state,
                status="gathering",
                recommendations=[]
            )

        if state.selected_option is None:
            return ChatResponse(
                reply=(
                    "Please tell me which option you would like "
                    "to confirm, for example: Option 1."
                ),
                state=state,
                status="recommending",
                recommendations=state.recommendations
            )

        selected_recommendation = next(
            (
                recommendation
                for recommendation in state.recommendations
                if recommendation.rank == state.selected_option
            ),
            None
        )

        if selected_recommendation is None:
            return ChatResponse(
                reply=(
                    "I couldn't find that option. Please choose one "
                    "of the options I recommended."
                ),
                state=state,
                status="recommending",
                recommendations=state.recommendations
            )

        return ChatResponse(
            reply=(
                f"Your selection, Option "
                f"{selected_recommendation.rank}, is confirmed. "
                f"The total is ₹{selected_recommendation.total_price:.0f}."
            ),
            state=state,
            status="confirmed",
            recommendations=[selected_recommendation]
        )

    def _handle_policy_query(
        self,
        session_id: str,
        state: BookingState,
        extracted: ExtractedBookingInfo
    ) -> ChatResponse:
        """
        Answer only policies present in inventory.json.
        """

        policy_topic = extracted.policy_topic

        if not policy_topic:
            reply = (
                "I can help with booking information available "
                "in the hotel data, but I don't have enough "
                "information to answer that policy question."
            )
        else:
            policy_value = self.inventory_service.get_policy(
                policy_topic
            )

            if policy_value is None:
                reply = (
                    "I don't have that information in the available "
                    "hotel data, so I can't confirm it."
                )
            else:
                readable_topic = policy_topic.replace(
                    "_",
                    " "
                )

                reply = (
                    f"The {readable_topic} policy is: "
                    f"{policy_value}"
                )

        return ChatResponse(
            reply=reply,
            state=state,
            status="gathering",
            recommendations=[]
        )

    def _handle_out_of_scope(
        self,
        session_id: str,
        state: BookingState
    ) -> ChatResponse:
        """
        Handle questions about hotel information not present
        in inventory.json.

        Booking state is preserved.
        """

        reply = (
            "I don't have that information in the available hotel "
            "data, so I can't confirm it."
        )

        next_missing_field = self._get_next_missing_field(
            state
        )

        if next_missing_field is not None:
            reply += " " + self._get_missing_field_question(
                next_missing_field
            )

        return ChatResponse(
            reply=reply,
            state=state,
            status="gathering",
            recommendations=[]
        )

    def clear_session(
        self,
        session_id: str
    ) -> None:
        """
        Clear one conversation from memory.
        """

        if session_id in self.sessions:
            del self.sessions[session_id]

    # def _apply_date_fallback(
    #     self,
    #     message: str,
    #     current_state: BookingState,
    #     extracted: ExtractedBookingInfo
    # ) -> ExtractedBookingInfo:
    #     """
    #     Use conversation context to correctly assign
    #     dates to check-in or check-out.
    #     """

    #     parsed_date = parse_guest_date(
    #         message
    #     )

    #     if parsed_date is None:
    #         return extracted

    #     # Check-in is already known and check-out is missing.
    #     # Any date-only follow-up should be treated as check-out.
    #     if (
    #         current_state.check_in is not None
    #         and current_state.check_out is None
    #     ):
    #         extracted.check_in = None
    #         extracted.check_out = parsed_date

    #         return extracted

    #     # Check-in is missing, so use the date as check-in.
    #     if current_state.check_in is None:
    #         extracted.check_in = parsed_date

    #     return extracted

    def _apply_date_fallback(
        self,
        message: str,
        current_state: BookingState,
        extracted: ExtractedBookingInfo
    ) -> ExtractedBookingInfo:
        """
        Assign dates using conversation state.

        If check-in is already known and check-out is missing,
        a date provided by the guest is treated as check-out.
        """

        parsed_date = parse_guest_date(message)

        if parsed_date is None:
            return extracted

        # CASE 1:
        # We already know check-in and are waiting for check-out.
        #
        # Ignore the field chosen by the LLM and use the actual
        # conversation context.
        if (
            current_state.check_in is not None
            and current_state.check_out is None
        ):
            extracted.check_in = None
            extracted.check_out = parsed_date

            return extracted

        # CASE 2:
        # Check-in is missing, so the date is check-in.
        if current_state.check_in is None:
            extracted.check_in = parsed_date

            # Do not invent checkout.
            extracted.check_out = None

            return extracted

        return extracted

    def _apply_date_range_fallback(
        self,
        message: str,
        extracted: ExtractedBookingInfo
    ) -> ExtractedBookingInfo:
        """
        Apply deterministic parsing for date ranges.
        """

        check_in, check_out = parse_date_range(
            message
        )

        if check_in is not None and check_out is not None:
            extracted.check_in = check_in
            extracted.check_out = check_out
            return extracted

        if "weekend" in message.lower():
            check_in, check_out = parse_weekend_range(
                message
            )

            if check_in is not None:
                extracted.check_in = check_in

            if check_out is not None:
                extracted.check_out = check_out

        return extracted


    def _invalid_checkout_response(
        self,
        session_id: str,
        state: BookingState,
        check_in: str
    ) -> ChatResponse:
        """
        Return an error for an invalid check-out date.

        The invalid date is not merged into the state.
        """

        self._save_state(
            session_id=session_id,
            state=state
        )

        reply = (
            "Your check-out date should be after your "
            f"check-in date ({check_in}). "
            "Please share the correct date."
        )

        return ChatResponse(
            reply=reply,
            state=state,
            status="gathering"
        )