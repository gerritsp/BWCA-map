from Portage import Portage
class Lake:
    def __init__(self, name: str, x: float, y: float):
        self.name = name
        self.x = x
        self.y = y
        # Keep track of lines connected to this specific bubble
        self.connections: list['Portage'] = []

    def add_connection(self, Portage: 'Portage'):
        # Enforce your limit of 18 connections
        self.connections.append(Portage)