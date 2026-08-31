import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class InventoryService:
    """
    Loads and provides access to hotel inventory data.

    All hotel-specific information must come from inventory.json.
    """

    def __init__(self, inventory_path: str):
        self.inventory_path = Path(inventory_path)
        self.inventory = self._load_inventory()

    def _load_inventory(self) -> Dict[str, Any]:
        """
        Load inventory.json when the application starts.
        """
        if not self.inventory_path.exists():
            raise FileNotFoundError(
                f"Inventory file not found: {self.inventory_path}"
            )

        try:
            with open(
                self.inventory_path,
                "r",
                encoding="utf-8"
            ) as file:
                inventory = json.load(file)

        except json.JSONDecodeError as error:
            raise ValueError(
                f"Invalid JSON in inventory file: {error}"
            ) from error

        self._validate_inventory(inventory)

        return inventory

    def _validate_inventory(
        self,
        inventory: Dict[str, Any]
    ) -> None:
        """
        Validate the minimum required inventory structure.
        """
        required_fields = [
            "hotel_id",
            "hotel_name",
            "currency",
            "rooms",
            "policies"
        ]

        for field in required_fields:
            if field not in inventory:
                raise ValueError(
                    f"Missing required inventory field: {field}"
                )

        if not isinstance(inventory["rooms"], list):
            raise ValueError(
                "'rooms' must be a list."
            )

        if not inventory["rooms"]:
            raise ValueError(
                "Inventory must contain at least one room type."
            )

        required_room_fields = [
            "type",
            "base_occupancy",
            "max_occupancy",
            "extra_bed_price",
            "price_per_night"
        ]

        for room in inventory["rooms"]:
            for field in required_room_fields:
                if field not in room:
                    raise ValueError(
                        f"Room is missing required field: {field}"
                    )

            if (
                room["base_occupancy"]
                > room["max_occupancy"]
            ):
                raise ValueError(
                    f"Invalid occupancy for room: {room['type']}"
                )

    def get_hotel_id(self) -> str:
        """
        Return the hotel ID.
        """
        return self.inventory["hotel_id"]

    def get_hotel_name(self) -> str:
        """
        Return the hotel name.
        """
        return self.inventory["hotel_name"]

    def get_currency(self) -> str:
        """
        Return the hotel's currency.
        """
        return self.inventory["currency"]

    def get_check_in_time(self) -> Optional[str]:
        """
        Return check-in time if available.
        """
        return self.inventory.get("check_in_time")

    def get_check_out_time(self) -> Optional[str]:
        """
        Return check-out time if available.
        """
        return self.inventory.get("check_out_time")

    def get_all_rooms(self) -> List[Dict[str, Any]]:
        """
        Return all room types.
        """
        return self.inventory["rooms"]

    def get_room_by_type(
        self,
        room_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find a room using its exact type name.
        """
        for room in self.get_all_rooms():
            if room["type"].lower() == room_type.lower():
                return room

        return None

    def get_rooms_by_ac_preference(
        self,
        ac_preference: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        Filter rooms according to AC preference.

        AC:
            Returns room types containing 'AC' but not 'Non-AC'.

        NON_AC:
            Returns room types containing 'Non-AC'.

        ANY or None:
            Returns all rooms.
        """
        rooms = self.get_all_rooms()

        if not ac_preference or ac_preference == "ANY":
            return rooms

        if ac_preference == "NON_AC":
            return [
                room
                for room in rooms
                if "non-ac" in room["type"].lower()
                or "non ac" in room["type"].lower()
            ]

        if ac_preference == "AC":
            return [
                room
                for room in rooms
                if "ac" in room["type"].lower()
                and "non-ac" not in room["type"].lower()
                and "non ac" not in room["type"].lower()
            ]

        return rooms

    def get_policies(self) -> Dict[str, Any]:
        """
        Return all policies exactly as provided in inventory.json.
        """
        return self.inventory["policies"]

    def get_policy(
        self,
        policy_name: str
    ) -> Optional[Any]:
        """
        Return a specific policy.

        Returns None if the policy does not exist.
        This is important for preventing hallucination.
        """
        return self.inventory["policies"].get(policy_name)

    def has_policy(
        self,
        policy_name: str
    ) -> bool:
        """
        Check whether a policy exists in inventory.json.
        """
        return policy_name in self.inventory["policies"]

    def get_inventory_summary(self) -> Dict[str, Any]:
        """
        Return hotel information that can safely be supplied
        to other parts of the application.
        """
        return {
            "hotel_id": self.get_hotel_id(),
            "hotel_name": self.get_hotel_name(),
            "currency": self.get_currency(),
            "check_in_time": self.get_check_in_time(),
            "check_out_time": self.get_check_out_time(),
            "rooms": self.get_all_rooms(),
            "policies": self.get_policies()
        }