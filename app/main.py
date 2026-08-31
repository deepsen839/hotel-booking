from flask import Flask, jsonify, request, render_template
from pydantic import ValidationError

from app.agent.booking_agent import BookingAgent
from app.config import Config
from app.models.schemas import ChatRequest
from app.services.inventory_service import InventoryService


def create_app() -> Flask:
    """
    Create and configure the Flask application.
    """

    app = Flask(__name__)

    # Load hotel inventory once when the application starts.
    inventory_service = InventoryService(
        Config.INVENTORY_PATH
    )

    # Create one booking agent.
    # The agent maintains in-memory state for all sessions.
    booking_agent = BookingAgent(
        inventory_service=inventory_service
    )

    @app.get("/")
    def home():
        return render_template("index.html")


    @app.get("/health")
    def health():
        """
        Health-check endpoint.
        """

        return jsonify(
            {
                "status": "healthy",
                "hotel_id": inventory_service.get_hotel_id(),
                "hotel_name": inventory_service.get_hotel_name()
            }
        ), 200

    @app.post("/chat")
    def chat():
        """
        Main hotel booking conversation endpoint.

        Expected request:

        {
            "session_id": "guest_001",
            "message": "I need an AC room tomorrow for 2 people"
        }
        """

        try:
            request_data = request.get_json()

            if request_data is None:
                return jsonify(
                    {
                        "error": "Request body must contain valid JSON."
                    }
                ), 400

            chat_request = ChatRequest(
                **request_data
            )

        except ValidationError as error:
            return jsonify(
                {
                    "error": "Invalid request.",
                    "details": error.errors()
                }
            ), 400

        except Exception:
            return jsonify(
                {
                    "error": "Unable to read the request."
                }
            ), 400

        try:
            response = booking_agent.chat(
                session_id=chat_request.session_id,
                message=chat_request.message
            )

            return jsonify(
                response.model_dump()
            ), 200

        except ValueError as error:
            return jsonify(
                {
                    "error": str(error)
                }
            ), 400

        except Exception as error:
            app.logger.exception(
                "Unexpected error while processing chat."
            )

            return jsonify(
                {
                    "error": "An internal server error occurred."
                }
            ), 500

    @app.delete("/session/<session_id>")
    def clear_session(session_id: str):
        """
        Clear the in-memory conversation state for one session.
        """

        booking_agent.clear_session(
            session_id
        )

        return jsonify(
            {
                "message": (
                    f"Session '{session_id}' was cleared."
                )
            }
        ), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=Config.PORT,
        debug=Config.DEBUG
    )