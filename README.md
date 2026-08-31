# StayChat - Hotel Booking Conversation Agent

StayChat is a hotel-agnostic AI booking conversation agent designed for a WhatsApp-first hotel booking workflow.

The agent accepts guest messages, maintains context across multiple turns, asks only for missing booking information, supports English/Hinglish/Hindi expressions, and recommends at most three suitable room combinations.

## Features

- Multi-turn conversation state management
- English, Hinglish, and common Hindi input support
- Extracts check-in date, check-out date, adults, children, children ages, room count, AC/non-AC preference, and special requests
- Never re-asks for information already stored in the conversation state
- Does not assume a one-night stay
- Asks explicitly for a missing check-out date
- Recommends at most three ranked room combinations
- Supports combinations containing multiple rooms
- Calculates total price for the stay
- Reads hotel-specific information only from `data/inventory.json`
- Handles policy questions using available inventory data
- Does not hallucinate unsupported hotel facilities or services
- Returns structured JSON on every turn
- Supports booking confirmation
- Uses in-memory session storage
- Dockerized for easy execution

---

# Tech Stack

- Python 3.11
- Flask
- LangChain
- Groq
- Pydantic
- Docker
- Docker Compose

---

# Project Structure

```text
staychat/
│
├── app/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── booking_agent.py
│   │   ├── extractor.py
│   │   └── prompts.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── inventory_service.py
│   │   └── recommendation_service.py
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   └── date_utils.py
│   │
│   ├── static/
│   │   ├── style.css
│   │   └── script.js
│   │
│   ├── templates/
│   │   └── index.html
│   │
│   ├── config.py
│   └── main.py
│
├── data/
│   └── inventory.json
│
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

# How to Run

## Prerequisites

Install:

- Docker
- Docker Compose

Create a `.env` file from `.env.example` and add a valid Groq API key and model:

```env
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=your_available_groq_model
```

From a clean clone, run the application in three commands or fewer:

```bash
git clone <repository-url>
cd staychat
docker compose up --build
```

Then open:

```text
http://localhost:5000
```

The application provides a chat interface and a `POST /chat` endpoint.

---

# API

## POST `/chat`

Example request:

```json
{
  "session_id": "guest-001",
  "message": "2 rooms, 15th to 17th, 4 adults, AC"
}
```

Example response:

```json
{
  "reply": "Here are the best room options for you...",
  "state": {
    "check_in": "2026-09-15",
    "check_out": "2026-09-17",
    "adults": 4,
    "children": null,
    "children_ages": [],
    "rooms_requested": 2,
    "ac_preference": "AC",
    "special_requests": [],
    "recommendations": []
  },
  "status": "recommending"
}
```

Each response contains:

- A guest-facing reply
- The current known booking state
- A status field

Possible statuses are:

```text
gathering
recommending
confirmed
```

---

# Architecture

The LLM is responsible for understanding the latest guest message and extracting structured booking information and intent. It is used for natural-language understanding because guests may express the same requirement in many ways, including English, Hinglish, and Hindi.

Deterministic Python code handles date normalization and validation, including expressions such as `tomorrow`, `kal`, `aaj`, `parso`, explicit date ranges, and weekend dates. This avoids relying on the LLM for arithmetic and validation.

Conversation state is loaded and merged deterministically so information supplied in earlier turns is preserved and is not repeatedly requested.

Room occupancy, room combinations, ranking, and total price calculations are handled deterministically.

Hotel-specific information such as hotel name, room types, occupancy, prices, check-in/check-out times, and policies comes from `inventory.json`.

At most three combinations are returned. Unsupported hotel information is never invented.

The boundary is therefore: **LLM for language understanding; deterministic code for dates, state, pricing, occupancy, recommendations, and validation; inventory data as the source of hotel truth.**

---

# Conversation State

Conversation state is stored in memory using `session_id` as the key.

A typical state contains:

```json
{
  "check_in": null,
  "check_out": null,
  "adults": null,
  "children": null,
  "children_ages": [],
  "rooms_requested": null,
  "ac_preference": null,
  "special_requests": [],
  "selected_option": null,
  "recommendations": []
}
```

For every guest message:

1. The current state is loaded using the `session_id`.
2. The latest message is sent to the extraction component.
3. The extractor returns only information explicitly stated or clearly implied by the latest message.
4. Deterministic code normalizes date expressions and validates date ranges.
5. New values are merged into the existing state.
6. Existing values remain unchanged unless the guest explicitly changes them.
7. The agent identifies only the information still required for booking.
8. If required information is missing, the agent asks for the next missing item.
9. If enough information is available, the recommendation service generates up to three options.
10. The updated state is stored back in memory.

This approach prevents repeated questions. For example, once the guest has provided the number of adults, the agent should not ask for it again unless the guest explicitly changes the number.

---

# Inventory Source

The application is hotel-agnostic.

All hotel-specific information is loaded from:

```text
data/inventory.json
```

The booking logic does not hardcode:

- Hotel name
- Room names
- Room prices
- Room occupancy
- Extra-bed prices
- Check-in time
- Check-out time
- Hotel policies

The same application logic can therefore work with another hotel's inventory by replacing the inventory data.

---

# Test Transcripts

## 1. "Room available for tomorrow?"

### Guest

```text
Room available for tomorrow?
```

### Bot

```text
How many adults will be staying?
```

### Guest

```text
2
```

### Bot

```text
What date would you like to check out?
```

### Guest

```text
day after tomorrow
```

### Bot

```text
Do you prefer an AC room or a non-AC room?
```

### Guest

```text
AC
```

### Bot

```text
Here are the best room options for you:

1. Option 1 ...
2. Option 2 ...
3. Option 3 ...

Reply with the option number if you would like to book.
```

The important behavior here is that the agent resolves `tomorrow` as the check-in date but does not automatically assume a check-out date or a one-night stay.

---

## 2. "2 rooms, 15th to 17th, 4 adults, AC"

### Guest

```text
2 rooms, 15th to 17th, 4 adults, AC
```

### Extracted and normalized information

```json
{
  "check_in": "2026-09-15",
  "check_out": "2026-09-17",
  "adults": 4,
  "rooms_requested": 2,
  "ac_preference": "AC"
}
```

### Bot

```text
Here are the best options at Hotel Sahu for 4 guest(s),
from 2026-09-15 to 2026-09-17:

1. Suitable room combination — total price ...
2. Suitable room combination — total price ...
3. Suitable room combination — total price ...

Reply with the option number if you would like to book.
```

No follow-up question is required because the message already contains the dates, guest count, room count, and AC preference.

---

## 3. "kal ke liye room chahiye, 3 log hain"

### Guest

```text
kal ke liye room chahiye, 3 log hain
```

### Bot

```text
What date would you like to check out?
```

The agent understands:

- `kal` = tomorrow
- `3 log hain` = 3 guests/adults when children are not separately mentioned

It does not invent the check-out date.

### Guest

```text
3rd sept tak
```

### Bot

```text
Do you prefer an AC room or a non-AC room?
```

### Guest

```text
AC
```

### Bot

```text
Here are the best options for you:

1. Option 1 ...
2. Option 2 ...
3. Option 3 ...

Reply with the option number if you would like to book.
```

---

## 4. "AC room chahiye" -> later -> "non-AC me kya rate hai"

### Guest

```text
AC room chahiye
```

### Bot

```text
Sure. Please tell me the check-in date.
```

The state now stores:

```json
{
  "ac_preference": "AC"
}
```

Later in the conversation:

### Guest

```text
non-AC me kya rate hai
```

### Extracted information

```json
{
  "intent": "price_query",
  "ac_preference": "NON_AC"
}
```

### Bot

```text
The available non-AC room option is shown in the hotel inventory.
Please share your check-in and check-out dates so I can calculate the total stay price.
```

The explicit new preference updates the previous preference from `AC` to `NON_AC`. The agent does not continue using the old AC preference after the guest has changed it.

---

## 5. "We are 7 people, 2 kids aged 4 and 6, need rooms this weekend"

### Guest

```text
We are 7 people, 2 kids aged 4 and 6, need rooms this weekend
```

### Extracted information

```json
{
  "adults": 7,
  "children": 2,
  "children_ages": [4, 6],
  "check_in": "this weekend"
}
```

Deterministic date handling resolves the weekend expression into concrete dates according to the application's date logic.

### Bot

```text
What date would you like to check out?
```

If the application defines `this weekend` as a complete stay range, it may instead proceed directly once all required information is available. Otherwise, it explicitly asks for the missing check-out date rather than inventing one.

After a valid check-out date is supplied:

### Bot

```text
Here are the best room options for your group:

1. Suitable combination — total price ...
2. Suitable combination — total price ...
3. Suitable combination — total price ...

Reply with the option number if you would like to book.
```

The room recommendation logic considers total occupancy when generating combinations. The policy `children_under_5_free` is read from `inventory.json`; it is not hardcoded into the business logic.

---

## 6. Mid-booking: "Do you have a swimming pool?"

### Guest

```text
Need a room for tomorrow.
```

### Bot

```text
How many adults will be staying?
```

### Guest

```text
2 adults
```

### Bot

```text
What date would you like to check out?
```

### Guest

```text
Do you have a swimming pool?
```

### Bot

```text
I do not have swimming pool information in the available hotel inventory, so I cannot confirm whether the hotel has one. I can continue helping with your room booking.
```

The agent does not answer `yes` or `no` because swimming pool information is not guaranteed by `inventory.json`.

The booking state is preserved while answering the out-of-scope question.

### Guest

```text
Day after tomorrow
```

### Bot

```text
Do you prefer an AC room or a non-AC room?
```

The conversation continues from the previously stored booking state.

---

# Confirmation Flow

After room recommendations are generated:

### Guest

```text
I want option 2
```

### Bot

```text
You selected option 2. Please confirm if you would like to proceed with this booking.
```

### Guest

```text
Yes, confirm it
```

### Bot

```text
Your booking request has been confirmed.
```

The final response uses:

```json
{
  "status": "confirmed"
}
```

---

# Handling Policy and Unsupported Questions

The agent does not hallucinate hotel information.

For policy questions, it uses only information available in `inventory.json`.

For example, if the inventory contains cancellation information, the agent can answer a cancellation-policy question from that data.

Questions about facilities or services that are not present in the inventory, such as:

- Swimming pool
- Taxi service
- Airport transfer
- Parking
- Restaurant
- WiFi

are treated as unsupported or out-of-scope.

The agent responds that it cannot verify the information from the available hotel inventory instead of inventing an answer.

Example:

```text
I don't have that information in the available hotel inventory, so I can't confirm it.
```

The current booking state remains unchanged after answering such a question.

This design was chosen to prevent hallucination. `inventory.json` is treated as the source of truth for hotel-specific facts.

---

# What I Would Build Next With One More Week

## 1. Persistent Conversation Storage

Replace the in-memory dictionary with Redis or a database so conversations survive application restarts and can work across multiple application instances.

## 2. Real Availability by Date

Add date-specific room availability so the agent can distinguish between room types that exist in the catalogue and rooms that are actually available for a requested stay.

## 3. Stronger Multilingual Date Parsing

Expand deterministic date handling for expressions such as:

```text
next Friday
agle Friday
kal
parso
is weekend
Monday tak
15 September se 18 September
```

The final date validation would remain deterministic.

## 4. More Complete Guest and Child Pricing

Extend `inventory.json` with explicit rules for:

- Children
- Extra beds
- Age-based pricing
- Taxes
- Additional charges

Then calculate prices entirely from inventory data.

## 5. Persistent Booking Records

After confirmation, create a booking record containing:

- Booking ID
- Session ID
- Selected room combination
- Check-in date
- Check-out date
- Guest count
- Total amount
- Booking status

## 6. Automated Testing

Add unit and integration tests for:

- Date parsing
- Date range validation
- Conversation state merging
- English extraction
- Hinglish extraction
- Hindi expressions
- Room combination generation
- Occupancy validation
- Price calculation
- Policy queries
- Out-of-scope queries
- Confirmation flow
- All six required test conversations

## 7. LLM Reliability Improvements

Add normalization and fallback handling for harmless LLM output variations, such as an intent label that differs slightly from the expected schema.

This would reduce failures caused by outputs such as:

```text
availability_query
```

when the schema expects:

```text
availability
```

## 8. Production Deployment

For production, I would add:

- Gunicorn or another production WSGI server
- Structured logging
- Health-check endpoints
- Request validation
- Error monitoring
- Rate limiting
- Retry and fallback behavior
- Environment-based configuration
- Automated CI tests

---

# Design Principle

**LLM for language understanding. Deterministic code for business logic. Inventory data as the source of hotel truth.**

This separation keeps natural-language understanding flexible while making state management, date validation, occupancy calculations, pricing, room ranking, and hotel facts predictable, reproducible, and easier to test.
