import json
from datetime import date
from typing import Optional

from langchain_groq import ChatGroq

from app.agent.prompts import EXTRACTION_PROMPT
from app.config import Config
from app.models.schemas import ExtractedBookingInfo
from app.utils.date_utils import resolve_dates


class BookingExtractor:
    """
    Uses Groq + LangChain to extract structured booking information
    from the latest guest message.
    """

    def __init__(self) -> None:
        if not Config.GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is not set. "
                "Please add it to your .env file."
            )

        self.llm = ChatGroq(
            model=Config.GROQ_MODEL,
            groq_api_key=Config.GROQ_API_KEY,
            temperature=0
        )

        self.structured_llm = self.llm.with_structured_output(
            ExtractedBookingInfo,
            method="json_mode"
        )

        self.chain = (
            EXTRACTION_PROMPT
            | self.structured_llm
        )

    def extract(
        self,
        message: str,
        current_state: Optional[dict] = None
    ) -> ExtractedBookingInfo:
        """
        Extract booking information from the latest guest message.

        The current state is supplied only for context.
        The LLM should extract information from the latest message,
        not copy existing state values.
        """

        if current_state is None:
            current_state = {}

        result = self.chain.invoke(
            {
                "today": date.today().isoformat(),
                "current_state": json.dumps(
                    current_state,
                    indent=2,
                    default=str
                ),
                "message": message
            }
        )

        return self._normalize_extracted_dates(result)

    def _normalize_extracted_dates(
        self,
        extracted: ExtractedBookingInfo
    ) -> ExtractedBookingInfo:
        """
        Convert extracted date expressions into YYYY-MM-DD format.

        Examples:
            tomorrow -> 2026-09-02
            kal -> 2026-09-02
            this weekend -> upcoming Saturday and Monday
            15th -> YYYY-09-15, based on the date parser
        """

        check_in, check_out = resolve_dates(
            extracted.check_in,
            extracted.check_out
        )

        extracted.check_in = check_in
        extracted.check_out = check_out

        return extracted