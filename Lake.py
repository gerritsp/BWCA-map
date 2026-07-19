from Portage import Portage
class Lake:
    def __init__(self, name: str):
        self.name = name
        self.campsites = []
        self.portages = []
        # Keep track of lines connected to this specific bubble
        # self.connections: list['Portage'] = []

    # def add_connection(self, Portage: 'Portage'):
    #     # Enforce your limit of 18 connections
    #     self.connections.append(Portage)