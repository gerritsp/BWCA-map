from Lake import Lake
class Portage:
    def __init__(self, Lake_a: Lake, Lake_b: Lake, length_rods: int):

        self.Lake_a = Lake_a
        self.Lake_b = Lake_b
        self.length_rods = length_rods

    def get_length(self) -> float:
        """Dynamically calculates length based on the current bubble positions."""
        dx = self.Lake_b.x - self.Lake_a.x
        dy = self.Lake_b.y - self.Lake_a.y
        return (dx ** 2 + dy ** 2) ** 0.5
