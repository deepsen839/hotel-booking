from typing import List, Literal, Optional

from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    """
    Request received by the /chat endpoint.
    """


    session_id: str = Field(
        ...,
        description="Unique ID used to maintain conversation state."
    )
    message: str = Field(
        ...,
        min_length=1,
        description="Guest message."
    )


from typing import Literal, Optional

from pydantic import BaseModel, Field


class ExtractedBookingInfo(BaseModel):
    """
    Information extracted from the latest guest message.
    Fields are optional because a guest may provide only
    part of the booking information in each turn.
    """

    check_in: Optional[str] = None
    check_out: Optional[str] = None

    adults: Optional[int] = None

    children: Optional[int] = None

    children_ages: Optional[list[int]] = None

    rooms_requested: Optional[int] = None

    ac_preference: Optional[
        Literal["AC", "NON_AC"]
    ] = None

    special_requests: Optional[list[str]] = None

    selected_option: Optional[int] = None

    recommendations: Optional[list] = None

    intent: Optional[
        Literal[
            "booking",
            "availability",
            "price_query",
            "policy_query",
            "confirmation",
            "out_of_scope",
            "other",
        ]
    ] = None

    policy_topic: Optional[str] = None

    wants_confirmation: Optional[bool] = None


class BookingState(BaseModel):
    """
    Complete state stored for each conversation session.
    """


    check_in: Optional[str] = None
    check_out: Optional[str] = None

    adults: Optional[int] = None
    children: Optional[int] = None
    children_ages: List[int] = Field(default_factory=list)

    rooms_requested: Optional[int] = None

    ac_preference: Optional[Literal["AC", "NON_AC", "ANY"]] = None

    special_requests: List[str] = Field(default_factory=list)

    selected_option: Optional[int] = None

    recommendations: List["RoomRecommendation"] = Field(
        default_factory=list
    )


class RecommendedRoom(BaseModel):
    """
    A single room type inside a recommendation combination.
    """

    room_type: str
    quantity: int
    capacity_used: int
    extra_beds: int = 0

class RoomRecommendation(BaseModel):
    """
    One complete room combination recommended to the guest.
    """


    rank: int

    rooms: List[RecommendedRoom]

    total_capacity: int

    total_extra_beds: int = 0

    nights: int

    total_price: float

    currency: str

    reason: str


class ChatResponse(BaseModel):
    """
    Final response returned by the API every turn.
    """

    reply: str

    state: BookingState

    status: Literal[
        "gathering",
        "recommending",
        "confirmed"
    ]

    recommendations: List[RoomRecommendation] = Field(
        default_factory=list
    )

